// Dedicated page for a single category: header, scoped stats, search and the
// list of pattern groups belonging to that category.

import { esc } from "./utils.js";
import { catColor } from "./config.js";
import { invPR } from "./normalizers.js";
import { renderGroup } from "./render-group.js";
import { applySearch, setAll } from "./search.js";

const investigationCount = groups => groups.reduce((sum, g) => sum + g.investigations.length, 0);

function scopedStats(groups) {
    const investigations = investigationCount(groups);
    const recurring = groups.filter(g => g.investigations.length > 1).length;
    const prs = new Set();
    groups.forEach(g => g.investigations.forEach(inv => {
        const n = invPR(inv).number;
        if (n) prs.add(n);
    }));
    return `<div class="stats">
      <div class="stat"><div class="num">${groups.length}</div><div class="lbl">Patterns</div></div>
      <div class="stat"><div class="num">${investigations}</div><div class="lbl">Investigations</div></div>
      <div class="stat"><div class="num">${recurring}</div><div class="lbl">Recurring</div><div class="sub">patterns seen &ge;2×</div></div>
      <div class="stat"><div class="num">${prs.size}</div><div class="lbl">PRs affected</div></div>
    </div>`;
}

export function renderCategoryPage(model, cat) {
    const groups = model.byCat[cat] || [];
    const body = groups.map(g => renderGroup(g, model.patterns)).join("");

    return `
    <a class="back-link" href="#/">← All categories</a>
    <div class="cat-page-head" style="--c:${catColor(cat)}">
      <span class="cat-dot"></span>
      <h2>${esc(cat)}</h2>
    </div>
    ${scopedStats(groups)}
    <div class="toolbar">
      <input id="q" type="search" placeholder="Search titles, PRs, errors, signatures…" />
      <button class="btn" id="expand">Expand all</button>
      <button class="btn" id="collapse">Collapse all</button>
    </div>
    <div id="cats" class="pattern-grid">${body}</div>`;
}

// Wire up controls after the category page HTML is inserted into the DOM.
export function wireCategoryPage() {
    const q = document.getElementById("q");
    if (q) q.addEventListener("input", e => applySearch(e.target.value));

    const expand = document.getElementById("expand");
    if (expand) expand.addEventListener("click", () => setAll(true));

    const collapse = document.getElementById("collapse");
    if (collapse) collapse.addEventListener("click", () => setAll(false));
}
