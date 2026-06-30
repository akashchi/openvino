// Top-of-page summary: aggregate counts, category split bar and workflow line.

import { esc } from "./utils.js";
import { catColor } from "./config.js";
import { badgeCat } from "./badges.js";
import { invCat, invPR } from "./normalizers.js";

function countBy(items, keyFn) {
    const counts = {};
    items.forEach(item => { const k = keyFn(item); counts[k] = (counts[k] || 0) + 1; });
    return counts;
}

export function renderStats(model) {
    const invs = model.investigations;
    const total = invs.length;

    const cats = countBy(invs, invCat);
    const prs = new Set(invs.map(i => invPR(i).number).filter(Boolean));
    const recurring = Object.values(model.groups).filter(g => g.investigations.length > 1).length;

    const sortedCats = Object.entries(cats).sort((a, b) => b[1] - a[1]);

    const catRows = sortedCats.map(([c, n]) => {
        const pct = (n / total * 100).toFixed(0);
        const bar = `<span style="display:inline-block;width:${pct}%;min-width:3px;height:8px;background:${catColor(c)};border-radius:3px;vertical-align:middle"></span>`;
        return `<tr>
          <td>${badgeCat(c)}</td>
          <td style="text-align:right;font-variant-numeric:tabular-nums;padding:0 10px">${n}</td>
          <td style="width:120px">${bar}</td>
          <td style="color:var(--muted);padding-left:4px">${pct}%</td>
        </tr>`;
    }).join("");

    return `
  <div class="stats">
    <div class="stat"><div class="num">${total}</div><div class="lbl">Investigations</div></div>
    <div class="stat"><div class="num">${Object.keys(model.patterns).length}</div><div class="lbl">Patterns</div></div>
    <div class="stat"><div class="num">${recurring}</div><div class="lbl">Recurring</div><div class="sub">patterns seen &ge;2×</div></div>
    <div class="stat"><div class="num">${prs.size}</div><div class="lbl">PRs affected</div></div>
  </div>
  <table class="cat-summary">
    <thead><tr>
      <th>Category</th>
      <th style="text-align:right">Count</th>
      <th colspan="2">Share</th>
    </tr></thead>
    <tbody>${catRows}</tbody>
  </table>`;
}
