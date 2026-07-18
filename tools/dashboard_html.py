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
