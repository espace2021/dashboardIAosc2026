"""
client_test_dashboard.py
Script de test : appelle en séquence les 3 tools MCP du dashboard décisionnel
    get_kpi_par_famille -> generate_insights -> generate_dashboard_html
et sauvegarde le dashboard HTML final, puis l'ouvre dans le navigateur.

Prérequis : le serveur doit déjà tourner dans un autre terminal :
    uv run server.py

Usage :
    uv run client_test_dashboard.py
"""
import asyncio
import json
import webbrowser
from pathlib import Path

from fastmcp import Client

SERVER_URL = "http://127.0.0.1:8000/mcp"   # doit correspondre à host/port/path de server.py
OUTPUT_HTML = Path("dashboard_infosoft.html")

# Période de test courte (adapter à des dates où vous savez qu'il existe des factures)
DATE_DEBUT = "2024-07-01"
DATE_FIN = "2024-07-31"


def _extract(result):
    """
    Récupère la donnée renvoyée par un tool MCP, quelle que soit la forme
    exacte du résultat selon la version de fastmcp :
    - `result.data`               -> donnée déjà structurée (dict/list/str)
    - `result.structured_content` -> repli si `.data` est absent
    - `result.content[0].text`    -> repli texte brut ; on tente un JSON,
                                      sinon on renvoie le texte tel quel (cas du HTML)
    """
    if getattr(result, "data", None) is not None:
        return result.data
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


async def main():
    async with Client(SERVER_URL) as client:

        # 1) Skill 2 - Agrégation KPI
        print(f"1) get_kpi_par_famille(date_debut={DATE_DEBUT!r}, date_fin={DATE_FIN!r})...")
        kpi_result = await client.call_tool(
            "get_kpi_par_famille",
            {"date_debut": DATE_DEBUT, "date_fin": DATE_FIN},
        )
        kpi_table = _extract(kpi_result)

        if not kpi_table:
            print("   -> kpi_table est vide.")
            print("      Vérifiez qu'il existe des factures (types 6/7) sur cette "
                  "période dans Sage, puis relancez avec d'autres dates.")
            return

        print(f"   -> {len(kpi_table)} famille(s) trouvée(s) :")
        for row in kpi_table:
            print(f"      {row}")

        # 2) Skill 3 - Génération d'Insights
        print("\n2) generate_insights(kpi_table=...)...")
        insights_result = await client.call_tool(
            "generate_insights",
            {"kpi_table": kpi_table},
        )
        insights = _extract(insights_result)

        print("   -> points_cles :")
        for p in insights.get("points_cles", []):
            print(f"      - {p}")
        print("   -> anomalies :")
        for a in insights.get("anomalies", []):
            print(f"      - {a}")
        print("   -> recommandations :")
        for r in insights.get("recommandations", []):
            print(f"      - {r}")

        # 3) Skills 4+5 - Dashboard HTML
        print("\n3) generate_dashboard_html(kpi_table=..., insights=...)...")
        html_result = await client.call_tool(
            "generate_dashboard_html",
            {
                "title": f"Dashboard InfoSoft — CA par famille ({DATE_DEBUT} au {DATE_FIN})",
                "kpi_table": kpi_table,
                "insights": insights,
            },
        )
        html = _extract(html_result)

        OUTPUT_HTML.write_text(html, encoding="utf-8")
        print(f"   -> Dashboard sauvegardé : {OUTPUT_HTML.resolve()}")

        webbrowser.open(OUTPUT_HTML.resolve().as_uri())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"\n❌ Erreur pendant le test : {exc}")