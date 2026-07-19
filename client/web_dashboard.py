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

from fastmcp import Client
import datetime as dt

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"

DEFAULT_DIMENSIONS = [
    ("categorie", "CA par catégorie"),
    ("ville", "CA par ville"),
    ("canal_marketing", "CA par canal marketing"),
    ("statut_commande", "CA par statut de commande"),
]

WEB_PORT = 8080

FORM_PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Dashboard </title>
<style>
body {{ font-family: sans-serif; background:#0A1628; color:#fff; padding:40px; }}
form {{ background:#0F2038; padding:24px; border-radius:10px; max-width:520px; }}
label {{ display:block; margin-top:12px; font-size:14px; color:#8FA3C0; }}
textarea {{ width:100%; padding:10px; margin-top:4px; border-radius:6px; border:1px solid #22385A; background:#0A1628; color:#fff; box-sizing:border-box; font-family:inherit; font-size:14px; resize:vertical; }}
button {{ margin-top:20px; padding:10px 20px; background:#00C4CC; color:#0A1628; border:none; border-radius:6px; font-weight:bold; cursor:pointer; }}
.exemples {{ margin-top:16px; font-size:12px; color:#8FA3C0; }}

/* --- styles pour le dashboard multi-graphiques inséré ci-dessous --- */
.card {{ background:#0F2038; border-radius:10px; padding:16px; margin-bottom:16px; }}
.chart-wrap {{ position:relative; height:220px; width:100%; }}
.grid {{ display:grid; grid-template-columns:repeat(2, 1fr); gap:16px; margin-top:24px; }}
@media (max-width: 700px) {{ .grid {{ grid-template-columns:1fr; }} }}
</style></head><body>
<h2>Dashboard — décrivez ce que vous voulez voir</h2>
<form action="/dashboard" method="get">
  <label>Votre demande (n'importe laquelle)</label>
  <textarea name="prompt" rows="3" required placeholder="ex. les produits achetés par chaque client en juillet 2024">{prompt}</textarea>
  <button type="submit">Générer le dashboard</button>
</form>"""


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
            try:
                default_dashboard = asyncio.run(build_default_dashboard())
            except Exception as exc:
                default_dashboard = f"<p style='color:#ff8080'>Vue par défaut indisponible : {exc}</p>"
            self._send_html(FORM_PAGE.format(prompt="") + default_dashboard + "</body></html>")
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



async def build_default_dashboard() -> str:
    # Dates à adapter dans la plage du dataset 
    date_debut = "2023-01-01"
    date_fin = "2025-07-31"

    async with Client(MCP_SERVER_URL) as client:
        sections = []
        for dimension, label in DEFAULT_DIMENSIONS:
            result = await client.call_tool(
                "get_kpi",
                {"dimension": dimension, "date_debut": date_debut, "date_fin": date_fin},
            )
            kpi_table = result.data if getattr(result, "data", None) is not None else []
            sections.append({"label": label, "kpi_table": kpi_table})

        result = await client.call_tool(
            "generate_multi_dashboard_html",
            {"title": f"Vue d'ensemble ({date_debut} → {date_fin})",
             "sections": sections, "standalone": False},
        )
        return result.data
    
if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", WEB_PORT), Handler)
    print(f"Ouvrez http://127.0.0.1:{WEB_PORT} dans votre navigateur (Ctrl+C pour arrêter).")
    server.serve_forever()