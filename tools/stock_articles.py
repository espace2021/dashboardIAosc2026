"""
stock_articles.py
------------------
Définit les tools MCP en s'appuyant directement sur dotnetApi.py
(api_get / api_post), sans couche intermédiaire.

Ce que stockarticle apporte de nouveau :
aS_QteSto  → stock disponible
aS_QteCom  → quantité en commande (déjà réservée)
aR_Ref     → lien avec articles (aR_Ref)
dE_Intitule→ dépôt / entrepôt
aS_Principal → stock principal ou secondaire

Stock réel disponible = aS_QteSto - aS_QteCom
"""
from fastmcp import FastMCP
from api.dotnetApi import api_get

stock_mcp = FastMCP("Sage100C")


async def _fetch_stock() -> list[dict]:
    """Récupère la liste complète des stocks articles via l'API .NET (async)."""
    data = await api_get("/stocks_articles")
    if isinstance(data, dict):
        return data.get("value", [])
    return data  # au cas où l'endpoint renvoie directement une liste


def register_tools(mcp: FastMCP):
    """Enregistre les outils de manipulation des stocks dans le MCP."""

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
    async def get_stock_article(ar_ref: str) -> dict:
        """
        Retourne le stock d'un article par sa référence.
        Inclut stock dispo, en commande et dépôt.
        """
        try:
            stocks = await _fetch_stock()
            result = [s for s in stocks if s["aR_Ref"] == ar_ref]
            if not result:
                return {"error": f"Article {ar_ref} introuvable"}

            principal = next((s for s in result if s["aS_Principal"]), result[0])
            return {
                "ref": ar_ref,
                "depot": principal["dE_Intitule"],
                "qte_stock": principal["aS_QteSto"],
                "qte_commande": principal["aS_QteCom"],
                "qte_dispo": principal["aS_QteSto"] - principal["aS_QteCom"],
            }
        except Exception as err:
            return {"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}

    # ── Tool 2 ──────────────────────────────────────────────
    @mcp.tool()
    async def get_articles_rupture(seuil: float = 0) -> list[dict]:
        """
        Retourne les articles en rupture ou sous un seuil de stock disponible.
        Stock dispo = aS_QteSto - aS_QteCom
        """
        try:
            stocks = await _fetch_stock()
            ruptures = []
            for s in stocks:
                if not s["aS_Principal"]:
                    continue
                dispo = s["aS_QteSto"] - s["aS_QteCom"]
                if dispo <= seuil:
                    ruptures.append({
                        "ref": s["aR_Ref"],
                        "depot": s["dE_Intitule"],
                        "qte_dispo": round(dispo, 3),
                        "en_commande": s["aS_QteCom"],
                    })
            return sorted(ruptures, key=lambda x: x["qte_dispo"])
        except Exception as err:
            return [{"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}]

    # ── Tool 3 ──────────────────────────────────────────────
    @mcp.tool()
    async def get_stock_par_depot(depot: str) -> list[dict]:
        """
        Retourne tous les articles d'un dépôt donné avec leur stock.
        """
        try:
            stocks = await _fetch_stock()
            return [
                {
                    "ref": s["aR_Ref"],
                    "qte_stock": s["aS_QteSto"],
                    "qte_dispo": s["aS_QteSto"] - s["aS_QteCom"],
                }
                for s in stocks
                if s["dE_Intitule"].lower() == depot.lower()
            ]
        except Exception as err:
            return [{"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}]

    # ── Tool 4 ──────────────────────────────────────────────
    @mcp.tool()
    async def get_articles_surstock(seuil: float = 1000) -> list[dict]:
        """
        Retourne les articles dont le stock dépasse un seuil (surstock).
        """
        try:
            stocks = await _fetch_stock()
            return [
                {
                    "ref": s["aR_Ref"],
                    "depot": s["dE_Intitule"],
                    "qte_stock": s["aS_QteSto"],
                }
                for s in stocks
                if s["aS_Principal"] and s["aS_QteSto"] > seuil
            ]
        except Exception as err:
            return [{"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}]


# =========================================================
# AFFICHAGE DES TOOLS
# =========================================================
tools = [
    "get_stock_article",
    "get_articles_rupture",
    "get_stock_par_depot",
    "get_articles_surstock"
]

print("\n📌 Tools enregistrés stocks articles :")
for tool_name in tools:
    print(f" • {tool_name}")