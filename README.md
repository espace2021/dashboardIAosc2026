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
