// Entry point: load data, build the model, then hand off to the router.

import { loadData } from "./data.js";
import { buildModel } from "./model.js";
import { initRouter } from "./router.js";
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
        initRouter(model);
    } catch (err) {
        renderError(app, err);
    }
}

main();
