#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Converte XML da Vista/Loft em feed RSS XML compatível com catálogo do Meta.
Gera docs/feed-meta.xml para publicação via GitHub Pages.
"""

from __future__ import annotations

import html
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SOURCE_XML_URL = os.getenv(
    "SOURCE_XML_URL",
    "https://thaisred-portais.vistahost.com.br/36ac72a03c01d6eab2a640de018e5a71",
)

# O site usa URLs no padrão:
# https://thaisimobiliaria.com.br/imovel/casa-guara-ii-guara-df-4-quartos-129m2-TH35309
PROPERTY_BASE_URL = os.getenv(
    "PROPERTY_BASE_URL",
    "https://thaisimobiliaria.com.br/imovel",
)

OUTPUT_PATH = Path(os.getenv("OUTPUT_PATH", "docs/feed-meta.xml"))
INDEX_PATH = Path(os.getenv("INDEX_PATH", "docs/index.html"))
MAX_DESCRIPTION_LENGTH = int(os.getenv("MAX_DESCRIPTION_LENGTH", "5000"))


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    return value


def get_text(parent: ET.Element, tag: str) -> str:
    child = parent.find(tag)
    return clean_text(child.text if child is not None else "")


def get_price(imovel: ET.Element) -> tuple[str, str] | None:
    venda = get_text(imovel, "PrecoVenda")
    locacao = get_text(imovel, "PrecoLocacao")

    def as_float(v: str) -> float:
        try:
            return float(v.replace(".", "", v.count(".") - 1).replace(",", "."))
        except Exception:
            return 0.0

    venda_val = as_float(venda)
    locacao_val = as_float(locacao)

    if venda_val > 0:
        return f"{venda_val:.2f} BRL", "Venda"
    if locacao_val > 0:
        return f"{locacao_val:.2f} BRL", "Locação"
    return None



def slugify(value: str) -> str:
    value = clean_text(value).lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def extract_location_hint(imovel: ET.Element) -> str:
    """Tenta extrair termos como 'Guará II', que aparecem no site antes da cidade."""
    cidade = get_text(imovel, "Cidade")
    uf = get_text(imovel, "UF")
    text = " ".join([
        get_text(imovel, "Diferencial"),
        get_text(imovel, "Observacao")[:400],
        get_text(imovel, "Complemento"),
    ])

    # Casos comuns no DF que aparecem nas URLs do site.
    candidates = [
        "Guará II", "Guará I", "Asa Norte", "Asa Sul", "Águas Claras", "Taguatinga",
        "Sudoeste", "Noroeste", "Sobradinho", "Lago Norte", "Lago Sul", "Candangolândia",
        "Ceilândia", "Samambaia", "Vicente Pires", "Park Sul", "Park Way", "Jardim Botânico",
        "Cruzeiro", "Octogonal", "Riacho Fundo", "Núcleo Bandeirante", "Santa Maria",
    ]
    for cand in candidates:
        if re.search(re.escape(cand), text, flags=re.IGNORECASE):
            return cand
    return cidade or uf or "df"


def build_property_link(imovel: ET.Element, codigo: str) -> str:
    tipo = get_text(imovel, "TipoImovel") or "imovel"
    cidade = get_text(imovel, "Cidade") or "df"
    uf = get_text(imovel, "UF") or "df"
    quartos = get_text(imovel, "QtdDormitorios")
    area = get_text(imovel, "AreaUtil") or get_text(imovel, "AreaTotal")
    area = re.sub(r"\.0$", "", area)
    area = re.sub(r"[^0-9,\.]", "", area).replace(",", ".")
    if "." in area:
        # Para URL, 129.00 vira 129 e 70.68 vira 70-68.
        area = area.rstrip("0").rstrip(".").replace(".", "-")

    parts = [slugify(tipo), slugify(extract_location_hint(imovel)), slugify(cidade), slugify(uf)]
    if quartos and quartos != "0":
        parts.extend([slugify(quartos), "quartos"])
    if area and area != "0":
        parts.append(f"{slugify(area)}m2")

    slug = "-".join([p for p in parts if p])
    return f"{PROPERTY_BASE_URL.rstrip('/')}/{slug}-{codigo}"


def get_main_image(imovel: ET.Element) -> tuple[str, list[str]]:
    fotos = imovel.findall("./Fotos/Foto")
    urls = []
    main = ""
    for foto in fotos:
        url = get_text(foto, "URLArquivo")
        if not url:
            continue
        urls.append(url)
        if get_text(foto, "Principal") == "1":
            main = url
    if not main and urls:
        main = urls[0]
    additional = [u for u in urls if u != main]
    return main, additional


def build_title(imovel: ET.Element, tipo_negocio: str) -> str:
    diferencial = get_text(imovel, "Diferencial")
    tipo = get_text(imovel, "TipoImovel")
    cidade = get_text(imovel, "Cidade")
    quartos = get_text(imovel, "QtdDormitorios")
    area = get_text(imovel, "AreaUtil") or get_text(imovel, "AreaTotal")

    if diferencial:
        return diferencial[:150]

    parts = [tipo or "Imóvel"]
    if quartos and quartos != "0":
        parts.append(f"{quartos} quartos")
    if area and area != "0":
        parts.append(f"{area}m²")
    if cidade:
        parts.append(cidade)
    parts.append(tipo_negocio)
    return " - ".join(parts)[:150]


def convert() -> tuple[int, int]:
    print(f"Baixando XML original: {SOURCE_XML_URL}")
    req = urllib.request.Request(
        SOURCE_XML_URL,
        headers={"User-Agent": "Mozilla/5.0 Meta Feed Converter"},
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        xml_bytes = response.read()

    root = ET.fromstring(xml_bytes)
    imoveis = root.findall("./Imoveis/Imovel")

    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:g": "http://base.google.com/ns/1.0",
    })
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Thais Imobiliária - Feed Meta"
    ET.SubElement(channel, "link").text = "https://www.thaisimobiliaria.com.br/"
    ET.SubElement(channel, "description").text = "Feed automático de imóveis para catálogo Meta."

    skipped = 0
    converted = 0

    for imovel in imoveis:
        codigo = get_text(imovel, "CodigoImovel")
        if not codigo:
            skipped += 1
            continue

        price_info = get_price(imovel)
        if not price_info:
            skipped += 1
            continue
        price, tipo_negocio = price_info

        image, additional_images = get_main_image(imovel)
        if not image:
            skipped += 1
            continue

        title = build_title(imovel, tipo_negocio)
        description = get_text(imovel, "Observacao") or get_text(imovel, "Diferencial") or title
        description = description[:MAX_DESCRIPTION_LENGTH]
        link = build_property_link(imovel, codigo)

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "g:id").text = codigo
        ET.SubElement(item, "g:title").text = title
        ET.SubElement(item, "g:description").text = description
        ET.SubElement(item, "g:link").text = link
        ET.SubElement(item, "g:image_link").text = image
        for img in additional_images[:10]:
            ET.SubElement(item, "g:additional_image_link").text = img
        ET.SubElement(item, "g:availability").text = "in stock"
        ET.SubElement(item, "g:price").text = price
        ET.SubElement(item, "g:condition").text = "new"
        ET.SubElement(item, "g:brand").text = "Thais Imobiliária"
        ET.SubElement(item, "g:google_product_category").text = "Home & Garden > Real Estate"
        ET.SubElement(item, "g:product_type").text = tipo_negocio

        # Campos extras úteis para diagnóstico/segmentação.
        ET.SubElement(item, "tipo_imovel").text = get_text(imovel, "TipoImovel")
        ET.SubElement(item, "cidade").text = get_text(imovel, "Cidade")
        ET.SubElement(item, "uf").text = get_text(imovel, "UF")
        ET.SubElement(item, "area_util").text = get_text(imovel, "AreaUtil")
        ET.SubElement(item, "quartos").text = get_text(imovel, "QtdDormitorios")
        ET.SubElement(item, "vagas").text = get_text(imovel, "QtdVagas")

        converted += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(OUTPUT_PATH, encoding="utf-8", xml_declaration=True)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    INDEX_PATH.write_text(
        f"""<!doctype html>
<html lang=\"pt-BR\">
<head><meta charset=\"utf-8\"><title>Feed Meta - Thais Imobiliária</title></head>
<body>
  <h1>Feed Meta - Thais Imobiliária</h1>
  <p>Última geração: {html.escape(generated_at)}</p>
  <p>Imóveis convertidos: {converted}</p>
  <p>Imóveis ignorados: {skipped}</p>
  <p><a href=\"feed-meta.xml\">Abrir feed-meta.xml</a></p>
</body>
</html>
""",
        encoding="utf-8",
    )

    print(f"Convertidos: {converted} | Ignorados: {skipped}")
    print(f"Arquivo gerado: {OUTPUT_PATH}")
    return converted, skipped


if __name__ == "__main__":
    try:
        convert()
    except Exception as exc:
        print(f"Erro ao converter XML: {exc}", file=sys.stderr)
        sys.exit(1)
