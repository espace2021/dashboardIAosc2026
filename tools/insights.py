"""
Skill 3 - Generation d'Insights (version Gemini, skill paramétré)
Analyse un tableau de KPIs et produit points_cles / anomalies / recommandations.

Le prompt vit dans skills/skill-3-generation-insights.md, sous deux formes :
- un en-tête YAML (---...---) pour la configuration (model, temperature)
- un corps avec un placeholder {{axe_analyse}}, rempli dynamiquement selon
  l'axe réellement analysé (famille, client, produit...).
"""
import os
import json
import re
import time
from pathlib import Path
from google import genai
from fastmcp import FastMCP

SKILL_PATH = Path(__file__).parent.parent / "skills" / "skill-3-generation-insights.md"

# Valeurs de repli si l'en-tête YAML du skill ne précise pas model/temperature.
_DEFAULT_MODEL = "gemini-2.5-flash"
_DEFAULT_TEMPERATURE = 0.2


def _load_skill(path: Path) -> tuple[dict, str]:
    """
    Charge un skill .md avec un en-tête YAML optionnel :
        ---
        cle: valeur
        ---
        <corps du prompt>
    Retourne (config: dict, corps: str). Si aucun en-tête n'est présent,
    retourne un dict vide et le fichier entier comme corps.
    """
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    front, body = match.groups()
    config = {}
    for line in front.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            config[key.strip()] = value.strip()
    return config, body


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


def register_tools(mcp: FastMCP):

    @mcp.tool()
    async def generate_insights(kpi_table: list[dict], axe_analyse: str = "par famille d'articles") -> dict:
        """
        Génère une analyse structurée (points_cles, anomalies, recommandations)
        à partir d'un tableau de KPIs. `axe_analyse` décrit l'angle du tableau
        (ex. "par famille d'articles", "par client", "par produit et par client")
        et est injecté dans le prompt pour adapter le vocabulaire de l'analyse.
        En cas d'indisponibilité prolongée de Gemini, retourne un résultat de
        repli plutôt que de faire échouer tout le dashboard.
        """
        config, body = _load_skill(SKILL_PATH)
        model = config.get("model", _DEFAULT_MODEL)
        temperature = float(config.get("temperature", _DEFAULT_TEMPERATURE))

        system_prompt = body.replace("{{axe_analyse}}", axe_analyse)
        user_prompt = f"Voici les KPIs à analyser : {json.dumps(kpi_table, ensure_ascii=False)}"

        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

        try:
            response = _call_gemini_with_retry(
                client.models.generate_content,
                model=model,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config={"temperature": temperature, "response_mime_type": "application/json"},
            )
            return json.loads(response.text)
        except Exception as exc:
            return {
                "points_cles": [],
                "anomalies": [f"Analyse indisponible : le service Gemini est temporairement surchargé ({exc})."],
                "recommandations": ["Réessayer la génération du dashboard dans quelques minutes."],
            }