// Builds dashboard/manifest.json — a complete list of every investigation
// file, independent of the upstream investigations/index.json (which may be
// pruned to only recent entries). Run locally or in the deploy workflow:
//
//   node mq/dashboard/tools/build-manifest.mjs
//
// A static site cannot enumerate a directory at runtime, so this manifest is
// what lets the dashboard load *all* investigations.

import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dashboardDir = path.resolve(here, "..");
const invDir = path.resolve(dashboardDir, "../investigations");
const outFile = path.join(dashboardDir, "manifest.json");

const files = (await readdir(invDir))
    .filter(f => f.endsWith(".json") && f !== "index.json");

const entries = [];
for (const file of files) {
    try {
        const d = JSON.parse(await readFile(path.join(invDir, file), "utf8"));
        entries.push({
            file,
            investigation_id: d.investigation_id || file.replace(/\.json$/, ""),
            timestamp: d.timestamp || d.timestamp_utc || null,
            run_id: d.run_id ?? null,
            workflow_name: d.workflow_name || d.workflow || null,
            category: d.category || null,
            title: d.title || null,
            signature_hash: d.signature_hash || d.signature || null,
            pr_number: d.pr_number ?? null,
        });
    } catch (e) {
        console.error(`skip ${file}: ${e.message}`);
    }
}

// Newest first.
entries.sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));

await writeFile(outFile, JSON.stringify(entries, null, 2) + "\n");
console.log(`Wrote ${entries.length} entries to ${path.relative(process.cwd(), outFile)}`);
