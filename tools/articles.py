from fastmcp import FastMCP
from api.dotnetApi import api_get

mcp = FastMCP("Sage100C")

def register_tools(mcp: FastMCP):
    def _extraire_erreur(err):
        reponse = getattr(err, "response", None)
        if reponse is not None:
            try:
                return reponse.json()
            except ValueError:
                return reponse.text
        return str(err)

    # TOOL 1 : sage_get_article_by_id
    @mcp.tool(name="sage_getArticleByID", description="Récupérer un article par code depuis l'API .NET")
    async def sage_get_article_by_id(code_article: str) -> dict:
        try:
            data = await api_get("/article", params={"aR_Ref": code_article})
            return {"ok": True, "data": data}
        except Exception as err:
            return {"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}

    # TOOL 2 : sage_filter_articles_by_price_range
    @mcp.tool(
        name="sage_filterArticlesByPriceRange",
        description="Filtre les articles selon une plage de prix de vente (aR_PrixVen)."
    )
    async def sage_filter_articles_by_price_range(prix_min: float = None, prix_max: float = None) -> dict:
        try:
            data = await api_get("/articles")
            articles = data if isinstance(data, list) else data.get("data", data)

            def prix_valide(article):
                prix = article.get("aR_PrixVen")
                if prix is None:
                    return False
                try:
                    prix = float(prix)
                except (TypeError, ValueError):
                    return False
                if prix_min is not None and prix < prix_min:
                    return False
                if prix_max is not None and prix > prix_max:
                    return False
                return True

            articles_filtres = [a for a in articles if prix_valide(a)]
            return {
                "ok": True, "count": len(articles_filtres),
                "prix_min": prix_min, "prix_max": prix_max,
                "data": articles_filtres
            }
        except Exception as err:
            return {"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}

    # TOOL 3 : sage_search_articles
    @mcp.tool(
        name="sage_search_articles",
        description="Recherche des produits par mot-clé dans le design, la description ou la référence."
    )
    async def sage_search_articles(query: str) -> dict:
        try:
            data = await api_get("/articles")
            articles = data if isinstance(data, list) else data.get("data", data)
            query_lower = query.lower()

            def correspond(article):
                design = (article.get("aR_Design") or "").lower()
                description = (article.get("aR_Description") or "").lower()
                short_desc = (article.get("aR_ShortDescription") or "").lower()
                ref = (article.get("aR_Ref") or "").lower()
                return query_lower in design or query_lower in description or query_lower in short_desc or query_lower in ref

            resultats = [a for a in articles if correspond(a)]
            return {"ok": True, "query": query, "count": len(resultats), "data": resultats}
        except Exception as err:
            return {"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}
# =========================================================

# AFFICHAGE DES TOOLS

# =========================================================

tools = [

        "sage_get_article_by_id",
        "sage_filter_articles_by_price_range",
        "sage_search_articles"
    ]

print("\n📌 Tools enregistrés d'articles :")

