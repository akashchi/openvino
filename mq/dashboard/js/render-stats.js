// Top-of-page summary: aggregate counts across the whole dataset.

import { invPR } from "./normalizers.js";

export function renderStats(model) {
  const invs = model.investigations;
  const total = invs.length;
  const prs = new Set(invs.map(i => invPR(i).number).filter(Boolean));
  const recurring = Object.values(model.groups).filter(g => g.investigations.length > 1).length;

  return `
  <div class="stats">
    <div class="stat"><div class="num">${total}</div><div class="lbl">Investigations</div></div>
    <div class="stat"><div class="num">${Object.keys(model.patterns).length}</div><div class="lbl">Patterns</div></div>
    <div class="stat"><div class="num">${recurring}</div><div class="lbl">Recurring</div><div class="sub">patterns seen &ge;2×</div></div>
    <div class="stat"><div class="num">${prs.size}</div><div class="lbl">PRs affected</div></div>
  </div>`;
}
