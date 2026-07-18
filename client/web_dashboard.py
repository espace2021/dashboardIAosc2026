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