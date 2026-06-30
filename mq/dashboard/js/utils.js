// Small, dependency-free helpers shared across modules.

// Escape a value for safe insertion into HTML.
export const esc = value =>
    String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;",
    }[ch]));

// Coerce a value into an array (null/undefined -> []).
export function asList(value) {
    if (Array.isArray(value)) return value;
    return value == null ? [] : [value];
}

// Format an ISO timestamp as YYYY-MM-DD, falling back to the raw value.
export const fmtDay = ts => {
    try {
        return new Date(ts).toISOString().slice(0, 10);
    } catch {
        return ts;
    }
};
