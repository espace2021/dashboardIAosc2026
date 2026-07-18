from fastmcp import FastMCP
from api.dotnetApi import api_get, api_post

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

    @mcp.tool()
    async def get_ca_client(code_client: str, date_debut: str = "2000-01-01", date_fin: str = "2024-12-31") -> dict:
        """Calcule le chiffre d'affaires, encaissements et solde d'un client."""
        try:
            data = await api_post("/relever_client", {
                "codeClient": code_client,
                "tT_Inclure_BL_BA_BR": True,
                "tT_Periode": False,
                "dateDebut": date_debut,
                "dateFin": date_fin
            })
            if not data.get("isSuccess"):
                return {"error": data.get("error")}

            lignes = data["value"]
            ca_total = sum(l["rC_Debit"] for l in lignes)
            encaisse = sum(l["rC_Credit"] for l in lignes)
            solde_final = lignes[-1]["rC_Solde"] if lignes else 0
            impayes = [l for l in lignes if l["rC_EtatPiece"] == "Non Règlé"]

            return {
                "client": lignes[0]["rC_IntituleClient"] if lignes else code_client,
                "ca_total": round(ca_total, 3),
                "encaisse": round(encaisse, 3),
                "solde": round(solde_final, 3),
                "taux_recouvrement": round(encaisse / ca_total * 100, 1) if ca_total else 0,
                "nb_impayes": len(impayes),
                "montant_impaye": round(sum(l["rC_Solde"] for l in impayes), 3)
            }
        except Exception as err:
            return {"ok": False, "message": "API .NET error", "error": _extraire_erreur(err)}

    @mcp.tool()
    async def get_releve_client(code_client: str, date_debut: str = "2000-01-01", date_fin: str = "2024-12-31") -> list[dict]:
        """Retourne le relevé brut d'un client (factures, règlements, soldes)."""
        data = await api_post("/relever_client", {
            "codeClient": code_client,
            "tT_Inclure_BL_BA_BR": True,
            "tT_Periode": False,
            "dateDebut": date_debut,
            "dateFin": date_fin
        })
        if not data.get("isSuccess"):
            return {"error": data.get("error")}

        lignes = data["value"]
        return [
            {
                "piece": l.get("rC_Piece"), "type": l.get("rC_TypePiece"),
                "date": l.get("rC_Date"), "intitule": l.get("rC_Intitule"),
                "debit": l.get("rC_Debit", 0), "credit": l.get("rC_Credit", 0),
                "solde": l.get("rC_Solde", 0), "etat": l.get("rC_EtatPiece"),
                "echeance": l.get("rC_Echeance"),
            }
            for l in lignes
        ]