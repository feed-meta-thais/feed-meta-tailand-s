#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
    return re.sub(r"\s+", " ", value).strip()


def get_text(parent: ET.Element, tag: str) -> str:
    child = parent.find(tag)
    return clean_text(child.text if child is not None else "")


def as_float(v: str) -> float:
    try:
        return float(v.replace(".", "", v.count(".") - 1).replace(",", "."))
    except Exception:
        return 0.0


def get_price(imovel: ET.Element) -> tuple[str, str] | None:
    venda = as_float(get_text(imovel, "PrecoVenda"))
    locacao = as_float(get_text(imovel, "PrecoLocacao"))

    if venda > 0:
        return f"{venda:.2f} BRL", "for_sale"
    if locacao > 0:
        return f"{locacao:.2f} BRL", "for_rent"
    return None


def slugify(value: str) -> str:
    value = clean_text(value).lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def extract_location_hint(imovel: ET.Element) -> str:
    cidade = get_text(imovel, "Cidade")
    text = " ".join([
        get_text(imovel, "Diferencial"),
        get_text(imovel, "Observacao")[:400],
        get_text(imovel, "Complemento"),
    ])

    candidates = [
        "Guará II", "Guará I", "Asa Norte", "Asa Sul", "Águas Claras", "Taguatinga",
        "Sudoeste", "Noroeste", "Sobradinho", "Lago Norte", "Lago Sul", "Candangolândia",
        "Ceilândia", "Samambaia", "Vicente Pires", "Park Sul", "Park Way", "Jardim Botânico",
        "Cruzeiro", "Octogonal", "Riacho Fundo", "Núcleo Bandeirante", "Santa Maria",
    ]

    for cand in candidates:
        if re.search(re.escape(cand), text, flags=re.IGNORECASE):
            return cand

    return cidade or "df"


def build_property_link(imovel: ET.Element, codigo: str) -> str:
    tipo = get_text(imovel, "TipoImovel") or "imovel"
    cidade = get_text(imovel, "Cidade") or "df"
    uf = get_text(imovel, "UF") or "df"
    quartos = get_text(imovel, "QtdDormitorios")
    area = get_text(imovel, "AreaUtil") or get_text(imovel, "AreaTotal")

    area = re.sub(r"\.0$", "", area)
    area = re.sub(r"[^0-9,\.]", "", area).replace(",", ".")
    if "." in area:
        area = area.rstrip("0").rstrip(".").replace(".", "-")

    parts = [
        slugify(tipo),
        slugify(extract_location_hint(imovel)),
        slugify(cidade),
        slugify(uf),
    ]

    if quartos and quartos != "0":
        parts.extend([slugify(quartos), "quartos"])

    if area and area != "0":
        parts.append(f"{slugify(area)}m2")

    slug = "-".join([p for p in parts if p])
    return f"{PROPERTY_BASE_URL.rstrip('/')}/{slug}-{codigo}"


def get_images(imovel: ET.Element) -> list[str]:
    fotos = imovel.findall("./Fotos/Foto")
    urls = []

    principal = ""
    for foto in fotos:
        url = get_text(foto, "URLArquivo")
        if not url:
            continue

        if get_text(foto, "Principal") == "1":
            principal = url
        else:
            urls.append(url)

    if principal:
        return [principal] + urls

    return urls


def build_name(imovel: ET.Element, codigo: str) -> str:
    diferencial = get_text(imovel, "Diferencial")
    if diferencial:
        return diferencial[:150]

    tipo = get_text(imovel, "TipoImovel") or "Imóvel"
    cidade = get_text(imovel, "Cidade")
    quartos = get_text(imovel, "QtdDormitorios")
    area = get_text(imovel, "AreaUtil") or get_text(imovel, "AreaTotal")

    parts = [tipo]
    if quartos and quartos != "0":
        parts.append(f"{quartos} quartos")
    if area and area != "0":
        parts.append(f"{area}m²")
    if cidade:
        parts.append(cidade)

    return " - ".join(parts)[:150] or codigo


def add_address(listing: ET.Element, imovel: ET.Element) -> None:
    address = ET.SubElement(listing, "address", {"format": "simple"})

    complemento = get_text(imovel, "Complemento")
    cidade = get_text(imovel, "Cidade")
    uf = get_text(imovel, "UF")
    cep = get_text(imovel, "CEP")

    ET.SubElement(address, "component", {"name": "addr1"}).text = complemento or cidade or "Endereço não informado"
    ET.SubElement(address, "component", {"name": "city"}).text = cidade or "Brasília"
    ET.SubElement(address, "component", {"name": "region"}).text = uf or "DF"
    ET.SubElement(address, "component", {"name": "postal_code"}).text = cep or ""
    ET.SubElement(address, "component", {"name": "country"}).text = "Brasil"


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

    listings = ET.Element("listings")
    ET.SubElement(listings, "title").text = "Thais Imobiliária - Feed Meta"

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

        price, availability = price_info
        images = get_images(imovel)
        if not images:
            skipped += 1
            continue

        name = build_name(imovel, codigo)
        description = get_text(imovel, "Observacao") or get_text(imovel, "Diferencial") or name
        description = description[:MAX_DESCRIPTION_LENGTH]
        url = build_property_link(imovel, codigo)

        listing = ET.SubElement(listings, "listing")

        for img_url in images[:20]:
            image = ET.SubElement(listing, "image")
            ET.SubElement(image, "url").text = img_url

        ET.SubElement(listing, "home_listing_id").text = codigo
        ET.SubElement(listing, "availability").text = availability
        ET.SubElement(listing, "url").text = url
        ET.SubElement(listing, "name").text = name
        ET.SubElement(listing, "description").text = description
        ET.SubElement(listing, "price").text = price

        add_address(listing, imovel)

        bairro = extract_location_hint(imovel)
        if bairro:
            ET.SubElement(listing, "neighborhood").text = bairro

        tipo = get_text(imovel, "TipoImovel")
        quartos = get_text(imovel, "QtdDormitorios")
        area = get_text(imovel, "AreaUtil") or get_text(imovel, "AreaTotal")
        vagas = get_text(imovel, "QtdVagas")

        if tipo:
            ET.SubElement(listing, "product_tags").text = tipo
        if quartos and quartos != "0":
            ET.SubElement(listing, "product_tags").text = f"{quartos} quartos"
        if area and area != "0":
            ET.SubElement(listing, "product_tags").text = f"{area}m2"
        if vagas and vagas != "0":
            ET.SubElement(listing, "product_tags").text = f"{vagas} vagas"

        converted += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    tree = ET.ElementTree(listings)
    ET.indent(tree, space="  ", level=0)
    tree.write(OUTPUT_PATH, encoding="utf-8", xml_declaration=True)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    INDEX_PATH.write_text(
        f"""<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>Feed Meta - Thais Imobiliária</title></head>
<body>
  <h1>Feed Meta - Thais Imobiliária</h1>
  <p>Última geração: {html.escape(generated_at)}</p>
  <p>Imóveis convertidos: {converted}</p>
  <p>Imóveis ignorados: {skipped}</p>
  <p><a href="feed-meta.xml">Abrir feed-meta.xml</a></p>
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
