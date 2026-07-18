import asyncio
from pathlib import Path
from fastmcp import FastMCP
from tools import kpi_agregation, insights, dashboard_html
from dotenv import load_dotenv

load_dotenv()

mcp_server = FastMCP("AFRIKA-DASHBOARD")

kpi_agregation.register_tools(mcp_server)   
insights.register_tools(mcp_server)         
dashboard_html.register_tools(mcp_server)   

# Cette chaîne "skills://dashboard-insights" est le nom sous lequel la ressource est exposée aux clients MCP
@mcp_server.resource("skills://dashboard-insights")
def skill_dashboard_insights() -> str:
    """Retourne le contenu du skill Dashboard pour un agent client."""
    # Le contenu de la ressource est lu depuis le fichier "skills-dashboard.md" et renvoyé au client. La fonction retourne :
    return Path("skills-dashboard.md").read_text(encoding="utf-8")


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
