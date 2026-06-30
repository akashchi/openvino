// Shared badge/pill HTML snippets.

import { esc } from "./utils.js";
import { catColor } from "./config.js";

export function badgeCat(category) {
    return `<span class="badge cat" style="background:${catColor(category)}">${esc(category)}</span>`;
}
