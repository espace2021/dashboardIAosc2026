"""
art_clients.py
------------------
Définit les tools MCP en s'appuyant directement sur dotnetApi.py
(api_get / api_post), sans couche intermédiaire.
"""
from fastmcp import FastMCP
from api.dotnetApi import api_get

stock_mcp = FastMCP("Sage100C")


async def _fetch_articles_clients(code: str) -> list[dict]:
    """Récupère les articles liés à un client donné via l'API .NET (async)."""
    data = await api_get("/articles_client", params={"codeClient": code})
    if isinstance(data, dict):
        return data.get("value", [])
    return data  # au cas où l'endpoint renvoie directement une liste


def register_tools(mcp: FastMCP):
    """Enregistre les outils de manipulation des articles clients dans le MCP."""

    def _extraire_erreur(err):
        reponse = getattr(err, "response", None)
        if reponse is not None:
            try:
                return reponse.json()
            except ValueError:
                return reponse.text
        return str(err)

    # ── Tool 1 ──────────────────────────────────────────────
    @mcp.tool()
    async def get_client_articles(code_client: str):
        """
        Retourne les articles_clients d'un client par sa référence.
        Inclut articles_clients dispo, en commande et dépôt.
        """
        try:
            articles = await _fetch_articles_clients(code_client)
            if not articles:
                return {"error": f"Article {code_client} introuvable"}
            return articles
        except Exception as err:
            return {"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}


# =========================================================
# AFFICHAGE DES TOOLS
# =========================================================
tools = [
    "get_client_articles"
]

print("\n📌 Tools enregistrés articles clients :")
for tool_name in tools:
    print(f" • {tool_name}")