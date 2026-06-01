name: Atualizar feed Meta

on:
  workflow_dispatch:
  schedule:
    # Roda às 22:00 UTC = 19:00 horário de Brasília (1h após atualização da equipe às 18h)
    - cron: "00 22 * * *"

permissions:
  contents: write

jobs:
  update-feed:
    runs-on: ubuntu-latest

    steps:
      - name: Baixar repositório
        uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Converter XML Vista para XML Meta
        run: python scripts/convert_vista_to_meta.py

      - name: Commitar feed atualizado
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: atualiza feed Meta Home Listings [auto]"
          file_pattern: "docs/feed-meta.xml"
