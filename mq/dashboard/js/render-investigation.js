// Renders a single investigation as a collapsible card.

import { esc, asList, fmtDay } from "./utils.js";
import {
    invSig, invPR, invRunUrl, invTitle, invWf, invTime,
    rootCause, errorList, jobNames,
} from "./normalizers.js";

function workflowLabel(inv) {
    const wf = invWf(inv);
    if (wf.startsWith("Windows")) return "Windows";
    if (wf.startsWith("Linux")) return "Linux";
    return wf;
}

function rootCauseLabel(rc) {
    let label = "Root cause";
    if (rc.cls) label += ` · ${esc(rc.cls)}`;
    if (rc.conf) {
        const level = esc(String(rc.conf).split(/[\s-]/)[0]);
        label += ` · <span class="badge conf-${level}">${esc(rc.conf)}</span>`;
    }
    return label;
}

function testRows(inv) {
    const rows = [];
    if (inv.failed_test) rows.push(["Test", inv.failed_test]);
    if (inv.test_method) rows.push(["Method", inv.test_method]);
    if (inv.test_file) rows.push(["File", inv.test_file]);
    if (inv.device) rows.push(["Device", inv.device]);
    if (inv.exit_code) rows.push(["Exit code", inv.exit_code]);
    if (inv.command || inv.failed_command) rows.push(["Command", inv.command || inv.failed_command]);
    if (inv.test_summary) rows.push(["Result", inv.test_summary]);
    return rows;
}

function metaLinks(inv, pr) {
    const bits = [];
    const runUrl = invRunUrl(inv);
    if (runUrl) bits.push(`<a href="${esc(runUrl)}" target="_blank" rel="noopener">Run ${esc(inv.run_id || "")}</a>`);
    if (pr.url) bits.push(`<a href="${esc(pr.url)}" target="_blank" rel="noopener">PR #${esc(pr.number)}</a>${pr.author ? ` by ${esc(pr.author)}` : ""}`);
    if (inv.head_sha) bits.push(`<code>${esc(String(inv.head_sha).slice(0, 10))}</code>`);
    if (inv.trigger || inv.trigger_event) bits.push(esc(inv.trigger || inv.trigger_event));
    return bits.join(" &nbsp;·&nbsp; ");
}

export function renderInvestigation(inv, patterns) {
    if (inv._error) {
        return `<div class="inv"><div class="i-head"><span class="i-title">⚠ Failed to load ${esc(inv._file)}</span></div></div>`;
    }

    const sig = invSig(inv);
    const pr = invPR(inv);
    const rc = rootCause(inv);
    const errs = errorList(inv);
    const jobs = jobNames(inv);
    const pattern = patterns[sig];

    const fields = [];
    const add = (label, html) => {
        if (html != null && html !== "") {
            fields.push(`<div class="field"><div class="fl">${label}</div><div class="fv">${html}</div></div>`);
        }
    };

    if (inv.summary) add("Summary", esc(inv.summary));
    if (rc.text) add(rootCauseLabel(rc), esc(rc.text));
    if (jobs.length) add("Failed job(s)", jobs.map(j => `<span class="pill">${esc(j)}</span>`).join(""));
    if (inv.failed_step) add("Failed step", esc(inv.failed_step));
    if (errs.length) add("Errors / evidence", `<pre class="err">${errs.map(esc).join("\n")}</pre>`);

    const rows = testRows(inv);
    if (rows.length) {
        add("Test", `<dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd><code>${esc(v)}</code></dd>`).join("")}</dl>`);
    }

    if (inv.test_params) add("Test params", `<pre class="err">${esc(JSON.stringify(inv.test_params, null, 2))}</pre>`);
    if (inv.recommended_actions) add("Recommended actions", `<ul>${asList(inv.recommended_actions).map(a => `<li>${esc(a)}</li>`).join("")}</ul>`);
    if (inv.reproduction) add("Reproduction", esc(inv.reproduction));
    if (inv.prevention) add("Prevention", esc(inv.prevention));
    if (inv.investigation_notes) add("Notes", esc(inv.investigation_notes));
    if (inv.notes) add("Notes", esc(inv.notes));
    if (inv.pr_changes) add("PR changes", esc(inv.pr_changes));

    add("Links &amp; meta", metaLinks(inv, pr));
    if (pattern) add("Part of pattern", `${esc(pattern.title)} — <b>${pattern.count || 1}</b> occurrence(s)`);

    const rawJson = JSON.stringify(inv, (k, v) => (k === "_meta" || k === "_file" ? undefined : v), 2);
    const raw = `<details class="raw"><summary>Raw JSON</summary><pre>${esc(rawJson)}</pre></details>`;

    const title = invTitle(inv, patterns);
    const searchText = [title, sig, pr.number, pr.author, inv.summary, rc.text, jobs.join(" "), errs.join(" ")]
        .join(" ").toLowerCase();

    return `<div class="inv" data-search="${esc(searchText)}">
    <div class="i-head" onclick="this.parentNode.classList.toggle('open')">
      <span class="chev">▶</span>
      <span class="i-title">${esc(title)}</span>
      <span class="i-meta">${esc(workflowLabel(inv))} · ${esc(fmtDay(invTime(inv)))}${pr.number ? ` · #${esc(pr.number)}` : ""}</span>
    </div>
    <div class="i-body">${fields.join("")}${raw}</div>
  </div>`;
}
