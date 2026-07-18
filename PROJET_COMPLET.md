# Projet complet — atelier1 (Jewelry MCP + Dashboard Décisionnel, agent Gemini)

Ce fichier regroupe l'intégralité du projet, dans son état le plus récent :
- LLM : Gemini (`google-genai`)
- Prompts externalisés dans `skills/` (chargés depuis le disque, plus de prompt en dur dans le code)
- Scripts client regroupés dans `client/`

Chaque section indique le **chemin de destination exact** dans `atelier1/`, suivi du contenu complet du fichier.

**Fichiers non inclus** (jamais partagés avec moi — gardez vos versions existantes) : `tools/articles.py`, `tools/relv_clients.py`, `tools/stock_articles.py`, `tools/art_clients.py`, ainsi que `.env` réel (secrets), `.venv/`, `.git/`, `uv.lock` (régénérer via `uv sync`).

**Note** : `GUIDE_INTEGRATION_SKILLS_ATELIER1.md` et `skills-dashboard-infosoft.md` datent de la toute première version du projet (avant le passage à l'architecture `skills/` + `client/` actuelle) — utiles pour la démarche d'ensemble, mais certains détails de code qu'ils montrent sont dépassés. Le code des sections ci-dessous fait foi.

## Sommaire

- `README.md`
- `GUIDE_INTEGRATION_SKILLS_ATELIER1.md`
- `skills-dashboard-infosoft.md`
- `skills/skill-0-interpretation-demande.md`
- `skills/skill-3-generation-insights.md`
- `skills/skill-orchestrateur-agent.md`
- `pyproject.toml`
- `.env.example`
- `.gitignore`
- `.python-version`
- `main.py`
- `server.py`
- `api/dotnetApi.py`
- `tools/kpi_agregation.py`
- `tools/insights.py`
- `tools/dashboard_html.py`
- `client/dashboard_pipeline.py`
- `client/web_dashboard.py`
- `client/prompt_to_dashboard.py`
- `client/agent_dashboard.py`
- `client/client_test_dashboard.py`

---

## `README.md`

````markdown
# atelier1 — Jewelry MCP

Serveur FastMCP exposant les données InfoSoft (Sage 100C) sous forme de tools MCP,
avec un dashboard décisionnel (KPIs + insights générés par LLM) et un agent
générique capable de construire un dashboard à partir de n'importe quel prompt.

Voir `GUIDE_INTEGRATION_SKILLS_ATELIER1.md` pour la marche à suivre complète.

## Démarrage rapide

```bash
uv sync
uv run server.py
```

Dans un autre terminal, au choix :

```bash
uv run client/client_test_dashboard.py                       # test avec dates figées
uv run client/prompt_to_dashboard.py "les ventes de juillet"  # chaîne fixe, dates en langage naturel
uv run client/agent_dashboard.py "les produits par client"    # agent générique, n'importe quel prompt
uv run client/web_dashboard.py                                # formulaire navigateur (http://127.0.0.1:8080)
```
````

---

## `GUIDE_INTEGRATION_SKILLS_ATELIER1.md`

````markdown
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
````

---

## `skills-dashboard-infosoft.md`

````markdown
# Skills — Dashboard InfoSoft (Sage 100C)

Ce fichier regroupe les 5 skills nécessaires à la construction du dashboard décisionnel InfoSoft, dans l'ordre où l'agent LangGraph les exécute : Extraction → Agrégation → Insights → Visualisation → Mise en page.

---

# Skill: Extraction InfoSoft (MCP)

## Role

Tu es l'agent responsable de la récupération des données brutes depuis le système InfoSoft (Sage 100C) via le serveur MCP. Tu ne réalises aucune analyse : ton unique responsabilité est d'aller chercher la bonne donnée, au bon endroit, sans la transformer.

## Objective

Récupérer, pour une période et un périmètre donnés, les données de ventes, de stock, de clients ou de facturation nécessaires à la demande, et les transmettre telles quelles au skill suivant (Agrégation KPI).

## Inputs

- `periode_debut` (date), `periode_fin` (date)
- `perimetre` (famille, client, ou global) — optionnel
- `type_donnee` (ventes | stock | clients | factures)

## Tools available

You can call the following MCP tools:

- `get_ventes_periode(debut, fin)` — retourne les lignes de vente sur une période
- `get_stock_par_famille()` — retourne la valeur et la quantité de stock, groupées par famille
- `get_ca_par_client(client_id)` — retourne le chiffre d'affaires et l'historique d'un client
- `get_factures_impayees()` — retourne la liste des factures en attente de règlement

## Strategy

1. Identifier, à partir de la demande, quel(s) tool(s) MCP correspondent au besoin.
2. Appeler le(s) tool(s) avec les paramètres fournis (dates, identifiants).
3. Ne jamais agréger, filtrer, arrondir ou recalculer les données à ce stade — cette responsabilité appartient au skill Agrégation KPI.
4. Transmettre les données brutes reçues du serveur MCP, sans modification.

## Output format

Un DataFrame (ou une liste de dicts JSON), avec les colonnes d'origine renvoyées par le serveur MCP, sans transformation.

## Rules

- Ne jamais halluciner de données si un tool retourne une erreur ou un résultat vide — remonter l'erreur telle quelle, ne pas la combler par une estimation.
- Ne jamais appeler un tool avec des paramètres inventés (ex : une date par défaut) sans confirmation explicite du contexte fourni par l'utilisateur ou l'agent appelant.
- Ne jamais transformer, arrondir ou filtrer les données à cette étape, même si cela semble utile pour la suite.

---

# Skill: Agrégation KPI

## Role

Tu es l'agent responsable de transformer les données brutes InfoSoft (issues du skill Extraction) en un tableau de KPIs compact, exploitable par le skill Génération d'Insights.

## Objective

Réduire un ensemble de données brutes (potentiellement plusieurs milliers de lignes) à un tableau de quelques lignes de KPIs significatifs, sur l'axe d'analyse demandé (famille, client, période, etc.).

## Inputs

- Le ou les DataFrame(s) brut(s) produits par le skill Extraction InfoSoft (MCP)
- `axe_analyse` (famille | client | periode) — l'angle sous lequel grouper les données
- `kpis_demandes` (optionnel) — liste des indicateurs à calculer ; si absent, calculer les KPIs standards (CA, %, stock)

## Tools available

You can call the following MCP tools:

- Aucun tool MCP direct. Ce skill opère uniquement sur les données déjà extraites, à l'aide de fonctions de calcul locales (pandas ou équivalent).

## Strategy

1. Grouper les données brutes par l'axe d'analyse demandé.
2. Calculer les agrégats pertinents : somme, moyenne, pourcentage relatif au total.
3. Croiser les KPIs connexes dans un seul tableau (ex : CA et valeur de stock côte à côte) pour permettre une comparaison directe.
4. Trier le tableau par ordre décroissant de l'indicateur principal.
5. Limiter la sortie à 5–15 lignes maximum ; au-delà, regrouper les éléments les moins significatifs sous une catégorie « Autres ».

## Output format

Un tableau de KPIs (DataFrame ou JSON), une ligne par élément de l'axe d'analyse, une colonne par KPI calculé. Exemple :

```json
[
  {"famille": "VERRERIE", "ca_ht": 210000, "pct_ca": 35.0, "valeur_stock": 95000},
  {"famille": "HYGIENE", "ca_ht": 128000, "pct_ca": 21.0, "valeur_stock": 310000}
]
```

## Rules

- Ne jamais transmettre au skill suivant un tableau brut de plus de 15 lignes.
- Toujours inclure une colonne de pourcentage relatif quand cela a du sens (ex : % du CA total).
- Ne jamais arrondir de façon à masquer un écart significatif (ex : ne pas arrondir 0,4 % à 0 %).
- Ne jamais mélanger deux unités différentes (ex : euros et quantités) dans une même colonne.

---

# Skill: Génération d'Insights

## Role

Tu es un analyste business senior pour un distributeur. Ton rôle est d'interpréter un tableau de KPIs et de produire une analyse claire, factuelle et actionnable — pas de simplement décrire les chiffres.

## Objective

Identifier, à partir des KPIs fournis par le skill Agrégation KPI, les points clés, les anomalies et les recommandations qui permettront à un décideur InfoSoft d'agir rapidement, sans avoir à relire lui-même l'ensemble des données.

## Inputs

- `kpi_table` (JSON) : tableau de KPIs agrégés, sortie du skill Agrégation KPI
- `contexte_metier` (optionnel) : précision sur l'axe d'analyse (ex : « famille d'articles », « client VIP », « période de soldes »)

## Tools available

You can call the following MCP tools:

- Aucun tool MCP. Ce skill s'exécute entièrement dans le raisonnement du LLM, à partir des données déjà fournies dans `kpi_table`. Il ne doit accéder à aucune source de données supplémentaire.

## Strategy

1. Lire attentivement l'intégralité du tableau `kpi_table` fourni.
2. Identifier 2 à 4 constats chiffrés et significatifs (`points_cles`) — privilégier les écarts les plus importants entre lignes.
3. Repérer les écarts, incohérences ou signaux faibles à signaler (`anomalies`) — retourner une liste vide `[]` si aucune n'est détectée, ne jamais en inventer une pour remplir le champ.
4. Formuler 1 à 3 recommandations concrètes et réalisables (`recommandations`), directement rattachées à un constat ou une anomalie identifiée.
5. Relire chaque affirmation produite et vérifier qu'elle est bien appuyée par un chiffre présent dans `kpi_table`, avant de renvoyer la réponse.

## Output format

Réponds UNIQUEMENT en JSON strict, sans texte hors du JSON, avec la structure suivante :

```json
{
  "points_cles": ["...", "..."],
  "anomalies": ["..."],
  "recommandations": ["...", "..."]
}
```

## Rules

- Ne jamais inventer de données absentes de `kpi_table`.
- Ne jamais fournir de recommandation sans donnée chiffrée à l'appui.
- Rester factuel : pas de ton commercial, pas de superlatifs non justifiés (« exceptionnel », « incroyable »...).
- Utiliser une température basse (0–0.3) pour ce skill — la créativité n'est pas souhaitable sur une tâche analytique.
- Toujours retourner un JSON valide, même lorsque `anomalies` est vide.
- Ne jamais répondre par un texte libre hors du format JSON demandé, même si la question semble appeler une réponse conversationnelle.

---

# Skill: Visualisation

## Role

Tu es l'agent responsable de transformer les KPIs et les insights en éléments visuels — graphiques et composants — intégrables au dashboard final.

## Objective

Produire, pour chaque KPI ou groupe de KPIs pertinent, la représentation graphique la plus adaptée (comparaison, répartition, évolution), dans le format attendu par la cible d'affichage (dashboard web interactif ou export statique).

## Inputs

- `kpi_table` (sortie du skill Agrégation KPI)
- `insights` (sortie du skill Génération d'Insights, pour mise en évidence visuelle des points signalés)
- `format_cible` (`web_interactif` | `export_statique`)

## Tools available

You can call the following MCP tools:

- Aucun tool MCP. Ce skill appelle des fonctions de rendu graphique (Chart.js / Recharts pour le web, matplotlib pour l'export) ; il ne récupère aucune donnée supplémentaire.

## Strategy

1. Choisir le type de graphique adapté à la nature de la donnée :
   - barres → comparaison entre catégories (ex : CA par famille)
   - donut / camembert → répartition d'un total (ex : % du CA par famille)
   - ligne → évolution dans le temps
2. Si `format_cible = web_interactif` : générer une configuration de graphique (JSON) incluant tooltip, tri et filtre interactifs.
3. Si `format_cible = export_statique` : générer une image (PNG) via matplotlib, pour intégration dans un PDF ou une slide.
4. Mettre en évidence visuellement (couleur d'accent, badge) les éléments mentionnés dans `insights.anomalies`.
5. Conserver une palette de couleurs cohérente avec la charte du dashboard.

## Output format

- Web : une configuration de graphique (JSON) prête à être rendue par le frontend (ex : structure attendue par Chart.js/Recharts).
- Export : le chemin du fichier image généré (PNG).

## Rules

- Ne jamais afficher plus de 8 catégories sur un même graphique — regrouper le reste sous « Autres » si nécessaire.
- Toujours conserver la même couleur pour une même catégorie (ex : une famille) d'un graphique à l'autre du dashboard.
- Ne jamais dupliquer dans le graphique un chiffre déjà mis en texte par le skill Insights — le graphique illustre, il ne répète pas.
- Ne jamais utiliser un type de graphique 3D ou une échelle tronquée qui pourrait déformer la lecture des écarts.

---

# Skill: Mise en Page du Dashboard

## Role

Tu es l'agent responsable de l'assemblage final du dashboard : la disposition des cartes KPI, du texte d'insights et des graphiques en un écran (ou document) cohérent et lisible.

## Objective

Assembler les sorties des skills précédents (KPIs, Insights, Graphiques) en un dashboard unique où l'information la plus actionnable (les insights) est immédiatement visible, sans obliger le lecteur à chercher.

## Inputs

- `kpi_table` (sortie du skill Agrégation KPI)
- `insights` (sortie du skill Génération d'Insights)
- `graphiques` (sortie du skill Visualisation)
- `theme` (couleurs, espacements de l'application hôte)

## Tools available

You can call the following MCP tools:

- Aucun tool MCP. Ce skill génère du balisage (HTML/CSS, ou une slide) à partir exclusivement des sorties déjà produites par les skills précédents.

## Strategy

1. Placer les insights (`points_cles`, `anomalies`, `recommandations`) en haut du dashboard — c'est l'information la plus actionnable, elle doit être vue en premier.
2. Disposer les graphiques bruts en dessous, organisés dans une grille cohérente (2 à 3 colonnes selon le nombre d'éléments).
3. Représenter les KPIs principaux sous forme de cartes (un chiffre clé + un libellé + une tendance), jamais sous forme de tableau dense en tête de dashboard.
4. Appliquer le thème visuel fourni (`theme`) de façon cohérente sur l'ensemble des éléments assemblés.
5. Faire ressortir visuellement (couleur d'accent, icône) toute anomalie signalée par le skill Insights.

## Output format

Un document HTML autonome (ou une slide), assemblant l'ensemble des éléments reçus, prêt à être affiché dans l'application ou exporté.

## Rules

- Ne jamais afficher un graphique sans son insight associé à proximité immédiate.
- Respecter strictement la hiérarchie visuelle : Insights > Cartes KPI > Graphiques bruts.
- Ne jamais dépasser 3 couleurs d'accent par écran, au-delà de la palette neutre de fond.
- Ne jamais surcharger un même écran avec plus de 6 cartes KPI simultanées — prévoir un défilement ou un second écran au-delà.
````

---

## `skills/skill-0-interpretation-demande.md`

````markdown
# Skill: Interprétation de la Demande

## Role

Tu extrais une période de dates à partir d'une demande utilisateur en langage naturel, exprimée en français.

## Objective

Transformer n'importe quelle formulation libre (« le mois dernier », « juillet 2024 », « de juin à août 2024 »...) en une période exacte et exploitable par les tools d'extraction Sage 100.

## Inputs

- La date du jour (fournie dans le message utilisateur, format YYYY-MM-DD)
- La demande de l'utilisateur (texte libre, fournie dans le message utilisateur)

## Tools available

You can call the following MCP tools:

- Aucun tool MCP. Ce skill ne fait qu'interpréter du texte ; il n'accède à aucune donnée et ne doit appeler aucun outil.

## Strategy

1. Repérer si la demande mentionne un mois précis (« juillet 2024 », « le mois dernier ») : utiliser le 1er et le dernier jour de ce mois.
2. Repérer si la demande mentionne une année seule (« en 2024 ») : utiliser le 1er janvier au 31 décembre de cette année.
3. Repérer si la demande mentionne une plage explicite (« de juin à août 2024 », « du 12/07/2022 au 25/07/2025 ») : respecter cette plage exactement, sans l'arrondir.
4. Si aucune période n'est mentionnée dans la demande : utiliser le mois calendaire précédent la date du jour fournie.
5. Ne jamais déduire une période contredisant une date explicitement donnée par l'utilisateur.

## Output format

Réponds UNIQUEMENT en JSON strict, sans aucun texte hors du JSON, avec exactement cette structure :

```json
{"date_debut": "YYYY-MM-DD", "date_fin": "YYYY-MM-DD"}
```

## Rules

- Ne jamais inventer une date qui contredit la demande explicite de l'utilisateur.
- Ne jamais renvoyer de texte, d'explication ou de commentaire en dehors du JSON demandé.
- En cas de doute sur une période ambiguë, privilégier l'interprétation la plus restrictive (période la plus courte compatible avec la demande) plutôt que d'inventer une plage large.
````

---

## `skills/skill-3-generation-insights.md`

````markdown
# Skill: Génération d'Insights

## Role

Tu es un analyste business senior pour un distributeur (bijouterie). Ton rôle est d'interpréter un tableau de KPIs et de produire une analyse claire, factuelle et actionnable — pas de simplement décrire les chiffres.

## Objective

Identifier, à partir des KPIs fournis, les points clés, les anomalies et les recommandations qui permettront à un décideur InfoSoft d'agir rapidement, sans avoir à relire lui-même l'ensemble des données.

## Inputs

- `kpi_table` : un tableau de KPIs agrégés (CA, quantités, stock, selon l'axe d'analyse demandé — famille, client, ou produit), fourni dans le message utilisateur au format JSON.

## Tools available

You can call the following MCP tools:

- Aucun tool MCP. Ce skill s'exécute entièrement dans le raisonnement du LLM, à partir des données déjà fournies dans `kpi_table`. Il ne doit accéder à aucune source de données supplémentaire.

## Strategy

1. Lire attentivement l'intégralité du tableau `kpi_table` fourni.
2. Identifier 2 à 4 constats chiffrés et significatifs (`points_cles`) — privilégier les écarts les plus importants entre lignes.
3. Repérer les écarts, incohérences ou signaux faibles à signaler (`anomalies`) — retourner une liste vide `[]` si aucune n'est détectée, ne jamais en inventer une pour remplir le champ.
4. Formuler 1 à 3 recommandations concrètes et réalisables (`recommandations`), directement rattachées à un constat ou une anomalie identifiée.
5. Relire chaque affirmation produite et vérifier qu'elle est bien appuyée par un chiffre présent dans `kpi_table`, avant de renvoyer la réponse.

## Output format

Réponds UNIQUEMENT en JSON strict, sans texte hors du JSON, avec la structure suivante :

```json
{
  "points_cles": ["...", "..."],
  "anomalies": ["..."],
  "recommandations": ["...", "..."]
}
```

## Rules

- Ne jamais inventer de données absentes de `kpi_table`.
- Ne jamais fournir de recommandation sans donnée chiffrée à l'appui.
- Rester factuel : pas de ton commercial, pas de superlatifs non justifiés (« exceptionnel », « incroyable »...).
- Toujours retourner un JSON valide, même lorsque `anomalies` est vide.
- Ne jamais répondre par un texte libre hors du format JSON demandé, même si la question semble appeler une réponse conversationnelle.
````

---

## `skills/skill-orchestrateur-agent.md`

````markdown
# Skill: Orchestrateur Agent Dashboard

## Role

Tu es un agent qui construit des dashboards décisionnels à partir des données Sage 100 d'une bijouterie (InfoSoft), en suivant le pattern ReAct (Raisonnement -> Action -> Observation).

## Objective

Transformer n'importe quelle demande utilisateur en langage naturel en un dashboard HTML pertinent, en choisissant toi-même les tools à appeler, dans quel ordre, et avec quels paramètres — sans chaîne fixe imposée.

## Inputs

- La demande de l'utilisateur (texte libre, fournie dans le message utilisateur)
- La date du jour (fournie dans le message utilisateur)
- La liste des tools MCP disponibles (fournie séparément à l'appel du modèle, pas dans ce texte)

## Tools available

You can call the following MCP tools:

- `get_kpi(dimension, date_debut, date_fin)` — CA/% agrégé par `"famille"`, `"client"` ou `"article"`
- `get_produits_par_client(date_debut, date_fin, code_client)` — détail produit × client (CA, quantité)
- `get_kpi_par_famille(date_debut, date_fin)` — conservé pour compatibilité ; préférer `get_kpi` pour toute nouvelle demande
- `generate_insights(kpi_table)` — analyse un tableau de KPIs (points_cles, anomalies, recommandations)
- `generate_dashboard_html(title, kpi_table, insights)` — assemble le dashboard final
- Les tools d'extraction Sage déjà existants (articles, stock, clients, relevés...) pour tout besoin non couvert par les tools ci-dessus

## Strategy

1. Identifie les données nécessaires à la demande (par famille, par client, par article/produit, sur quelle période) et choisis le ou les tools d'extraction/agrégation adaptés.
2. Le tableau obtenu ne doit jamais dépasser une trentaine de lignes — si besoin, affine la période ou le filtre plutôt que de tout redemander.
3. Appelle OBLIGATOIREMENT `generate_insights` sur ce tableau pour produire une analyse, avant de passer à l'étape suivante.
4. Termine TOUJOURS par un appel à `generate_dashboard_html` avec :
   - `title` : un titre clair décrivant la demande de l'utilisateur
   - `kpi_table` : le tableau obtenu à l'étape 1
   - `insights` : le résultat de l'étape 3

## Output format

La réponse finale doit toujours être le résultat de l'appel à `generate_dashboard_html` (un document HTML autonome). Ne réponds jamais en texte libre à la place de cet appel, sauf si la demande sort réellement du périmètre des tools disponibles.

## Rules

- Ne jamais inventer de données que les tools n'ont pas renvoyées.
- Si un tool renvoie une liste vide, appelle quand même `generate_dashboard_html` avec ce tableau vide plutôt que d'inventer des chiffres — le dashboard l'affichera clairement.
- Si la demande ne précise pas de période, utilise le mois calendaire précédent la date du jour.
- Si la demande sort du périmètre de tous les tools disponibles (ex. une prévision, une donnée non stockée dans Sage), dis-le clairement en texte plutôt que d'halluciner un dashboard.
````

---

## `pyproject.toml`

```toml
[project]
name = "atelier1"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "fastmcp>=3.4.4",
    "httpx>=0.28.1",
    "load-dotenv>=0.1.0",
    "pandas>=2.2.0",
    "google-genai>=0.3.0",
]
```

---

## `.env.example`

```bash
# Copier ce fichier en .env et renseigner vos propres valeurs.
# Ne jamais committer le .env réel (voir .gitignore).

DOTNET_API_BASE="https://isdevsvr.ddns.net/SageCommerciale/api/v1"
API_TOKEN="<votre_token_bearer_Sage>"
GOOGLE_API_KEY="<votre_cle_API_Google_Gemini>"

# Note : api/dotnetApi.py a actuellement verify=False en dur (certificat auto-signé
# du serveur de dev isdevsvr). A retirer/adapter avant de pointer vers un serveur
# de production avec un certificat valide.
```

---

## `.gitignore`

```bash
# Python-generated files
__pycache__/
*.py[oc]
build/
dist/
wheels/
*.egg-info

# Virtual environments
.venv

# Secrets - ne jamais committer (token Sage, clé Google...)
.env
```

---

## `.python-version`

```bash
3.13
```

---

## `main.py`

```python
def main():
    print("Hello from atelier1!")


if __name__ == "__main__":
    main()
```

---

## `server.py`

```python
import asyncio
from pathlib import Path
from fastmcp import FastMCP
from tools import art_clients, articles, relv_clients, stock_articles
from tools import kpi_agregation, insights, dashboard_html

mcp_server = FastMCP("Jewelry MCP")

articles.register_tools(mcp_server)
relv_clients.register_tools(mcp_server)
stock_articles.register_tools(mcp_server)
art_clients.register_tools(mcp_server)

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
```

---

## `api/dotnetApi.py`

```python
"""
Couche API — Client HTTP vers Sage 100 Commerciale (InfoSoft)
Toutes les fonctions retournent directement le champ `value` de la réponse
(ou lèvent une exception si isSuccess=false), conformément à l'enveloppe
{isSuccess, value, error} utilisée par tous les services API-Sage.

Variables d'environnement attendues (.env, déjà présentes dans le projet) :
- DOTNET_API_BASE  → ex. https://isdevsvr.ddns.net/SageCommerciale/api/v1
- API_TOKEN        → token Bearer fourni par InfoSoft
"""
import os
import httpx
from dotenv import load_dotenv
load_dotenv()
BASE_URL = os.getenv("DOTNET_API_BASE", "").rstrip("/")
API_TOKEN = os.getenv("API_TOKEN", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}


async def api_get(path: str, params: dict | None = None):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30, verify=False) as client:
        resp = await client.get(path, headers=_headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("isSuccess", False):
            raise RuntimeError(f"Sage API error on GET {path}: {data.get('error')}")
        return data["value"]


async def api_post(path: str, payload: dict):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30, verify=False) as client:
        resp = await client.post(path, headers=_headers(), json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("isSuccess", False):
            raise RuntimeError(f"Sage API error on POST {path}: {data.get('error')}")
        return data["value"]


async def get_articles() -> list[dict]:
    """GET /api/v1/articles — liste des articles, stock total et prix de vente, avec catalogues (cL_No1..4)."""
    return await api_get("/articles")


async def get_catalogues() -> list[dict]:
    """GET /api/v1/catalogues — hiérarchie des familles d'articles (4 niveaux : 0 à 3)."""
    return await api_get("/catalogues")


async def get_documents_facturation(
    date_debut: str,
    date_fin: str,
    types_document: list[int] = [6, 7],
) -> list[dict]:
    """
    POST /documents_facturation — factures sur une période.
    types_document : 6 = Facture, 7 = Facture comptabilisée (valeurs Sage standard).
    Dates au format 'YYYY-MM-DD'.
    """
    payload = {
        "numero": "", "reference": "", "codeClient": "", "intituleClient": "",
        "idRepresentant": None, "intituleRepresentant": "", "date": None,
        "typeDocument": None, "totalHT": None, "totalTTC": None, "resteAPayer": None,
        "tT_Periode": False, "dateDebut": date_debut, "dateFin": date_fin,
        "typesDocument": types_document, "sortField": None, "sortOrder": None,
    }
    return await api_post("/documents_facturation", payload)


async def get_lignes_document(num_document: str) -> list[dict]:
    """GET /lignes_document?numDocument=... — articles vendus pour un document donné."""
    return await api_get("/lignes_document", params={"numDocument": num_document})


async def get_recouvrement_client(code_client: str | None = None) -> list[dict]:
    """POST /recouvrement_client — factures impayées (tT_typeFiltre=1)."""
    payload = {
        "codeClient": code_client or "", "idRepresentant": None,
        "tT_Inclure_BL_BA_BR": True, "tT_typeFiltre": 1,
        "sortField": None, "sortOrder": "desc",
        "rC_NumClient": None, "rC_IntituleClient": None, "rC_Representant": None,
        "rC_Piece": None, "rC_Date": None, "rC_ModeReglement": None,
        "rC_Echeance": None, "rC_NumBanque_Cheque_Traite": None, "rC_EtatPiece": None,
        "rC_Intitule": None, "rC_Montant": 0, "rC_MontantAffecte": None, "rC_Solde": None,
    }
    return await api_post("/recouvrement_client", payload)
```

---

## `tools/kpi_agregation.py`

```python
"""
Skill 2 — Agrégation KPI (basé sur l'API Sage 100 réelle)
Calcule le CA HT et la valeur de stock par famille d'articles, sur une période donnée.

Source des données :
- api.dotnetApi.get_catalogues()            -> libellés de famille (cL_No -> cL_Intitule)
- api.dotnetApi.get_articles()               -> stock (aR_TotalQteStock), prix (aR_PrixVen), famille (cL_No1/cL_No2)
- api.dotnetApi.get_documents_facturation()  -> factures de la période (types 6, 7)
- api.dotnetApi.get_lignes_document()        -> détail des articles vendus par facture (lP_MontantHT)

NOTE : la documentation Sage n'est pas cohérente sur la casse des champs d'un endpoint
à l'autre (ex. "numero" pour documents_facturation vs "Numero" pour documents_achat
dans les exemples de la doc). Toutes les lectures de champs passent donc par `_field()`,
qui essaie plusieurs variantes de casse plutôt que de supposer une seule orthographe exacte.
"""
import asyncio
import pandas as pd
from fastmcp import FastMCP

from api import dotnetApi

# Limite de requêtes concurrentes vers l'API Sage (évite de la saturer sur une grosse période)
_CONCURRENCY = 5


def _field(d: dict, *candidates: str, default=None):
    """
    Retourne la valeur du premier champ trouvé parmi `candidates`, en essayant
    d'abord la casse exacte puis une comparaison insensible à la casse.
    Évite les KeyError quand l'API renvoie une casse différente de la documentation.
    """
    for c in candidates:
        if c in d:
            return d[c]
    lower_map = {k.lower(): v for k, v in d.items()}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return default


def _famille_labels(catalogues: list[dict]) -> dict[int, str]:
    """cL_No -> cL_Intitule, pour résoudre le libellé de famille."""
    return {
        _field(c, "cL_No", "CL_No"): _field(c, "cL_Intitule", "CL_Intitule")
        for c in catalogues
    }


def _famille_id(article: dict) -> int:
    """
    Niveau de catalogue retenu comme 'famille' : cL_No2 (ex. 'Or', 'Appareils')
    si renseigné, sinon on retombe sur cL_No1 (ex. 'Bijoux', 'Accessoires').
    Adaptez ce choix de niveau à votre propre arborescence de catalogues si besoin.
    """
    return _field(article, "cL_No2", "CL_No2") or _field(article, "cL_No1", "CL_No1") or 0


async def _lignes_avec_limite(numeros_documents: list[str], sem: asyncio.Semaphore) -> list[list[dict]]:
    async def _one(num):
        async with sem:
            return await dotnetApi.get_lignes_document(num)
    return await asyncio.gather(*[_one(n) for n in numeros_documents])


async def _lignes_facturees(date_debut: str, date_fin: str) -> list[dict]:
    """
    Retourne les lignes de facture de la période, jointes au client de leur document
    (nécessaire pour toute agrégation par client, ex. get_kpi(dimension="client")
    ou get_produits_par_client). Colonnes : aR_Ref, codeClient, ca_ht, quantite.
    """
    documents = await dotnetApi.get_documents_facturation(date_debut, date_fin, types_document=[6, 7])
    if not documents:
        return []

    client_par_doc = {
        _field(d, "numero", "Numero"): _field(d, "codeClient", "CodeClient", default="Inconnu")
        for d in documents
    }
    numeros = [n for n in client_par_doc if n]

    sem = asyncio.Semaphore(_CONCURRENCY)
    lignes_par_doc = await _lignes_avec_limite(numeros, sem)

    rows = []
    for numero, lignes in zip(numeros, lignes_par_doc):
        code_client = client_par_doc.get(numero, "Inconnu")
        for ligne in lignes:
            rows.append({
                "aR_Ref": _field(ligne, "aR_Ref", "AR_Ref"),
                "codeClient": code_client,
                "ca_ht": _field(ligne, "lP_MontantHT", "LP_MontantHT", default=0),
                "quantite": _field(ligne, "lP_QteMvt", "LP_QteMvt", default=0),
            })
    return rows


def register_tools(mcp: FastMCP):

    @mcp.tool()
    async def get_kpi(dimension: str, date_debut: str, date_fin: str) -> list[dict]:
        """
        Calcule des KPIs agrégés (CA HT, % du CA) sur les factures Sage 100 de la
        période, selon la dimension choisie : "famille", "client" ou "article".
        Ajoute la valeur de stock quand dimension="famille" ou "article".
        Dates au format 'YYYY-MM-DD'. Sortie triée par CA décroissant, max 15 lignes.
        Utilisez ce tool pour toute demande de type "CA/ventes par X" où X n'est pas
        forcément une famille d'articles (ex. "CA par client").
        """
        if dimension not in {"famille", "client", "article"}:
            raise ValueError("dimension doit être 'famille', 'client' ou 'article'")

        rows = await _lignes_facturees(date_debut, date_fin)
        if not rows:
            return []
        df = pd.DataFrame(rows)

        articles = await dotnetApi.get_articles()
        article_design = {
            _field(a, "aR_Ref", "AR_Ref"): _field(a, "aR_Design", "AR_Design", default="")
            for a in articles
        }
        article_valeur_stock = {
            _field(a, "aR_Ref", "AR_Ref"): (_field(a, "aR_TotalQteStock", "AR_TotalQteStock") or 0)
            * (_field(a, "aR_PrixVen", "AR_PrixVen") or 0)
            for a in articles
        }

        stock_par_label: dict[str, float] = {}
        if dimension == "famille":
            catalogues = await dotnetApi.get_catalogues()
            labels = _famille_labels(catalogues)
            famille_par_article = {_field(a, "aR_Ref", "AR_Ref"): _famille_id(a) for a in articles}
            df["label"] = df["aR_Ref"].map(famille_par_article).map(labels).fillna("Non classé")
            for a in articles:
                fam = labels.get(_famille_id(a), "Non classé")
                ref = _field(a, "aR_Ref", "AR_Ref")
                stock_par_label[fam] = stock_par_label.get(fam, 0) + article_valeur_stock[ref]
        elif dimension == "article":
            df["label"] = df["aR_Ref"].map(article_design).replace("", pd.NA).fillna(df["aR_Ref"])
            for ref, val in article_valeur_stock.items():
                label = article_design.get(ref) or ref
                stock_par_label[label] = stock_par_label.get(label, 0) + val
        else:  # client
            df["label"] = df["codeClient"]

        ca = df.groupby("label")["ca_ht"].sum().sort_values(ascending=False)
        pct = (ca / ca.sum() * 100).round(1)

        kpi = pd.DataFrame({"label": ca.index, "ca_ht": ca.values.round(2), "pct_ca": pct.values})
        if stock_par_label:
            kpi["valeur_stock"] = [round(stock_par_label.get(l, 0), 2) for l in ca.index]

        return kpi.head(15).to_dict(orient="records")

    @mcp.tool()
    async def get_produits_par_client(date_debut: str, date_fin: str, code_client: str | None = None) -> list[dict]:
        """
        Détaille les produits achetés par client sur la période (CA HT et quantité
        par couple client/produit). Si code_client est fourni, filtre sur ce client
        uniquement. Dates au format 'YYYY-MM-DD'. Sortie triée par CA décroissant,
        limitée à 30 lignes. Utilisez ce tool pour toute demande du type
        "produits par client", "qu'achète le client X", etc.
        """
        rows = await _lignes_facturees(date_debut, date_fin)
        if not rows:
            return []
        df = pd.DataFrame(rows)

        if code_client:
            df = df[df["codeClient"] == code_client]
            if df.empty:
                return []

        articles = await dotnetApi.get_articles()
        article_design = {
            _field(a, "aR_Ref", "AR_Ref"): _field(a, "aR_Design", "AR_Design", default="")
            for a in articles
        }
        df["produit"] = df["aR_Ref"].map(article_design).replace("", pd.NA).fillna(df["aR_Ref"])

        grouped = (
            df.groupby(["codeClient", "produit"])
            .agg(ca_ht=("ca_ht", "sum"), quantite=("quantite", "sum"))
            .reset_index()
            .sort_values("ca_ht", ascending=False)
        )
        grouped["ca_ht"] = grouped["ca_ht"].round(2)
        grouped = grouped.rename(columns={"codeClient": "client"})

        return grouped.head(30).to_dict(orient="records")

    @mcp.tool()
    async def get_kpi_par_famille(date_debut: str, date_fin: str) -> list[dict]:
        """
        Calcule CA HT, % du CA et valeur de stock par famille d'articles,
        à partir des factures Sage 100 sur la période [date_debut, date_fin]
        (dates au format 'YYYY-MM-DD').
        Sortie triée par CA décroissant, limitée à 15 lignes.
        """
        catalogues, articles = await asyncio.gather(
            dotnetApi.get_catalogues(),
            dotnetApi.get_articles(),
        )
        labels = _famille_labels(catalogues)
        article_famille = {_field(a, "aR_Ref", "AR_Ref"): _famille_id(a) for a in articles}
        article_valeur_stock = {
            _field(a, "aR_Ref", "AR_Ref"): (_field(a, "aR_TotalQteStock", "AR_TotalQteStock") or 0)
            * (_field(a, "aR_PrixVen", "AR_PrixVen") or 0)
            for a in articles
        }

        documents = await dotnetApi.get_documents_facturation(date_debut, date_fin, types_document=[6, 7])
        if not documents:
            return []

        numeros = [_field(d, "numero", "Numero") for d in documents]
        numeros = [n for n in numeros if n]  # ignore les documents sans numéro exploitable

        sem = asyncio.Semaphore(_CONCURRENCY)
        lignes_par_doc = await _lignes_avec_limite(numeros, sem)

        rows = [
            {
                "aR_Ref": _field(ligne, "aR_Ref", "AR_Ref"),
                "ca_ht": _field(ligne, "lP_MontantHT", "LP_MontantHT", default=0),
            }
            for lignes in lignes_par_doc
            for ligne in lignes
        ]
        df = pd.DataFrame(rows)
        if df.empty:
            return []

        df["famille"] = df["aR_Ref"].map(article_famille).map(labels).fillna("Non classé")

        ca_famille = df.groupby("famille")["ca_ht"].sum().sort_values(ascending=False)
        pct_ca = (ca_famille / ca_famille.sum() * 100).round(1)

        stock_par_famille: dict[str, float] = {}
        for a in articles:
            ref = _field(a, "aR_Ref", "AR_Ref")
            fam = labels.get(_famille_id(a), "Non classé")
            stock_par_famille[fam] = stock_par_famille.get(fam, 0) + article_valeur_stock[ref]

        kpi = pd.DataFrame({
            "famille": ca_famille.index,
            "ca_ht": ca_famille.values,
            "pct_ca": pct_ca.values,
            "valeur_stock": [round(stock_par_famille.get(f, 0), 2) for f in ca_famille.index],
        })
        kpi["ca_ht"] = kpi["ca_ht"].round(2)

        return kpi.head(15).to_dict(orient="records")
```

---

## `tools/insights.py`

```python
"""
Skill 3 - Generation d'Insights (version Gemini)
Analyse un tableau de KPIs et produit points_cles / anomalies / recommandations.
Le prompt de ce skill vit dans skills/skill-3-generation-insights.md - ce fichier
ne fait que le charger et l'utiliser, il ne contient plus le texte du prompt.
"""
import os
import json
import time
from pathlib import Path
from google import genai
from fastmcp import FastMCP

MODEL = "gemini-2.5-flash"
SKILL_PATH = Path(__file__).parent.parent / "skills" / "skill-3-generation-insights.md"


def _call_gemini_with_retry(fn, *args, max_retries=4, base_delay=3, **kwargs):
    """
    Réessaie automatiquement en cas d'indisponibilité temporaire de l'API Gemini
    (503 UNAVAILABLE, surcharge du modèle) - erreur transitoire de Google, pas un
    bug applicatif. Backoff exponentiel : 3s, 6s, 12s, 24s.
    """
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            transient = any(s in str(exc) for s in ("503", "UNAVAILABLE", "overloaded", "429", "rate_limit"))
            if not transient or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"   (Gemini temporairement surchargé, nouvel essai dans {delay}s...)")
            time.sleep(delay)


def register_tools(mcp: FastMCP):

    @mcp.tool()
    async def generate_insights(kpi_table: list[dict]) -> dict:
        """
        Génère une analyse structurée (points_cles, anomalies, recommandations)
        à partir d'un tableau de KPIs produit par get_kpi_par_famille.
        En cas d'indisponibilité prolongée de Gemini, retourne un résultat de
        repli plutôt que de faire échouer tout le dashboard.
        """
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        system_prompt = SKILL_PATH.read_text(encoding="utf-8")
        user_prompt = f"Voici les KPIs à analyser : {json.dumps(kpi_table, ensure_ascii=False)}"

        try:
            response = _call_gemini_with_retry(
                client.models.generate_content,
                model=MODEL,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config={"temperature": 0.2, "response_mime_type": "application/json"},
            )
            return json.loads(response.text)
        except Exception as exc:
            return {
                "points_cles": [],
                "anomalies": [f"Analyse indisponible : le service Gemini est temporairement surchargé ({exc})."],
                "recommandations": ["Réessayer la génération du dashboard dans quelques minutes."],
            }
```

---

## `tools/dashboard_html.py`

```python
"""
Skills 4+5 — Visualisation + Mise en page (version générique)
Assemble un tableau de données quelconque (kpi_table) + insights en un dashboard
HTML interactif autonome. Fonctionne avec n'importe quelle forme de tableau :
- 1 dimension (ex. get_kpi_par_famille, get_kpi) -> graphique + tableau
- multi-colonnes (ex. get_produits_par_client) -> tableau détaillé, sans graphique
  si aucune paire (label, valeur numérique) évidente n'est détectée.
"""
import json
from fastmcp import FastMCP


def _detect_label_value(row: dict) -> tuple[str | None, str | None]:
    """Détecte automatiquement une colonne texte (label) et une colonne numérique (valeur)."""
    label_field = None
    value_field = None
    for k, v in row.items():
        if isinstance(v, str) and label_field is None:
            label_field = k
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and value_field is None:
            value_field = k
    return label_field, value_field


def register_tools(mcp: FastMCP):

    @mcp.tool()
    async def generate_dashboard_html(title: str, kpi_table: list[dict], insights: dict) -> str:
        """
        Génère un dashboard HTML autonome (Chart.js + tableau) à partir d'un tableau
        de données quelconque (kpi_table, liste de dicts) et d'une analyse (insights,
        sortie de generate_insights). `title` doit décrire la demande de l'utilisateur.
        Détecte automatiquement une colonne "label" et une colonne numérique pour le
        graphique quand c'est pertinent ; affiche toutes les colonnes dans un tableau.
        """
        if not kpi_table:
            rows_html = "<p>Aucune donnée pour cette période / ce filtre.</p>"
            chart_script = ""
        else:
            columns = list(kpi_table[0].keys())
            label_field, value_field = _detect_label_value(kpi_table[0])

            header_html = "".join(f"<th>{c}</th>" for c in columns)
            body_html = "".join(
                "<tr>" + "".join(f"<td>{row.get(c, '')}</td>" for c in columns) + "</tr>"
                for row in kpi_table
            )
            rows_html = f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"

            if label_field and value_field:
                labels = [str(r.get(label_field, "")) for r in kpi_table[:15]]
                values = [r.get(value_field, 0) for r in kpi_table[:15]]
                chart_script = f"""
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<div class="card"><canvas id="chart"></canvas></div>
<script>
new Chart(document.getElementById('chart'), {{
  type: 'bar',
  data: {{ labels: {json.dumps(labels)}, datasets: [{{ label: {json.dumps(value_field)}, data: {json.dumps(values)} }}] }},
  options: {{ responsive: true }}
}});
</script>"""
            else:
                chart_script = ""

        html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<style>
body {{ font-family: sans-serif; background:#0A1628; color:#fff; padding:24px; }}
.card {{ background:#0F2038; border-radius:10px; padding:16px; margin-bottom:16px; overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid #22385A; white-space:nowrap; }}
th {{ color:#8FA3C0; }}
</style></head><body>
<h2>{title}</h2>
{chart_script}
<div class="card"><b>Points clés</b><ul>{"".join(f"<li>{p}</li>" for p in insights.get("points_cles", []))}</ul></div>
<div class="card"><b>Anomalies</b><ul>{"".join(f"<li>{a}</li>" for a in insights.get("anomalies", []))}</ul></div>
<div class="card"><b>Recommandations</b><ul>{"".join(f"<li>{r}</li>" for r in insights.get("recommandations", []))}</ul></div>
<div class="card">{rows_html}</div>
</body></html>"""
        return html
```

---

## `client/dashboard_pipeline.py`

```python
"""
dashboard_pipeline.py (version Gemini)
Logique partagée par web_dashboard.py et prompt_to_dashboard.py :
1) interprète une demande en langage naturel pour en extraire une période de dates
   (Skill 0 - Interprétation de la demande, via Gemini)
2) exécute la chaîne de tools MCP existante :
       get_kpi_par_famille -> generate_insights -> generate_dashboard_html

Prérequis : le serveur MCP doit déjà tourner (uv run server.py).
"""
import os
import json
import time
import datetime as dt
from pathlib import Path

from fastmcp import Client
from google import genai
from dotenv import load_dotenv

load_dotenv()  # script client - jamais couvert par le load_dotenv() de api/dotnetApi.py

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"   # doit correspondre à server.py
MODEL = "gemini-2.5-flash"

SKILL_0_PATH = Path(__file__).parent.parent / "skills" / "skill-0-interpretation-demande.md"


def _call_gemini_with_retry(fn, *args, max_retries=4, base_delay=3, **kwargs):
    """Réessaie automatiquement en cas d'indisponibilité temporaire de l'API Gemini."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            transient = any(s in str(exc) for s in ("503", "UNAVAILABLE", "overloaded", "429", "rate_limit"))
            if not transient or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"   (Gemini temporairement surchargé, nouvel essai dans {delay}s...)")
            time.sleep(delay)


def extract_dates_from_prompt(prompt: str) -> dict:
    """Utilise Gemini (skill skill-0-interpretation-demande.md) pour transformer une demande en {date_debut, date_fin}."""
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    system_prompt = SKILL_0_PATH.read_text(encoding="utf-8")
    aujourdhui = dt.date.today().isoformat()
    user_message = f'Nous sommes aujourd\'hui le {aujourdhui}.\n\nDemande : "{prompt}"'

    response = _call_gemini_with_retry(
        client.models.generate_content,
        model=MODEL,
        contents=f"{system_prompt}\n\n{user_message}",
        config={"temperature": 0, "response_mime_type": "application/json"},
    )
    return json.loads(response.text)


def _extract_tool_result(result):
    """
    Récupère la donnée renvoyée par un tool MCP, quelle que soit la forme
    exacte du résultat selon la version de fastmcp.
    """
    if getattr(result, "data", None) is not None:
        return result.data
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


async def build_dashboard_from_dates(date_debut: str, date_fin: str) -> str | None:
    """Exécute get_kpi_par_famille -> generate_insights -> generate_dashboard_html. None si aucune donnée."""
    async with Client(MCP_SERVER_URL) as client:
        kpi_result = await client.call_tool(
            "get_kpi_par_famille", {"date_debut": date_debut, "date_fin": date_fin}
        )
        kpi_table = _extract_tool_result(kpi_result)

        if not kpi_table:
            return None

        insights_result = await client.call_tool("generate_insights", {"kpi_table": kpi_table})
        insights = _extract_tool_result(insights_result)

        html_result = await client.call_tool(
            "generate_dashboard_html",
            {
                "title": f"Dashboard InfoSoft — CA par famille ({date_debut} au {date_fin})",
                "kpi_table": kpi_table,
                "insights": insights,
            },
        )
        return _extract_tool_result(html_result)


async def build_dashboard_from_prompt(prompt: str) -> tuple[str | None, dict]:
    """
    Pipeline complet : prompt -> dates -> dashboard HTML.
    Retourne (html_ou_None, dates_utilisees) pour que l'appelant puisse toujours
    afficher la période interprétée, même quand le dashboard est vide.
    """
    dates = extract_dates_from_prompt(prompt)
    html = await build_dashboard_from_dates(dates["date_debut"], dates["date_fin"])
    return html, dates
```

---

## `client/web_dashboard.py`

```python
"""
web_dashboard.py
Serveur web local (stdlib uniquement) : un simple champ de prompt en langage
naturel dans le navigateur declenche l'AGENT GENERIQUE (agent_dashboard.py),
qui decide lui-meme quels tools appeler selon la demande - CA par famille,
par client, produits par client, ou toute autre combinaison couverte par les
tools MCP disponibles.

Prerequis : le serveur MCP doit deja tourner dans un autre terminal :
    uv run server.py

Usage :
    uv run web_dashboard.py
Puis ouvrir http://127.0.0.1:8080 dans le navigateur.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from agent_dashboard import run_agent

WEB_PORT = 8080

FORM_PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Dashboard InfoSoft</title>
<style>
body {{ font-family: sans-serif; background:#0A1628; color:#fff; padding:40px; }}
form {{ background:#0F2038; padding:24px; border-radius:10px; max-width:520px; }}
label {{ display:block; margin-top:12px; font-size:14px; color:#8FA3C0; }}
textarea {{ width:100%; padding:10px; margin-top:4px; border-radius:6px; border:1px solid #22385A; background:#0A1628; color:#fff; box-sizing:border-box; font-family:inherit; font-size:14px; resize:vertical; }}
button {{ margin-top:20px; padding:10px 20px; background:#00C4CC; color:#0A1628; border:none; border-radius:6px; font-weight:bold; cursor:pointer; }}
.exemples {{ margin-top:16px; font-size:12px; color:#8FA3C0; }}
</style></head><body>
<h2>Dashboard InfoSoft — décrivez ce que vous voulez voir</h2>
<form action="/dashboard" method="get">
  <label>Votre demande (n'importe laquelle)</label>
  <textarea name="prompt" rows="3" required placeholder="ex. les produits achetés par chaque client en juillet 2024">{prompt}</textarea>
  <button type="submit">Générer le dashboard</button>
</form>
<p class="exemples">Exemples : « le CA par famille du mois dernier » &middot; « les produits par client en juillet 2024 » &middot; « que vend-on le plus à CARAT cette année ? »</p>
</body></html>"""


def _error_page(message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"></head>
<body style="font-family:sans-serif; background:#0A1628; color:#fff; padding:40px;">
<h2>&#9888; {message}</h2>
<p><a href="/" style="color:#00C4CC;">&larr; Retour au formulaire</a></p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Le navigateur a fermé la connexion avant la fin de l'envoi (page
            # rafraîchie, requête dupliquée, onglet fermé...) - rien à corriger côté
            # applicatif, on ignore simplement plutôt que de planter le thread.
            print("   (connexion fermée par le navigateur avant la fin de l'envoi - ignoré)")

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/":
            self._send_html(FORM_PAGE.format(prompt=""))
            return

        if parsed.path == "/dashboard":
            prompt = params.get("prompt", [""])[0].strip()
            if not prompt:
                self._send_html(_error_page("Merci de décrire ce que vous voulez voir."), status=400)
                return
            try:
                result = asyncio.run(run_agent(prompt))

                is_html = result.strip().startswith("<!DOCTYPE") or result.strip().startswith("<html")
                if not is_html:
                    # L'agent a renvoyé du texte libre (aucun tool ne couvrait la demande,
                    # ou boucle non aboutie) plutôt qu'un dashboard.
                    self._send_html(_error_page(
                        f"L'agent n'a pas produit de dashboard pour : « {prompt} ».<br><br>"
                        f"Réponse de l'agent : {result}"
                    ))
                    return

                self._send_html(result)
            except Exception as exc:
                self._send_html(_error_page(f"Erreur pendant la génération : {exc}"), status=500)
            return

        self._send_html("<h1>404</h1>", status=404)

    def log_message(self, format, *args):
        print(f"[web_dashboard] {self.address_string()} - {format % args}")

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            print("   (connexion interrompue par le client - ignoré)")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", WEB_PORT), Handler)
    print(f"Ouvrez http://127.0.0.1:{WEB_PORT} dans votre navigateur (Ctrl+C pour arrêter).")
    server.serve_forever()
```

---

## `client/prompt_to_dashboard.py`

```python
"""
prompt_to_dashboard.py
Génère un dashboard décisionnel à partir d'une simple demande en langage naturel.

Prérequis : le serveur MCP doit déjà tourner dans un autre terminal :
    uv run server.py

Usage :
    uv run prompt_to_dashboard.py "Montre-moi le dashboard des ventes de juillet 2024"
    uv run prompt_to_dashboard.py            (demande le prompt de façon interactive)
"""
import asyncio
import sys
import webbrowser
from pathlib import Path

from dashboard_pipeline import build_dashboard_from_prompt

OUTPUT_HTML = Path("dashboard_infosoft.html")


async def main(prompt: str):
    print(f"Prompt : {prompt!r}")

    html, dates = await build_dashboard_from_prompt(prompt)
    print(f"Période interprétée : {dates['date_debut']} -> {dates['date_fin']}")

    if html is None:
        print("Aucune facture trouvée sur cette période. Essayez une autre formulation ou une autre période.")
        return

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"Dashboard sauvegardé : {OUTPUT_HTML.resolve()}")
    webbrowser.open(OUTPUT_HTML.resolve().as_uri())


if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])
    else:
        user_prompt = input("Décrivez le dashboard que vous voulez : ").strip()

    try:
        asyncio.run(main(user_prompt))
    except Exception as exc:
        print(f"\n❌ Erreur : {exc}")
```

---

## `client/agent_dashboard.py`

```python
"""
agent_dashboard.py (version Gemini)
Agent générique (pattern ReAct) : à partir de N'IMPORTE QUELLE demande en langage
naturel, décide lui-même quels tools MCP appeler (parmi TOUS ceux exposés par le
serveur), dans quel ordre, et produit un dashboard HTML adapté à la demande.

Utilise Gemini (function calling natif) - le format des tools et de la boucle de
conversation diffère de la version Groq/OpenAI : Content/Part + function_call,
au lieu de messages (system/user/assistant/tool) + tool_calls.

Prérequis : le serveur MCP doit déjà tourner dans un autre terminal :
    uv run server.py

Usage :
    uv run agent_dashboard.py "les produits achetés par chaque client en juillet 2024"
    uv run agent_dashboard.py "le CA par famille du mois dernier"
    uv run agent_dashboard.py            (mode interactif)
"""
import asyncio
import datetime as dt
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

from fastmcp import Client
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()  # script client - jamais couvert par le load_dotenv() de api/dotnetApi.py

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"   # doit correspondre à server.py
MODEL = "gemini-2.5-flash"
OUTPUT_HTML = Path("dashboard_infosoft.html")
MAX_STEPS = 8   # garde-fou contre une boucle infinie de l'agent

SKILL_PATH = Path(__file__).parent.parent / "skills" / "skill-orchestrateur-agent.md"

# Mots-clés JSON Schema générés par FastMCP/Pydantic mais non supportés par le
# schéma de paramètres de l'API Gemini (function calling) - à retirer récursivement.
# ATTENTION : ne PAS inclure "title" ici - certains tools ont un paramètre qui
# s'appelle littéralement "title" (generate_dashboard_html) ; un strip aveugle par
# nom de clé supprimerait la définition de ce paramètre lui-même.
_UNSUPPORTED_SCHEMA_KEYS = {"additionalProperties", "$schema"}


def _clean_schema(node):
    if isinstance(node, dict):
        return {k: _clean_schema(v) for k, v in node.items() if k not in _UNSUPPORTED_SCHEMA_KEYS}
    if isinstance(node, list):
        return [_clean_schema(v) for v in node]
    return node


def _mcp_tool_to_gemini(tool) -> types.FunctionDeclaration:
    raw_schema = tool.inputSchema or {"type": "object", "properties": {}}
    schema = _clean_schema(raw_schema)
    return types.FunctionDeclaration(
        name=tool.name,
        description=tool.description or "",
        parameters=schema,
    )


def _tool_result_to_value(result):
    """Récupère la donnée renvoyée par un tool MCP, quelle que soit la forme du résultat."""
    if getattr(result, "data", None) is not None:
        return result.data
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _call_gemini_with_retry(fn, *args, max_retries=4, base_delay=3, **kwargs):
    """
    Réessaie automatiquement en cas d'indisponibilité temporaire de l'API Gemini
    (503 UNAVAILABLE, surcharge du modèle). Backoff exponentiel : 3s, 6s, 12s, 24s.
    """
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            transient = any(s in str(exc) for s in ("503", "UNAVAILABLE", "overloaded", "429", "rate_limit"))
            if not transient or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"   (Gemini temporairement surchargé, nouvel essai dans {delay}s...)")
            time.sleep(delay)


async def run_agent(prompt: str) -> str:
    """Boucle ReAct : interroge Gemini, exécute les tools demandés, jusqu'au dashboard final."""
    async with Client(MCP_SERVER_URL) as mcp_client:
        mcp_tools = await mcp_client.list_tools()
        gemini_tool = types.Tool(function_declarations=[_mcp_tool_to_gemini(t) for t in mcp_tools])

        genai_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        system_instruction = SKILL_PATH.read_text(encoding="utf-8")
        aujourdhui = dt.date.today().isoformat()

        contents = [types.Content(
            role="user",
            parts=[types.Part(text=f"Nous sommes aujourd'hui le {aujourdhui}.\n\n{prompt}")],
        )]

        for step in range(MAX_STEPS):
            response = _call_gemini_with_retry(
                genai_client.models.generate_content,
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[gemini_tool],
                    temperature=0,
                ),
            )
            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [
                part.function_call for part in candidate.content.parts if part.function_call
            ]

            if not function_calls:
                # L'agent a répondu en texte au lieu d'appeler un tool -> on s'arrête là.
                return response.text or "(L'agent n'a produit aucun dashboard.)"

            for fc in function_calls:
                args = dict(fc.args) if fc.args else {}
                print(f"   [étape {step + 1}] {fc.name}({args})")

                try:
                    tool_result = await mcp_client.call_tool(fc.name, args)
                    value = _tool_result_to_value(tool_result)
                except Exception as exc:
                    value = {"error": str(exc)}
                    print(f"      -> erreur : {exc}")

                if fc.name == "generate_dashboard_html" and isinstance(value, str):
                    return value  # tool terminal : on retourne directement le HTML généré

                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(name=fc.name, response={"result": value})],
                ))

        return "(Nombre maximal d'étapes atteint sans dashboard final. Reformulez ou simplifiez la demande.)"


async def main(prompt: str):
    print(f"Prompt : {prompt!r}\n")
    result = await run_agent(prompt)

    if not result.strip().startswith("<!DOCTYPE") and not result.strip().startswith("<html"):
        print(result)
        return

    OUTPUT_HTML.write_text(result, encoding="utf-8")
    print(f"\nDashboard sauvegardé : {OUTPUT_HTML.resolve()}")
    webbrowser.open(OUTPUT_HTML.resolve().as_uri())


if __name__ == "__main__":
    user_prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Décrivez le dashboard voulu : ").strip()
    try:
        asyncio.run(main(user_prompt))
    except Exception as exc:
        print(f"\n❌ Erreur : {exc}")
```

---

## `client/client_test_dashboard.py`

```python
"""
client_test_dashboard.py
Script de test : appelle en séquence les 3 tools MCP du dashboard décisionnel
    get_kpi_par_famille -> generate_insights -> generate_dashboard_html
et sauvegarde le dashboard HTML final, puis l'ouvre dans le navigateur.

Prérequis : le serveur doit déjà tourner dans un autre terminal :
    uv run server.py

Usage :
    uv run client_test_dashboard.py
"""
import asyncio
import json
import webbrowser
from pathlib import Path

from fastmcp import Client

SERVER_URL = "http://127.0.0.1:8000/mcp"   # doit correspondre à host/port/path de server.py
OUTPUT_HTML = Path("dashboard_infosoft.html")

# Période de test courte (adapter à des dates où vous savez qu'il existe des factures)
DATE_DEBUT = "2024-07-01"
DATE_FIN = "2024-07-31"


def _extract(result):
    """
    Récupère la donnée renvoyée par un tool MCP, quelle que soit la forme
    exacte du résultat selon la version de fastmcp :
    - `result.data`               -> donnée déjà structurée (dict/list/str)
    - `result.structured_content` -> repli si `.data` est absent
    - `result.content[0].text`    -> repli texte brut ; on tente un JSON,
                                      sinon on renvoie le texte tel quel (cas du HTML)
    """
    if getattr(result, "data", None) is not None:
        return result.data
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    text = result.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


async def main():
    async with Client(SERVER_URL) as client:

        # 1) Skill 2 - Agrégation KPI
        print(f"1) get_kpi_par_famille(date_debut={DATE_DEBUT!r}, date_fin={DATE_FIN!r})...")
        kpi_result = await client.call_tool(
            "get_kpi_par_famille",
            {"date_debut": DATE_DEBUT, "date_fin": DATE_FIN},
        )
        kpi_table = _extract(kpi_result)

        if not kpi_table:
            print("   -> kpi_table est vide.")
            print("      Vérifiez qu'il existe des factures (types 6/7) sur cette "
                  "période dans Sage, puis relancez avec d'autres dates.")
            return

        print(f"   -> {len(kpi_table)} famille(s) trouvée(s) :")
        for row in kpi_table:
            print(f"      {row}")

        # 2) Skill 3 - Génération d'Insights
        print("\n2) generate_insights(kpi_table=...)...")
        insights_result = await client.call_tool(
            "generate_insights",
            {"kpi_table": kpi_table},
        )
        insights = _extract(insights_result)

        print("   -> points_cles :")
        for p in insights.get("points_cles", []):
            print(f"      - {p}")
        print("   -> anomalies :")
        for a in insights.get("anomalies", []):
            print(f"      - {a}")
        print("   -> recommandations :")
        for r in insights.get("recommandations", []):
            print(f"      - {r}")

        # 3) Skills 4+5 - Dashboard HTML
        print("\n3) generate_dashboard_html(kpi_table=..., insights=...)...")
        html_result = await client.call_tool(
            "generate_dashboard_html",
            {
                "title": f"Dashboard InfoSoft — CA par famille ({DATE_DEBUT} au {DATE_FIN})",
                "kpi_table": kpi_table,
                "insights": insights,
            },
        )
        html = _extract(html_result)

        OUTPUT_HTML.write_text(html, encoding="utf-8")
        print(f"   -> Dashboard sauvegardé : {OUTPUT_HTML.resolve()}")

        webbrowser.open(OUTPUT_HTML.resolve().as_uri())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"\n❌ Erreur pendant le test : {exc}")
```
