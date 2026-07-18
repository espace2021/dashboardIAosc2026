"""
Skill 3 - Generation d'Insights
Analyse un tableau de KPIs et produit :
- points_cles
- anomalies
- recommandations

Le prompt vit dans :
skills/skill-3-generation-insights.md

Prompt avec {{axe_analyse}}
"""

import json
import re
from pathlib import Path

from fastmcp import FastMCP

from services.gemini_service import call_gemini_json


SKILL_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "skill-3-generation-insights.md"
)


_DEFAULT_MODEL = "gemini-2.5-flash"
_DEFAULT_TEMPERATURE = 0.2



def _load_skill(path: Path) -> tuple[dict, str]:
    """
    Charge un skill Markdown avec frontmatter YAML.

    Retourne :
        config : dict
        body   : prompt
    """

    text = path.read_text(
        encoding="utf-8"
    )


    match = re.match(
        r"^---\s*\n(.*?)\n---\s*\n(.*)$",
        text,
        re.DOTALL
    )


    if not match:
        return {}, text


    front, body = match.groups()


    config = {}


    for line in front.splitlines():

        if ":" in line:

            key, _, value = line.partition(":")

            config[key.strip()] = value.strip()


    return config, body



def register_tools(mcp: FastMCP):


    @mcp.tool()
    async def generate_insights(
        kpi_table: list[dict],
        axe_analyse: str = "par famille d'articles"
    ) -> dict:
        """
        Génère une analyse intelligente des KPIs.

        Paramètres :
        - kpi_table : données KPI
        - axe_analyse : angle d'analyse
        """


        config, body = _load_skill(
            SKILL_PATH
        )


        model = config.get(
            "model",
            _DEFAULT_MODEL
        )


        temperature = float(
            config.get(
                "temperature",
                _DEFAULT_TEMPERATURE
            )
        )


        system_prompt = body.replace(
            "{{axe_analyse}}",
            axe_analyse
        )


        user_prompt = (
            "Voici les KPIs à analyser :\n"
            +
            json.dumps(
                kpi_table,
                ensure_ascii=False,
                indent=2
            )
        )


        prompt = f"""
{system_prompt}


{user_prompt}


Retourne uniquement un JSON valide :

{{
    "points_cles": [],
    "anomalies": [],
    "recommandations": []
}}
"""


        try:

            result = call_gemini_json(
                prompt,
                model=model,
                temperature=temperature
            )


            return result



        except Exception as exc:


            return {

                "points_cles": [],

                "anomalies": [
                    f"Analyse indisponible : {exc}"
                ],

                "recommandations": [
                    "Réessayer la génération du dashboard."
                ]
            }