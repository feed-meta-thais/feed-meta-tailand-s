# Feed automático Meta - Thais Imobiliária

Este projeto baixa diariamente o XML original da Vista/Loft, converte para XML RSS compatível com catálogo do Meta e publica o arquivo em `docs/feed-meta.xml` via GitHub Pages.

## Como publicar grátis no GitHub

1. Crie um repositório no GitHub, por exemplo: `feed-meta-thais`.
2. Faça upload destes arquivos mantendo a estrutura de pastas:
   - `.github/workflows/update-feed.yml`
   - `scripts/convert_vista_to_meta.py`
   - `docs/index.html`
3. No GitHub, vá em **Settings > Pages**.
4. Em **Build and deployment**, selecione:
   - Source: **Deploy from a branch**
   - Branch: **main**
   - Folder: **/docs**
5. Salve.
6. Vá em **Actions > Atualizar feed Meta > Run workflow** para rodar manualmente a primeira vez.
7. Depois disso, o arquivo será atualizado automaticamente todos os dias às 23h00, horário de Brasília.

## URL final esperada

Depois de ativar o GitHub Pages, a URL ficará parecida com:

`https://SEU_USUARIO.github.io/feed-meta-thais/feed-meta.xml`

Essa é a URL que deve ser cadastrada no Meta Commerce Manager.

## URL do imóvel

O script monta automaticamente URLs no padrão real do site, por exemplo:

`https://thaisimobiliaria.com.br/imovel/casa-guara-ii-guara-df-4-quartos-129m2-TH35309`

Ele usa o código do imóvel, tipo, cidade, UF, quartos, metragem e uma tentativa de bairro/região extraída do texto do anúncio.

## Rodar localmente

```bash
python scripts/convert_vista_to_meta.py
```

O arquivo será gerado em:

`docs/feed-meta.xml`
