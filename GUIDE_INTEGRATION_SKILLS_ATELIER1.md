# Guide pratique — Intégrer le skill « Dashboard Décisionnel » dans Atelier 1 (Jewelry MCP)

Ce guide part de votre projet `atelier1` (serveur FastMCP « Jewelry MCP », tools `articles`, `relv_clients`, `stock_articles`, `art_clients`) et ajoute les skills nécessaires pour exposer un dashboard décisionnel (KPIs + insights), **en s'appuyant sur les vrais endpoints documentés de l'API Sage 100 (InfoSoft)**.

---

## 0. Rappel de l'architecture cible

```
Sage 100 Commerciale (API InfoSoft, doc. fournie)
        │  GET /api/v1/articles, /api/v1/catalogues
        │  POST /api/v1/documents_facturation, GET /api/v1/lignes_document
        ▼
api/dotnetApi.py                        (couche HTTP — existant, complété avec les endpoints Sage)
        │
        ▼
tools/kpi_agregation.py                   (Skill 2 — NOUVEAU, pandas)
        │
        ▼
tools/insights.py                         (Skill 3 — NOUVEAU, Gemini)
        │
        ▼
tools/dashboard_html.py                   (Skills 4+5 — NOUVEAU, bonus interactif)
```

Contrairement à la première version de ce guide, `kpi_agregation.py` n'appelle plus des fonctions hypothétiques : il appelle directement `api/dotnetApi.py`, qui reproduit fidèlement les 4 endpoints Sage nécessaires, tels que documentés.

---

## 1. Installer les dépendances

```bash
uv add pandas google-genai
```

`httpx` est déjà présent dans `pyproject.toml` — c'est lui qui sera utilisé dans `api/dotnetApi.py`.

---

## 2. Compléter votre `api/dotnetApi.py` existant

Ce fichier encapsule 4 endpoints réels de la documentation Sage :

| Fonction | Endpoint Sage | Rôle |
|---|---|---|
| `get_articles()` | `GET /api/v1/articles` | Stock (`aR_TotalQteStock`), prix (`aR_PrixVen`), famille (`cL_No1`/`cL_No2`) |
| `get_catalogues()` | `GET /api/v1/catalogues` | Libellés de famille (`cL_No` → `cL_Intitule`) |
| `get_documents_facturation(...)` | `POST /api/v1/documents_facturation` | Factures de la période (types 6=Facture, 7=Facture comptabilisée) |
| `get_lignes_document(num)` | `GET /api/v1/lignes_document` | Détail des articles vendus par facture (`lP_MontantHT`) |

Le code complet est dans `api/dotnetApi.py` (fichier livré à part). Point clé : chaque réponse Sage est enveloppée dans `{isSuccess, value, error}` — le client lève une exception si `isSuccess=false` plutôt que de laisser passer une donnée invalide, conformément à la règle du Skill 1 (« ne jamais halluciner si le service renvoie une erreur »).

Authentification : `Authorization: Bearer <API_TOKEN>`, avec `DOTNET_API_BASE` et `API_TOKEN` lus depuis votre `.env` existant.

---

## 3. Créer le Skill 2 — `tools/kpi_agregation.py`

Logique réelle (plus de données inventées) :

1. Récupère `catalogues` (libellés de famille) et `articles` (stock, prix, famille) en parallèle.
2. Récupère les factures (`documents_facturation`) sur la période demandée.
3. Pour chaque facture, récupère ses lignes (`lignes_document`) — avec une limite de **5 requêtes concurrentes** (`asyncio.Semaphore`) pour ne pas saturer l'API Sage sur une période chargée.
4. Agrège le CA HT par famille (via la correspondance article → famille), calcule le % du CA, et croise avec la valeur de stock (`quantité × prix`).
5. Retourne un tableau trié, limité à 15 lignes.

> **Choix de niveau de catalogue** : Sage 100 a 4 niveaux (`cL_Niveau` 0 à 3, ex. Bijoux → Or → Chaînes → Femme). Le code retient `cL_No2` (niveau 1, ex. « Or », « Appareils ») comme « famille » — c'est le niveau le plus proche de ce qu'on appelle une famille dans le reste de la formation. Changez `_famille_id()` si vous préférez un autre niveau.

Le code complet est dans `tools/kpi_agregation.py` (fichier livré à part).

---

## 4. Skill 3 — `tools/insights.py` (inchangé)

Ce tool ne dépend d'aucun endpoint Sage — il analyse le `kpi_table` déjà produit par le Skill 2, quelle que soit sa source. Aucune modification nécessaire par rapport à la version précédente de ce guide.

---

## 5. Skills 4+5 — `tools/dashboard_html.py` (inchangé)

Idem : ce tool assemble `kpi_table` + `insights` en HTML, indépendamment de la source des données.

---

## 6. Enregistrer les nouveaux tools dans `server.py`

