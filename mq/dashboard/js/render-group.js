// Renders a signature group (a pattern + its linked investigations).

import { esc, asList, fmtDay } from "./utils.js";
import { badgeCat } from "./badges.js";
import { invPR, invRunUrl, invTime } from "./normalizers.js";
import { renderInvestigation } from "./render-investigation.js";

// Render a list of GitHub URLs as compact numbered links (trailing id).
function linkIds(urls, prefix = "") {
  return urls.map(u => {
    const m = String(u).match(/(\d+)$/);
    return `<a href="${esc(u)}" target="_blank" rel="noopener">${prefix}${m ? m[1] : esc(u)}</a>`;
  }).join(" ");
}

function patternMeta(group) {
  const { pattern: p, sig } = group;
  const prs = p
    ? asList(p.affected_prs)
    : [...new Set(group.investigations.map(i => invPR(i).url).filter(Boolean))];
  const runs = p
    ? asList(p.recent_run_urls)
    : group.investigations.map(invRunUrl).filter(Boolean);
  const first = p ? p.first_seen : invTime(group.investigations[group.investigations.length - 1]);
  const last = p ? p.last_seen : invTime(group.investigations[0]);

  let html = `<div class="pattern-meta">`;
  html += `<div class="sig">signature: ${esc(p ? p.signature || sig : sig)}</div>`;
  html += `<dl class="kv">`;
  html += `<dt>File</dt><dd><code>patterns/${esc(sig)}.json</code></dd>`;
  html += `<dt>Seen</dt><dd>${esc(fmtDay(first))} → ${esc(fmtDay(last))}</dd>`;
  if (prs.length) html += `<dt>Affected PRs</dt><dd>${linkIds(prs, "#")}</dd>`;
  if (runs.length) html += `<dt>Recent runs</dt><dd>${linkIds(runs)}</dd>`;
  if (!p) html += `<dt>Pattern file</dt><dd style="color:var(--muted)">none — derived from investigations</dd>`;
  html += `</dl></div>`;
  return { html, first, last };
}

export function renderGroup(group, patterns) {
  const n = group.investigations.length;
  const meta = patternMeta(group);
  const invsHtml = group.investigations.map(inv => renderInvestigation(inv, patterns)).join("");
  const searchText = [group.title, group.sig].join(" ").toLowerCase();

  return `<div class="group" data-search="${esc(searchText)}">
    <div class="g-head" onclick="this.parentNode.classList.toggle('open')">
      <span class="chev">▶</span>
      <div>
        <div class="g-title">${esc(group.title)}</div>
        <div class="g-sub">${badgeCat(group.category)}
          <span>${n} investigation${n > 1 ? "s" : ""}</span>
        </div>
      </div>
    </div>
    <div class="g-body">
      ${meta.html}
      <div class="conn-label">Linked investigations (${n})</div>
      ${invsHtml}
    </div>
  </div>`;
}
