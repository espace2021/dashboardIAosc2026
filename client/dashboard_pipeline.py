"""
dashboard_pipeline.py (version Gemini)
Logique partagée par web_dashboard.py et prompt_to_dashboard.py :
1) interprète une demande en langage naturel pour en extraire une période de dates
   (Skill 0 - Interprétation de la demande, via Gemini)
2) exécute la chaîne de tools MCP existante :
       get_kpi_par_famille -> generate_insights -> generate_dashboard_html

Prérequis : le serveur MCP doit déjà tourner (uv run server.py).
"""
import os
import json
import time
import datetime as dt
from pathlib import Path

from fastmcp import Client
from google import genai
from dotenv import load_dotenv

load_dotenv()  # script client - jamais couvert par le load_dotenv() de api/dotnetApi.py

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"   # doit correspondre à server.py
MODEL = "gemini-2.5-flash"

SKILL_0_PATH = Path(__file__).parent.parent / "skills" / "skill-0-interpretation-demande.md"


def _call_gemini_with_retry(fn, *args, max_retries=4, base_delay=3, **kwargs):
    """Réessaie automatiquement en cas d'indisponibilité temporaire de l'API Gemini."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            transient = any(s in str(exc) for s in ("503", "UNAVAILABLE", "overloaded", "429", "rate_limit"))
            if not transient or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"   (Gemini temporairement surchargé, nouvel essai dans {delay}s...)")
            time.sleep(delay)


def extract_dates_from_prompt(prompt: str) -> dict:
    """Utilise Gemini (skill skill-0-interpretation-demande.md) pour transformer une demande en {date_debut, date_fin}."""
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    system_prompt = SKILL_0_PATH.read_text(encoding="utf-8")
    aujourdhui = dt.date.today().isoformat()
    user_message = f'Nous sommes aujourd\'hui le {aujourdhui}.\n\nDemande : "{prompt}"'

    response = _call_gemini_with_retry(
        client.models.generate_content,
        model=MODEL,
        contents=f"{system_prompt}\n\n{user_message}",
        config={"temperature": 0, "response_mime_type": "application/json"},
    )
    return json.loads(response.text)


def _extract_tool_result(result):
    """
    Récupère la donnée renvoyée par un tool MCP, quelle que soit la forme
    exacte du résultat selon la version de fastmcp.
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


async def build_dashboard_from_dates(date_debut: str, date_fin: str) -> str | None:
    """Exécute get_kpi_par_famille -> generate_insights -> generate_dashboard_html. None si aucune donnée."""
    async with Client(MCP_SERVER_URL) as client:
        kpi_result = await client.call_tool(
            "get_kpi_par_famille", {"date_debut": date_debut, "date_fin": date_fin}
        )
        kpi_table = _extract_tool_result(kpi_result)

        if not kpi_table:
            return None

        insights_result = await client.call_tool("generate_insights", {"kpi_table": kpi_table})
        insights = _extract_tool_result(insights_result)

        html_result = await client.call_tool(
            "generate_dashboard_html",
            {
                "title": f"Dashboard InfoSoft — CA par famille ({date_debut} au {date_fin})",
                "kpi_table": kpi_table,
                "insights": insights,
            },
        )
        return _extract_tool_result(html_result)


async def build_dashboard_from_prompt(prompt: str) -> tuple[str | None, dict]:
    """
    Pipeline complet : prompt -> dates -> dashboard HTML.
    Retourne (html_ou_None, dates_utilisees) pour que l'appelant puisse toujours
    afficher la période interprétée, même quand le dashboard est vide.
    """
    dates = extract_dates_from_prompt(prompt)
    html = await build_dashboard_from_dates(dates["date_debut"], dates["date_fin"])
    return html, dates