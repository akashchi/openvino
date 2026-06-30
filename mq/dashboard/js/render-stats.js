// Top-of-page summary: aggregate counts, category split bar and workflow line.

import { esc } from "./utils.js";
import { catColor } from "./config.js";
import { badgeCat } from "./badges.js";
import { invCat, invWf, invPR } from "./normalizers.js";

function workflowGroup(inv) {
    const wf = invWf(inv);
    if (wf.startsWith("Windows")) return "Windows";
    if (wf.startsWith("Linux")) return "Linux";
    return wf || "Other";
}

function countBy(items, keyFn) {
    const counts = {};
    items.forEach(item => { const k = keyFn(item); counts[k] = (counts[k] || 0) + 1; });
    return counts;
}

export function renderStats(model) {
    const invs = model.investigations;
    const total = invs.length;

    const cats = countBy(invs, invCat);
    const wfs = countBy(invs, workflowGroup);
    const prs = new Set(invs.map(i => invPR(i).number).filter(Boolean));
    const recurring = Object.values(model.groups).filter(g => g.investigations.length > 1).length;

    const sortedCats = Object.entries(cats).sort((a, b) => b[1] - a[1]);

    const barCat = sortedCats
        .map(([c, n]) => `<span style="width:${(n / total * 100).toFixed(1)}%;background:${catColor(c)}" title="${esc(c)}: ${n}"></span>`)
        .join("");

    const catLines = sortedCats
        .map(([c, n]) => `<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;line-height:1">${badgeCat(c)}<span class="badge count">${n}</span></span>`)
        .join("");

    const wfLine = Object.entries(wfs).sort((a, b) => b[1] - a[1])
        .map(([w, n]) => `${esc(w)}: <b>${n}</b>`).join(" · ");

    return `
  <div class="stats">
    <div class="stat"><div class="num">${total}</div><div class="lbl">Investigations</div></div>
    <div class="stat"><div class="num">${Object.keys(model.patterns).length}</div><div class="lbl">Patterns</div></div>
    <div class="stat"><div class="num">${recurring}</div><div class="lbl">Recurring</div><div class="sub">patterns seen &ge;2×</div></div>
    <div class="stat"><div class="num">${prs.size}</div><div class="lbl">PRs affected</div></div>
    <div class="stat"><div class="num">${Object.keys(cats).length}</div><div class="lbl">Categories</div>
      <div class="bar">${barCat}</div></div>
  </div>
  <div style="display:flex;gap:20px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin:-6px 0 4px;">
    <span>${catLines}</span>
    <span style="margin-left:auto">${wfLine}</span>
  </div>`;
}
