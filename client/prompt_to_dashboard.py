"""
prompt_to_dashboard.py
Génère un dashboard décisionnel à partir d'une simple demande en langage naturel.

Prérequis : le serveur MCP doit déjà tourner dans un autre terminal :
    uv run server.py

Usage :
    uv run prompt_to_dashboard.py "Montre-moi le dashboard des ventes de juillet 2024"
    uv run prompt_to_dashboard.py            (demande le prompt de façon interactive)
"""
import asyncio
import sys
import webbrowser
from pathlib import Path

from dashboard_pipeline import build_dashboard_from_prompt

OUTPUT_HTML = Path("dashboard_africa.html")


async def main(prompt: str):
    print(f"Prompt : {prompt!r}")

    html, dates = await build_dashboard_from_prompt(prompt)
    print(f"Période interprétée : {dates['date_debut']} -> {dates['date_fin']}")

    if html is None:
        print("Aucune facture trouvée sur cette période. Essayez une autre formulation ou une autre période.")
        return

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"Dashboard sauvegardé : {OUTPUT_HTML.resolve()}")
    webbrowser.open(OUTPUT_HTML.resolve().as_uri())


if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])
    else:
        user_prompt = input("Décrivez le dashboard que vous voulez : ").strip()

    try:
        asyncio.run(main(user_prompt))
    except Exception as exc:
        print(f"\n❌ Erreur : {exc}")