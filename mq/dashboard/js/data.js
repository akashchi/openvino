// Loads the investigation list, every investigation file, and the pattern
// files referenced by their signatures.

import { INV_DIR, PAT_DIR, MANIFEST } from "./config.js";
import { invSig } from "./normalizers.js";

// Resolve the file name for an index/manifest entry across schema versions:
// - manifest / legacy index: "file"
// - new investigations index.json: "investigation_id" (file is <id>.json)
function entryFile(meta) {
    if (meta.file) return meta.file;
    if (meta.investigation_id) return `${meta.investigation_id}.json`;
    return null;
}

// Try to read a directory's JSON files from an autoindex/listing page.
// Works with `python -m http.server` (and most static dev servers), so the
// dashboard always reflects the actual files locally with no manual rebuild.
// GitHub Pages has no directory listing, so this returns null there.
async function listDir(dir) {
    try {
        const res = await fetch(`${dir}/`, { cache: "no-cache" });
        if (!res.ok) return null;
        const html = await res.text();
        const files = [...html.matchAll(/href="([^"?#]+\.json)"/gi)]
            .map(m => decodeURIComponent(m[1].split("/").pop()))
            .filter(f => f && f !== "index.json");
        return [...new Set(files)];
    } catch {
        return null;
    }
}

// Determine the full list of investigation entries. Priority:
//   1. Live directory listing (always current — local dev servers).
//   2. Dashboard manifest.json (generated at deploy — GitHub Pages).
//   3. Upstream investigations/index.json (may be pruned).
async function loadIndex() {
    const listed = await listDir(INV_DIR);
    if (listed && listed.length) return listed.map(file => ({ file }));

    try {
        const res = await fetch(MANIFEST, { cache: "no-cache" });
        if (res.ok) {
            const manifest = await res.json();
            const list = Array.isArray(manifest) ? manifest : (manifest.investigations || []);
            if (list.length) return list;
        }
    } catch {
        /* no manifest — fall back to the upstream index */
    }

    const index = await (await fetch(`${INV_DIR}/index.json`)).json();
    return Array.isArray(index) ? index : (index.investigations || []);
}

export async function loadData() {
    const metas = await loadIndex();

    const investigations = await Promise.all(metas.map(async meta => {
        const file = entryFile(meta);
        try {
            const data = await (await fetch(`${INV_DIR}/${file}`)).json();
            return { ...data, _meta: meta, _file: file };
        } catch (e) {
            return { _meta: meta, _file: file, _error: String(e) };
        }
    }));

    const signatures = [...new Set(investigations.map(invSig).filter(Boolean))];
    const patterns = {};
    await Promise.all(signatures.map(async sig => {
        try {
            const res = await fetch(`${PAT_DIR}/${sig}.json`);
            if (res.ok) patterns[sig] = await res.json();
        } catch {
            /* missing pattern file is non-fatal */
        }
    }));

    return { investigations, patterns };
}
