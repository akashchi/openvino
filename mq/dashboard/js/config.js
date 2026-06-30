// Configuration: data locations and category color mapping.

export const INV_DIR = "../investigations";
export const PAT_DIR = "../patterns";

// Maps a failure category to its CSS custom property (defined in dashboard.css).
const CATEGORY_COLORS = {
    "Flaky Test": "var(--cat-flaky)",
    "Network": "var(--cat-network)",
    "Infrastructure": "var(--cat-infra)",
    "Code Issue": "var(--cat-code)",
};

export function catColor(category) {
    return CATEGORY_COLORS[category] || "var(--cat-other)";
}
