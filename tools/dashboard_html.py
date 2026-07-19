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

# méthode interne pour générer un graphique Chart.js à partir d'un tableau de données
def _build_chart(chart_id: str, kpi_table: list[dict], chart_type: str = "bar") -> tuple[str, str]:
    if not kpi_table:
        return "<p>Aucune donnée.</p>", ""
    label_field, value_field = _detect_label_value(kpi_table[0])
    if not (label_field and value_field):
        return "<p>Pas de graphique pertinent pour ces données.</p>", ""

    labels = [str(r.get(label_field, "")) for r in kpi_table[:8]]
    values = [r.get(value_field, 0) for r in kpi_table[:8]]
    palette = ["#00C4CC", "#F2A900", "#E85D75", "#7B68EE", "#4CAF50", "#FF7043", "#42A5F5", "#AB47BC"]
    colors = palette[: len(values)]

    # --- Boutons radio pour choisir le type de graphique ---
    radios = f"""
    <div class="chart-toggle">
      <label><input type="radio" name="type_{chart_id}" value="bar"
        {"checked" if chart_type == "bar" else ""}
        onchange="renderChart_{chart_id}('bar')"> Barres</label>
      <label><input type="radio" name="type_{chart_id}" value="pie"
        {"checked" if chart_type == "pie" else ""}
        onchange="renderChart_{chart_id}('pie')"> Camembert</label>
    </div>"""

    canvas = f'{radios}<div class="chart-wrap"><canvas id="{chart_id}"></canvas></div>'

    # --- Fonction JS réutilisable : détruit et recrée le chart selon le type choisi ---
    script = f"""
            window.__allCharts = window.__allCharts || [];
            let chartInstance_{chart_id} = null;
            function renderChart_{chart_id}(type) {{
            if (chartInstance_{chart_id}) chartInstance_{chart_id}.destroy();
            chartInstance_{chart_id} = new Chart(document.getElementById('{chart_id}'), {{
                type: type,
                data: {{ labels: {json.dumps(labels)}, datasets: [{{ label: {json.dumps(value_field)}, data: {json.dumps(values)}, backgroundColor: {json.dumps(colors)} }}] }},
                options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: type === 'pie', position: 'right' }} }} }}
            }});
            const idx = window.__allCharts.indexOf(chartInstance_{chart_id});
            if (idx === -1) window.__allCharts.push(chartInstance_{chart_id});
            else window.__allCharts[idx] = chartInstance_{chart_id};
            }}
            renderChart_{chart_id}({json.dumps(chart_type)});
            """
    return canvas, script

# -------------------------------------------------------------
# TOOLS
# -------------------------------------------------------------

def register_tools(mcp: FastMCP):

    """Enregistre les outils de génération de dashboard HTML dans le MCP."""

    #=====================================================
    # Tool 1 Génération de dashboard HTML autonome (Chart.js + tableau)
    #=====================================================

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

    #=====================================================
    # Tool 2 Génération de dashboard HTML multi-sections (Chart.js + tableau)
    #=====================================================

    @mcp.tool()
    async def generate_multi_dashboard_html(
        title: str,
        sections: list[dict],   # [{ "label": str, "kpi_table": list[dict], "chart_type": "bar"|"pie", "theme": str }, ...]
        standalone: bool = True
    ) -> str:
        """
        Génère un dashboard avec plusieurs graphiques, regroupés en onglets par "theme".
        Si "theme" n'est pas fourni pour une section, son "label" sert de thème
        (= un onglet par section, comportement actuel).
        """
        themes: dict[str, list] = {}
        for i, section in enumerate(sections):
            theme = section.get("theme") or section.get("label", f"Section {i}")
            themes.setdefault(theme, []).append(section)

        scripts = ['<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>']
        tab_buttons, tab_panes = [], []

        for i, (theme, theme_sections) in enumerate(themes.items()):
            cards = []
            for j, section in enumerate(theme_sections):
                chart_id = f"chart_{i}_{j}"
                chart_type = section.get("chart_type", "bar")
                canvas_html, script_js = _build_chart(chart_id, section.get("kpi_table", []), chart_type)
                cards.append(f'<div class="card"><b>{section.get("label","")}</b>{canvas_html}</div>')
                if script_js:
                    scripts.append(f"<script>{script_js}</script>")

            active = "active" if i == 0 else ""
            tab_buttons.append(
                f'<button class="tab-btn {active}" onclick="switchTab(this, \'tab_{i}\')">{theme}</button>'
            )
            tab_panes.append(f'<div id="tab_{i}" class="tab-pane {active}"><div class="grid">{"".join(cards)}</div></div>')

        tabs_script = """
        <script>
        function switchTab(btn, paneId) {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(paneId).classList.add('active');
        requestAnimationFrame(() => (window.__allCharts || []).forEach(c => c && c.resize()));
        }
        </script>"""

        body = f"""<style>
        .card {{ background:#0F2038; border-radius:10px; padding:16px; margin-bottom:16px; }}
        .chart-wrap {{ position:relative; height:220px; width:100%; }}
        .grid {{ display:grid; grid-template-columns:1fr; gap:16px; }}
        @media (max-width: 700px) {{ .grid {{ grid-template-columns:1fr; }} }}
        .chart-toggle {{ display:flex; gap:16px; font-size:13px; color:#8FA3C0; margin-bottom:8px; }}
        .chart-toggle label {{ display:flex; align-items:center; gap:4px; cursor:pointer; }}
        .tabs {{ display:flex; gap:8px; margin-bottom:20px; border-bottom:1px solid #22385A; }}
        .tab-btn {{
        background:none;
        border:none;
        color:#8FA3C0;
        padding:16px 28px;        /* était 10px 16px → zone cliquable plus grande */
        cursor:pointer;
        font-size:16px;           /* était 14px */
        font-weight:600;
        border-bottom:3px solid transparent;  /* était 2px, plus visible */
        }}
        .tab-btn.active {{ color:#00C4CC; border-bottom:3px solid #00C4CC; }}
                .tab-pane {{ display:none; }}
                .tab-pane.active {{ display:block; }}
                </style>
                <div class="tabs">{"".join(tab_buttons)}</div>
                {"".join(tab_panes)}
                {tabs_script}{"".join(scripts)}"""

        if not standalone:
                return body

        return f"""<!DOCTYPE html>
        <html lang="fr"><head><meta charset="utf-8"><style>
        body {{ font-family: sans-serif; background:#0A1628; color:#fff; padding:24px; }}
        </style></head><body><h2>{title}</h2>{body}</body></html>"""