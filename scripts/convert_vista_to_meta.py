#!/usr/bin/env python3
"""
Converte o XML da Vista (Thaís Imobiliária) para o formato Meta Home Listings.
Documentação Meta: https://developers.facebook.com/docs/marketing-api/reference/product-catalog/home_listings/

Execução: python convert_vista_to_meta.py
Saída: docs/feed-meta.xml
"""

import urllib.request
import re
import os
from xml.etree import ElementTree as ET
from xml.dom import minidom

# ── Configuração ──────────────────────────────────────────────────────────────
VISTA_URL = "https://thaisred-portais.vistahost.com.br/36ac72a03c01d6eab2a640de018e5a71"
OUTPUT_FILE = "docs/feed-meta.xml"
BASE_LISTING_URL = "https://thaisimobiliaria.com.br/imovel"

# Tipos de imóvel da Vista → property_type do Meta
PROPERTY_TYPE_MAP = {
    "apartamento": "apartment",
    "casa": "house",
    "casa em condomínio": "townhouse",
    "cobertura": "apartment",
    "flat": "apartment",
    "kitnet": "apartment",
    "studio": "apartment",
    "sobrado": "house",
    "geminado": "house",
    "chácara": "house",
    "sítio": "house",
    "fazenda": "house",
    "terreno": "lot",
    "lote": "lot",
}

# Tipos comerciais — excluídos do feed residencial
COMMERCIAL_TYPES = {"loja", "sala comercial", "sala", "galpão", "prédio", "consultório",
                    "ponto comercial", "comercial", "garagem"}



def get_text(element, tag, default=""):
    """Retorna o texto de um subelemento, ou default se não existir/estiver vazio."""
    el = element.find(tag)
    if el is None or el.text is None:
        return default
    return el.text.strip()


def get_float(element, tag, default=0.0):
    try:
        return float(get_text(element, tag, "0").replace(",", "."))
    except ValueError:
        return default


def get_int(element, tag, default=0):
    try:
        return int(float(get_text(element, tag, "0")))
    except ValueError:
        return default


def build_listing_url(codigo, **_):
    """
    URL canônica do imóvel: o site aceita o código diretamente como slug.
    Ex: https://thaisimobiliaria.com.br/imovel/TH35314
    """
    return f"{BASE_LISTING_URL}/{codigo}"


def get_principal_photo(imovel):
    """Retorna a URL da foto principal (Principal=1) ou a primeira foto disponível."""
    fotos = imovel.find("Fotos")
    if fotos is None:
        return None

    first_url = None
    for foto in fotos.findall("Foto"):
        url = get_text(foto, "URLArquivo")
        if not url:
            continue
        if first_url is None:
            first_url = url
        if get_text(foto, "Principal") == "1":
            return url
    return first_url


def get_all_photos(imovel):
    """Retorna lista de URLs de todas as fotos do imóvel."""
    fotos = imovel.find("Fotos")
    if fotos is None:
        return []
    urls = []
    for foto in fotos.findall("Foto"):
        url = get_text(foto, "URLArquivo")
        if url:
            urls.append(url)
    return urls


def add_element(parent, tag, text):
    """Adiciona subelemento com texto ao parent."""
    el = ET.SubElement(parent, tag)
    el.text = str(text)
    return el


