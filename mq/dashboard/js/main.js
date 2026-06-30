// Entry point: load data, build the model, render, and wire up controls.

import { loadData } from "./data.js";
import { buildModel } from "./model.js";
import { renderStats } from "./render-stats.js";
import { renderCategories } from "./render-categories.js";
import { applySearch, setAll } from "./search.js";
import { esc } from "./utils.js";

function renderError(app, err) {
    const isFile = location.protocol === "file:";
    const hint = isFile
        ? `<p>The dashboard reads JSON files via <code>fetch()</code>, which browsers block on the <code>file://</code> protocol. Serve the <code>mq/</code> folder over HTTP and open the dashboard from there:</p>
      <pre>cd mq
python3 -m http.server 8000
# then open:
#   http://localhost:8000/dashboard/</pre>`
        : `<p>Make sure <code>../investigations/index.json</code> and <code>../patterns/*.json</code> are reachable from this page.</p>`;

    app.innerHTML = `<div class="notice">
      <h3>Could not load the database</h3>
      <p>${esc(String(err))}</p>
      ${hint}
    </div>`;
}

async function main() {
    const app = document.getElementById("app");
    try {
        const data = await loadData();
        if (!data.investigations.length) throw new Error("No investigations found.");

        const model = buildModel(data);
        app.innerHTML = renderStats(model) + `<div class="toolbar">
        <input id="q" type="search" placeholder="Search titles, PRs, errors, signatures…" />
        <button class="btn" id="expand">Expand all</button>
        <button class="btn" id="collapse">Collapse all</button>
      </div>
      <h2 class="section">Failures by category — click to expand</h2>
      <div id="cats">${renderCategories(model)}</div>`;

        document.getElementById("q").addEventListener("input", e => applySearch(e.target.value));
        document.getElementById("expand").addEventListener("click", () => setAll(true));
        document.getElementById("collapse").addEventListener("click", () => setAll(false));
    } catch (err) {
        renderError(app, err);
    }
}

main();
