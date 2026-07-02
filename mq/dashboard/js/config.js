// Configuration: data locations and category color mapping.

export const INV_DIR = "../investigations";
export const PAT_DIR = "../patterns";

// Maps a failure category to its CSS custom property (defined in dashboard.css).
// Category names match the enum in schemas/investigation.schema.json and
// schemas/pattern.schema.json.
const CATEGORY_COLORS = {
    "Code Issue": "var(--cat-code)",
    "Infrastructure": "var(--cat-infra)",
    "Dependencies": "var(--cat-deps)",
    "Configuration": "var(--cat-config)",
    "Flaky Test": "var(--cat-flaky)",
    "External Service": "var(--cat-external)",
    "Network": "var(--cat-network)",
};

export function catColor(category) {
    return CATEGORY_COLORS[category] || "var(--cat-other)";
}
