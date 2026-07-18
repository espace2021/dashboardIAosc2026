"""
dashboard_pipeline.py

Pipeline partagé par :
- web_dashboard.py
- prompt_to_dashboard.py

Flux :

1) Prompt utilisateur
        |
        |
   Skill 0 - interprétation demande
        |
        |
   Extraction dates JSON
        |
        |
2) Tools MCP :
        |
        +--> get_kpi_par_famille
        |
        +--> generate_insights
        |
        +--> generate_dashboard_html


Gemini est appelé via :
services/gemini_service.py
(ChatGoogleGenerativeAI)
"""


import json
import datetime as dt

from pathlib import Path

from fastmcp import Client

from services.gemini_service import call_gemini_json

from dotenv import load_dotenv


load_dotenv()



MCP_SERVER_URL = (
    "http://127.0.0.1:8000/mcp"
)


SKILL_0_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "skill-0-interpretation-demande.md"
)



# ==================================================
# Skill 0 : interprétation de la demande utilisateur
# ==================================================


def extract_dates_from_prompt(
        prompt: str
) -> dict:
    """
    Transforme une demande naturelle en :

    {
       "date_debut": "2024-07-01",
       "date_fin": "2024-07-31"
    }

    grâce au Skill 0.
    """


    system_prompt = SKILL_0_PATH.read_text(
        encoding="utf-8"
    )


    aujourd_hui = dt.date.today().isoformat()


    user_message = f"""
Nous sommes aujourd'hui le {aujourd_hui}.


Demande utilisateur :

{prompt}
"""


    full_prompt = f"""

{system_prompt}


{user_message}


Retourne uniquement un JSON valide :

{{
 "date_debut": "YYYY-MM-DD",
 "date_fin": "YYYY-MM-DD"
}}

"""


    return call_gemini_json(
        full_prompt,
        model="gemini-2.5-flash",
        temperature=0
    )



# ==================================================
# Extraction résultat MCP
# ==================================================


def _extract_tool_result(result):


    if getattr(
        result,
        "data",
        None
    ) is not None:

        return result.data



    if getattr(
        result,
        "structured_content",
        None
    ) is not None:

        return result.structured_content



    text = result.content[0].text


    try:

        return json.loads(text)


    except (
        json.JSONDecodeError,
        TypeError
    ):

        return text




# ==================================================
# Construction Dashboard
# ==================================================


async def build_dashboard_from_dates(
        date_debut: str,
        date_fin: str
) -> str | None:

    """
    Pipeline MCP :

    get_kpi_par_famille
          |
    generate_insights
          |
    generate_dashboard_html
    """


    async with Client(
        MCP_SERVER_URL
    ) as client:



        # -------------------------------
        # 1 - Récupération KPI
        # -------------------------------

        kpi_result = await client.call_tool(
            "get_kpi_par_famille",
            {
                "date_debut": date_debut,
                "date_fin": date_fin
            }
        )


        kpi_table = _extract_tool_result(
            kpi_result
        )


        if not kpi_table:

            return None



        # -------------------------------
        # 2 - Analyse KPI
        # -------------------------------

        insights_result = await client.call_tool(
            "generate_insights",
            {
                "kpi_table": kpi_table,
                "axe_analyse": "par famille d'articles"
            }
        )


        insights = _extract_tool_result(
            insights_result
        )



        # -------------------------------
        # 3 - Génération HTML
        # -------------------------------

        html_result = await client.call_tool(
            "generate_dashboard_html",
            {

                "title":
                (
                    "Dashboard CA par famille "
                    f"({date_debut} au {date_fin})"
                ),


                "kpi_table":
                kpi_table,


                "insights":
                insights

            }
        )


        return _extract_tool_result(
            html_result
        )





# ==================================================
# Pipeline complet
# ==================================================


async def build_dashboard_from_prompt(
        prompt: str
) -> tuple[str | None, dict]:

    """
    Prompt utilisateur :

    "donne-moi le CA de juillet 2024"

    devient :

    {
       date_debut,
       date_fin
    }


    puis génère le dashboard.
    """


    dates = extract_dates_from_prompt(
        prompt
    )


    html = await build_dashboard_from_dates(
        dates["date_debut"],
        dates["date_fin"]
    )


    return html, dates