def convert(vista_xml_content):
    """Converte o XML da Vista para o formato Meta Home Listings."""
    root = ET.fromstring(vista_xml_content)
    imoveis = root.find("Imoveis")
    if imoveis is None:
        raise ValueError("Tag <Imoveis> não encontrada no XML da Vista.")

    listings_root = ET.Element("listings")

    skipped = 0
    converted = 0

    for imovel in imoveis.findall("Imovel"):
        codigo = get_text(imovel, "CodigoImovel")
        if not codigo:
            skipped += 1
            continue

        tipo_raw = get_text(imovel, "TipoImovel", "").strip()
        tipo_lower = tipo_raw.lower()

        # Filtra imóveis comerciais
        if tipo_lower in COMMERCIAL_TYPES:
            skipped += 1
            continue

        preco_locacao = get_float(imovel, "PrecoLocacao")
        preco_venda = get_float(imovel, "PrecoVenda")

        # Deve ter pelo menos um preço válido
        if preco_locacao <= 0 and preco_venda <= 0:
            skipped += 1
            continue

        # Define tipo de negócio
        if preco_locacao > 0:
            price_value = preco_locacao
            availability = "for_rent"
            listing_type = "for_rent"
        else:
            price_value = preco_venda
            availability = "for_sale"
            listing_type = "for_sale_by_agent"

        # Foto principal obrigatória
        photo_url = get_principal_photo(imovel)
        if not photo_url:
            skipped += 1
            continue

        # Campos de endereço
        cidade = get_text(imovel, "Cidade", "Brasília")
        uf = get_text(imovel, "UF", "DF")
        cep = get_text(imovel, "CEP", "").replace("-", "")
        complemento = get_text(imovel, "Complemento", "")
        nome_empreendimento = get_text(imovel, "NomeEmpreendimento", "")

        # addr1: usa complemento ou o nome do empreendimento
        addr1 = complemento or nome_empreendimento or cidade

        # Campos numéricos
        quartos = get_int(imovel, "QtdDormitorios")
        banheiros = get_int(imovel, "QtdBanheiros")
        suites = get_int(imovel, "QtdSuites")
        area = get_float(imovel, "AreaUtil")

        # QtdBanheiros costuma vir zerado no feed — usa suítes como mínimo
        num_baths = banheiros if banheiros > 0 else max(suites, 1)

        # property_type
        property_type = PROPERTY_TYPE_MAP.get(tipo_lower, "apartment")

        # name e description
        diferencial = get_text(imovel, "Diferencial", "")
        observacao = get_text(imovel, "Observacao", "")

        # Remove o código do imóvel do início do Diferencial (ex: "TH35314 - ...")
        name = re.sub(r"^TH\d+\s*-\s*", "", diferencial).strip() or tipo_raw
        # Trunca nome em 200 caracteres
        if len(name) > 200:
            name = name[:197] + "..."

        description = observacao or diferencial
        # Remove o código do início da descrição também
        description = re.sub(r"^TH\d+\s*-\s*", "", description).strip()
        # Trunca descrição em 5000 caracteres (limite Meta)
        if len(description) > 5000:
            description = description[:4997] + "..."

        # URL do imóvel
        listing_url = build_listing_url(codigo)

        # ── Monta o elemento <listing> ──────────────────────────────────────
        listing = ET.SubElement(listings_root, "listing")

        # Imagens — principal primeiro, depois as demais
        all_photos = get_all_photos(imovel)
        if photo_url in all_photos:
            all_photos.remove(photo_url)
        all_photos.insert(0, photo_url)

        for photo in all_photos[:10]:  # Meta aceita até 10 imagens por listing
            img_el = ET.SubElement(listing, "image")
            add_element(img_el, "url", photo)

        add_element(listing, "home_listing_id", codigo)
        add_element(listing, "availability", availability)
        add_element(listing, "listing_type", listing_type)
        add_element(listing, "property_type", property_type)
        add_element(listing, "url", listing_url)
        add_element(listing, "name", name)
        add_element(listing, "description", description)
        add_element(listing, "price", f"{price_value:.2f} BRL")

        # Endereço
        addr_el = ET.SubElement(listing, "address")
        addr_el.set("format", "simple")
        addr1_el = ET.SubElement(addr_el, "component")
        addr1_el.set("name", "addr1")
        addr1_el.text = addr1
        city_el = ET.SubElement(addr_el, "component")
        city_el.set("name", "city")
        city_el.text = cidade
        region_el = ET.SubElement(addr_el, "component")
        region_el.set("name", "region")
        region_el.text = uf
        postal_el = ET.SubElement(addr_el, "component")
        postal_el.set("name", "postal_code")
        postal_el.text = cep
        country_el = ET.SubElement(addr_el, "component")
        country_el.set("name", "country")
        country_el.text = "Brasil"

        add_element(listing, "neighborhood", cidade)
        add_element(listing, "num_beds", quartos)
        add_element(listing, "num_baths", num_baths)

        # Tags de produto (úteis para segmentação)
        add_element(listing, "product_tags", tipo_raw)
        add_element(listing, "product_tags", listing_type)
        if quartos > 0:
            add_element(listing, "product_tags", f"{quartos} quartos")

        converted += 1

    print(f"✅ Convertidos: {converted} imóveis | ⏭️  Ignorados: {skipped}")
    return listings_root


def pretty_print(element):
    """Retorna o XML formatado com indentação."""
    raw = ET.tostring(element, encoding="unicode")
    reparsed = minidom.parseString(raw)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def main():
    print(f"📥 Baixando XML da Vista: {VISTA_URL}")
    req = urllib.request.Request(VISTA_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        content = response.read()

    print("🔄 Convertendo para formato Meta Home Listings...")
    listings_root = convert(content)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    xml_output = pretty_print(listings_root)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_output)

    print(f"📄 Feed salvo em: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
