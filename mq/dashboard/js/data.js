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

// Prefer the dashboard-generated manifest (complete). Fall back to the upstream
// investigations index.json, which may be a bare array or { investigations: [] }
// and may be pruned to only recent entries.
async function loadIndex() {
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