```python
import asyncio
from fastmcp import FastMCP
from tools import art_clients, articles, relv_clients, stock_articles
from tools import kpi_agregation, insights, dashboard_html   # nouveaux imports

mcp_server = FastMCP("Jewelry MCP")

articles.register_tools(mcp_server)
relv_clients.register_tools(mcp_server)
stock_articles.register_tools(mcp_server)
art_clients.register_tools(mcp_server)

kpi_agregation.register_tools(mcp_server)   # Skill 2
insights.register_tools(mcp_server)         # Skill 3
dashboard_html.register_tools(mcp_server)   # Skills 4+5

async def main():
    await mcp_server.run_async(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000,
        path="/mcp",
    )

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 7. (Recommandé) Exposer `skills-dashboard-infosoft.md` comme Resource MCP

```python
from pathlib import Path

@mcp_server.resource("skills://dashboard-insights")
def skill_dashboard_insights() -> str:
    return Path("skills-dashboard-infosoft.md").read_text(encoding="utf-8")
```

---

## 8. Tester

```bash
uv run server.py
npx @modelcontextprotocol/inspector uv run server.py
```

Séquence de test, avec des dates réelles courtes pour commencer (ex. un mois) :

1. `get_kpi_par_famille(date_debut="2024-07-01", date_fin="2024-07-31")` → vérifier un tableau non vide.
   - Si vide : vérifiez qu'il existe bien des factures (types 6/7) sur cette période dans Sage.
2. Copier le résultat dans `generate_insights(kpi_table=...)` → vérifier le JSON `points_cles / anomalies / recommandations`.
3. Copier les deux résultats dans `generate_dashboard_html(...)` → sauvegarder en `.html` et ouvrir dans un navigateur.

**Test direct de l'API Sage (sans passer par MCP)**, pour valider vos credentials avant de coder :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
     "$DOTNET_API_BASE/api/v1/catalogues"
```

Si ce curl renvoie `isSuccess: true` avec vos catalogues, la couche `api/dotnetApi.py` fonctionnera de la même façon.

---

## 9. Points de vigilance

- **Performance** : `get_kpi_par_famille` fait 1 appel `lignes_document` par facture. Sur une période avec des centaines de factures, prévoyez un cache ou restreignez la période côté agent avant d'élargir.
- **Familles non classées** : un article sans `cL_No1`/`cL_No2` (0 ou absent) tombe dans « Non classé » — normal si votre catalogue Sage n'est pas complètement renseigné, mais à surveiller si cette catégorie devient trop grosse.
- Ne jamais transmettre à `generate_insights` un tableau de plus de 15 lignes.
- `temperature=0.2` pour `generate_insights` — ne pas l'augmenter.
- Si `get_documents_facturation` ou `get_lignes_document` lève une exception (`isSuccess=false`), la remonter telle quelle — ne jamais laisser `generate_insights` tourner sur des données partielles sans le signaler.

---

## 10. Agent générique — n'importe quel prompt (`agent_dashboard.py`)

Les scripts précédents (`dashboard_pipeline.py`, `web_dashboard.py`, `prompt_to_dashboard.py`) exécutent toujours la **même chaîne fixe** : CA par famille → insights → dashboard. Pour des demandes vraiment libres (« les produits par client », « que vend-on le plus à CARAT ? »...), il faut un vrai agent qui choisit lui-même ses tools.

**Nouveaux tools génériques** (ajoutés dans `tools/kpi_agregation.py`, aux côtés de `get_kpi_par_famille` qui reste inchangé) :

| Tool | Rôle |
|---|---|
| `get_kpi(dimension, date_debut, date_fin)` | CA/% agrégé par `"famille"`, `"client"` ou `"article"` |
| `get_produits_par_client(date_debut, date_fin, code_client=None)` | Détail produit × client (CA, quantité) |

`generate_dashboard_html` a aussi été généralisé : il prend maintenant un `title`, détecte automatiquement une colonne texte + une colonne numérique pour le graphique, et affiche systématiquement un tableau complet quel que soit le nombre de colonnes (utile pour `get_produits_par_client`, qui a 4 colonnes).

**`agent_dashboard.py`** implémente la vraie boucle ReAct : il récupère la liste de **tous** les tools MCP (anciens + nouveaux), les expose à Gemini comme des fonctions appelables, et laisse le modèle décider — appel après appel — quels tools utiliser et avec quels paramètres, jusqu'à ce qu'il appelle `generate_dashboard_html` (qui met fin à la boucle).

```bash
uv run agent_dashboard.py "les produits achetés par chaque client en juillet 2024"
uv run agent_dashboard.py "le CA par client du mois dernier"
```

**Limites à connaître** :
- Garde-fou `MAX_STEPS=8` pour éviter une boucle infinie si l'agent ne converge pas.
- Si une demande sort du périmètre des tools disponibles (ex. « prévisions de vente pour 2025 »), l'agent renverra du texte au lieu d'un dashboard — c'est voulu, plutôt que d'halluciner un résultat.
- `web_dashboard.py` utilise toujours la chaîne fixe, pas encore l'agent générique — dites-moi si vous voulez que je bascule le formulaire navigateur sur `agent_dashboard.py` à la place.
