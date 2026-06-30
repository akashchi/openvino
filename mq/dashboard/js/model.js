// Groups investigations by signature, links each group to its pattern, and
// buckets the groups by category.

import { invSig, invCat, invTime, invTitle } from "./normalizers.js";

export function buildModel({ investigations, patterns }) {
    // signature -> { sig, pattern, investigations[] }
    const groups = {};
    for (const inv of investigations) {
        const sig = invSig(inv) || "unknown";
        if (!groups[sig]) groups[sig] = { sig, pattern: patterns[sig] || null, investigations: [] };
        groups[sig].investigations.push(inv);
    }

    for (const group of Object.values(groups)) {
        const { pattern, investigations: invs } = group;
        group.category = (pattern && pattern.category) || invCat(invs[0]);
        group.title = (pattern && pattern.title) || invTitle(invs[0], patterns);
        invs.sort((a, b) => String(invTime(b)).localeCompare(String(invTime(a))));
    }

    const byCat = {};
    for (const group of Object.values(groups)) {
        (byCat[group.category] = byCat[group.category] || []).push(group);
    }
    for (const list of Object.values(byCat)) {
        list.sort((a, b) =>
            b.investigations.length - a.investigations.length || a.title.localeCompare(b.title));
    }

    return { groups, byCat, patterns, investigations };
}
