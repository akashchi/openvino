// Renders the category panels (Category -> Pattern -> Investigations).

import { esc } from "./utils.js";
import { catColor } from "./config.js";
import { renderGroup } from "./render-group.js";

const investigationCount = groups => groups.reduce((sum, g) => sum + g.investigations.length, 0);

export function renderCategories(model) {
    const categories = Object.entries(model.byCat)
        .sort((a, b) => investigationCount(b[1]) - investigationCount(a[1]));

    return categories.map(([cat, groups]) => {
        const invCount = investigationCount(groups);
        const body = groups.map(g => renderGroup(g, model.patterns)).join("");
        return `<div class="cat" data-cat="${esc(cat)}" style="--c:${catColor(cat)}">
      <div class="cat-head" onclick="this.parentNode.classList.toggle('open')">
        <span class="chev">▶</span>
        <span class="name">${esc(cat)}</span>
        <span class="meta">${groups.length} pattern${groups.length > 1 ? "s" : ""} · ${invCount} investigation${invCount > 1 ? "s" : ""}</span>
      </div>
      <div class="cat-body">${body}</div>
    </div>`;
    }).join("");
}
