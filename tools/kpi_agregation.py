import pandas as pd
from fastmcp import FastMCP
from api import dotnetApi  # Assurez-vous d'y avoir ajouté la fonction ci-dessus

def register_tools(mcp: FastMCP):

    @mcp.tool()
    async def get_kpi(dimension: str, date_debut: str, date_fin: str) -> list[dict]:
        """
        Calcule des KPIs agrégés (CA Net, % du CA, Coût Marketing, Quantité, Anomalies) 
        sur les nouvelles données e-commerce selon la dimension choisie :
        "categorie", "ville", "canal_marketing" ou "statut_commande".
        """
        valid_dimensions = {"categorie", "ville", "canal_marketing", "statut_commande"}
        if dimension not in valid_dimensions:
            raise ValueError(f"dimension doit être l'une des suivantes : {valid_dimensions}")

        commandes = await dotnetApi.get_ecom_commandes(date_debut, date_fin)
        if not commandes:
            return []

        df = pd.DataFrame(commandes)

        # Calcul du CA Net individuel : (Prix * Qte) * (1 - Remise)
        df["ca_net"] = (df["prix_unitaire"] * df["quantite"]) * (1 - df["remise"].fillna(0))
        df["cout_marketing"] = df["cout_marketing"].fillna(0)
        df["quantite"] = df["quantite"].fillna(0)
        
        # Renommer la dimension cible pour l'agrégation
        df["label"] = df[dimension].fillna("Inconnu")

        # Agrégation par groupe
        grouped = df.groupby("label").agg(
            ca_net=("ca_net", "sum"),
            quantite_vendue=("quantite", "sum"),
            cout_marketing=("cout_marketing", "sum"),
            nb_anomalies=("anomalie", lambda x: x.ne("").sum())
        ).reset_index()

        # Calcul des pourcentages de CA
        total_ca = grouped["ca_net"].sum()
        grouped["pct_ca"] = (((grouped["ca_net"] / total_ca) * 100) if total_ca > 0 else 0).round(1)
        
        # Arrondis financiers
        grouped["ca_net"] = grouped["ca_net"].round(2)
        grouped["cout_marketing"] = grouped["cout_marketing"].round(2)

        # Tri par CA Net décroissant
        grouped = grouped.sort_values(by="ca_net", ascending=False)

        return grouped.head(15).to_dict(orient="records")

    @mcp.tool()
    async def get_produits_par_client(date_debut: str, date_fin: str, code_client: str | None = None) -> list[dict]:
        """
        Détaille les produits achetés par client avec le CA Net et la quantité.
        """
        commandes = await dotnetApi.get_ecom_commandes(date_debut, date_fin)
        if not commandes:
            return []

        df = pd.DataFrame(commandes)
        if code_client:
            df = df[df["id_client"] == code_client]
            if df.empty:
                return []

        df["ca_net"] = (df["prix_unitaire"] * df["quantite"]) * (1 - df["remise"].fillna(0))

        grouped = df.groupby(["id_client", "nom_produit"]).agg(
            ca_net=("ca_net", "sum"),
            quantite=("quantite", "sum")
        ).reset_index()

        grouped["ca_net"] = grouped["ca_net"].round(2)
        grouped = grouped.rename(columns={"id_client": "client", "nom_produit": "produit"})
        
        return grouped.sort_values(by="ca_net", ascending=False).head(30).to_dict(orient="records")
