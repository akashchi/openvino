// Loads the investigation index, every investigation file, and the pattern
// files referenced by their signatures.

import { INV_DIR, PAT_DIR } from "./config.js";
import { invSig } from "./normalizers.js";

export async function loadData() {
    const index = await (await fetch(`${INV_DIR}/index.json`)).json();
    const metas = Array.isArray(index) ? index : (index.investigations || []);

    const investigations = await Promise.all(metas.map(async meta => {
        try {
            const data = await (await fetch(`${INV_DIR}/${meta.file}`)).json();
            return { ...data, _meta: meta, _file: meta.file };
        } catch (e) {
            return { _meta: meta, _file: meta.file, _error: String(e) };
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
