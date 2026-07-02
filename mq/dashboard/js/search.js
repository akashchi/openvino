// Live text filtering and expand/collapse controls.
// Scope-agnostic: operates on whatever .group / .inv elements are on the page
// (the category page renders groups directly, with no .cat wrapper).

export function applySearch(query) {
    const q = query.trim().toLowerCase();

    document.querySelectorAll(".group").forEach(groupEl => {
        let groupHasMatch = false;

        groupEl.querySelectorAll(".inv").forEach(invEl => {
            const match = !q || (invEl.dataset.search || "").includes(q);
            invEl.classList.toggle("hidden", !match);
            if (match) groupHasMatch = true;
        });

        const groupMatch = !q || (groupEl.dataset.search || "").includes(q) || groupHasMatch;
        groupEl.classList.toggle("hidden", !groupMatch);
        groupEl.classList.toggle("open", !!q && groupMatch);
    });
}

export function setAll(open) {
    document.querySelectorAll(".group, .inv").forEach(el => el.classList.toggle("open", open));
}
