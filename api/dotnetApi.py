import pandas as pd
from pathlib import Path

async def get_ecom_commandes(date_debut: str = None, date_fin: str = None) -> list[dict]:
    """Retourne les lignes de commandes e-commerce brutes."""
   
    # 1. Trouver le dossier où se situe dotnetApi.py (le dossier 'api')
    CURRENT_DIR = Path(__file__).resolve().parent

    # 2. Remonter d'un cran à la racine, puis va dans 'csv'
    CSV_PATH = CURRENT_DIR.parent / "csv" / "afrimarket_dataset_clean.csv"

    # 3. Lecture du fichier
    data = pd.read_csv(CSV_PATH).to_dict(orient="records")
    
    # Filtrage par date basique
    if date_debut and date_fin:
        data = [d for d in data if date_debut <= d["date_commande"] <= date_fin]
        return data



