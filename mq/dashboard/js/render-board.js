// Home view: overview stats + a Kanban-style board of category cards.
// Each card links to that category's dedicated page (#/cat/<category>).

import { esc } from "./utils.js";
import { catColor } from "./config.js";
import { renderStats } from "./render-stats.js";

const investigationCount = groups => groups.reduce((sum, g) => sum + g.investigations.length, 0);

function categoryCard(cat, groups) {
    const investigations = investigationCount(groups);
    const recurring = groups.filter(g => g.investigations.length > 1).length;
    return `<a class="kcard" href="#/cat/${encodeURIComponent(cat)}" style="--c:${catColor(cat)}">
      <div class="kcard-name">${esc(cat)}</div>
      <div class="kcard-metrics">
        <div class="kmetric"><span class="knum">${groups.length}</span><span class="klbl">pattern${groups.length === 1 ? "" : "s"}</span></div>
        <div class="kmetric"><span class="knum">${investigations}</span><span class="klbl">investigation${investigations === 1 ? "" : "s"}</span></div>
        <div class="kmetric"><span class="knum">${recurring}</span><span class="klbl">recurring</span></div>
      </div>
      <div class="kcard-open">Open →</div>
    </a>`;
}

export function renderBoard(model) {
    const cards = Object.entries(model.byCat)
        .sort((a, b) => investigationCount(b[1]) - investigationCount(a[1]))
        .map(([cat, groups]) => categoryCard(cat, groups))
        .join("");

    return renderStats(model) +
        `<h2 class="section">Categories — pick a board</h2>
         <div class="kanban">${cards}</div>`;
}
