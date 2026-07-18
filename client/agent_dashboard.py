"""
agent_dashboard.py (version Gemini)
Agent générique (pattern ReAct) : à partir de N'IMPORTE QUELLE demande en langage
naturel, décide lui-même quels tools MCP appeler (parmi TOUS ceux exposés par le
serveur), dans quel ordre, et produit un dashboard HTML adapté à la demande.

Utilise Gemini (function calling natif) - le format des tools et de la boucle de
conversation diffère de la version Groq/OpenAI : Content/Part + function_call,
au lieu de messages (system/user/assistant/tool) + tool_calls.

Prérequis : le serveur MCP doit déjà tourner dans un autre terminal :
    uv run server.py

Usage :
    uv run agent_dashboard.py "les produits achetés par chaque client en juillet 2024"
    uv run agent_dashboard.py "le CA par famille du mois dernier"
    uv run agent_dashboard.py            (mode interactif)
"""
import asyncio
import datetime as dt
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

from fastmcp import Client
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()  # script client - jamais couvert par le load_dotenv() de api/myApi.py

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"   # doit correspondre à server.py
MODEL = "gemini-2.5-flash"
OUTPUT_HTML = Path("dashboard_africa.html")
MAX_STEPS = 8   # garde-fou contre une boucle infinie de l'agent

SKILL_PATH = Path(__file__).parent.parent / "skills" / "skill-orchestrateur-agent.md"

# Mots-clés JSON Schema générés par FastMCP/Pydantic mais non supportés par le
# schéma de paramètres de l'API Gemini (function calling) - à retirer récursivement.
# ATTENTION : ne PAS inclure "title" ici - certains tools ont un paramètre qui
# s'appelle littéralement "title" (generate_dashboard_html) ; un strip aveugle par
# nom de clé supprimerait la définition de ce paramètre lui-même.
_UNSUPPORTED_SCHEMA_KEYS = {"additionalProperties", "$schema"}


def _clean_schema(node):
    if isinstance(node, dict):
        return {k: _clean_schema(v) for k, v in node.items() if k not in _UNSUPPORTED_SCHEMA_KEYS}
    if isinstance(node, list):
        return [_clean_schema(v) for v in node]
    return node


def _mcp_tool_to_gemini(tool) -> types.FunctionDeclaration:
    raw_schema = tool.inputSchema or {"type": "object", "properties": {}}
    schema = _clean_schema(raw_schema)
    return types.FunctionDeclaration(
        name=tool.name,
        description=tool.description or "",
        parameters=schema,
    )


def _tool_result_to_value(result):
    """Récupère la donnée renvoyée par un tool MCP, quelle que soit la forme du résultat."""
    if getattr(result, "data", None) is not None:
        return result.data
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _call_gemini_with_retry(fn, *args, max_retries=4, base_delay=3, **kwargs):
    """
    Réessaie automatiquement en cas d'indisponibilité temporaire de l'API Gemini
    (503 UNAVAILABLE, surcharge du modèle). Backoff exponentiel : 3s, 6s, 12s, 24s.
    """
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


async def run_agent(prompt: str) -> str:
    """Boucle ReAct : interroge Gemini, exécute les tools demandés, jusqu'au dashboard final."""
    async with Client(MCP_SERVER_URL) as mcp_client:
        mcp_tools = await mcp_client.list_tools()
        gemini_tool = types.Tool(function_declarations=[_mcp_tool_to_gemini(t) for t in mcp_tools])

        genai_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        system_instruction = SKILL_PATH.read_text(encoding="utf-8")
        aujourdhui = dt.date.today().isoformat()

        contents = [types.Content(
            role="user",
            parts=[types.Part(text=f"Nous sommes aujourd'hui le {aujourdhui}.\n\n{prompt}")],
        )]

        for step in range(MAX_STEPS):
            response = _call_gemini_with_retry(
                genai_client.models.generate_content,
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[gemini_tool],
                    temperature=0,
                ),
            )
            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [
                part.function_call for part in candidate.content.parts if part.function_call
            ]

            if not function_calls:
                # L'agent a répondu en texte au lieu d'appeler un tool -> on s'arrête là.
                return response.text or "(L'agent n'a produit aucun dashboard.)"

            for fc in function_calls:
                args = dict(fc.args) if fc.args else {}
                print(f"   [étape {step + 1}] {fc.name}({args})")

                try:
                    tool_result = await mcp_client.call_tool(fc.name, args)
                    value = _tool_result_to_value(tool_result)
                except Exception as exc:
                    value = {"error": str(exc)}
                    print(f"      -> erreur : {exc}")

                if fc.name == "generate_dashboard_html" and isinstance(value, str):
                    return value  # tool terminal : on retourne directement le HTML généré

                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(name=fc.name, response={"result": value})],
                ))

        return "(Nombre maximal d'étapes atteint sans dashboard final. Reformulez ou simplifiez la demande.)"


async def main(prompt: str):
    print(f"Prompt : {prompt!r}\n")
    result = await run_agent(prompt)

    if not result.strip().startswith("<!DOCTYPE") and not result.strip().startswith("<html"):
        print(result)
        return

    OUTPUT_HTML.write_text(result, encoding="utf-8")
    print(f"\nDashboard sauvegardé : {OUTPUT_HTML.resolve()}")
    webbrowser.open(OUTPUT_HTML.resolve().as_uri())


if __name__ == "__main__":
    user_prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Décrivez le dashboard voulu : ").strip()
    try:
        asyncio.run(main(user_prompt))
    except Exception as exc:
        print(f"\n❌ Erreur : {exc}")