import asyncio
from pathlib import Path
from fastmcp import FastMCP
from tools import kpi_agregation, insights, dashboard_html

mcp_server = FastMCP("AFRIKA-DASHBOARD")

kpi_agregation.register_tools(mcp_server)   # Skill 2 : get_kpi_par_famille, get_kpi, get_produits_par_client
insights.register_tools(mcp_server)         # Skill 3 : generate_insights
dashboard_html.register_tools(mcp_server)   # Skills 4+5 : generate_dashboard_html


@mcp_server.resource("skills://dashboard-insights")
def skill_dashboard_insights() -> str:
    """Retourne le contenu du skill Dashboard InfoSoft pour un agent client."""
    return Path("skills-dashboard-infosoft.md").read_text(encoding="utf-8")


async def main():

    # Lancer le serveur (bloquant)
    await mcp_server.run_async(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000,
        path="/mcp",
    )

if __name__ == "__main__":
    asyncio.run(main())
