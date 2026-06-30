// Live text filtering and expand/collapse controls.

export function applySearch(query) {
    const q = query.trim().toLowerCase();

    document.querySelectorAll(".cat").forEach(catEl => {
        let categoryHasMatch = false;

        catEl.querySelectorAll(".group").forEach(groupEl => {
            let groupHasMatch = false;

            groupEl.querySelectorAll(".inv").forEach(invEl => {
                const match = !q || (invEl.dataset.search || "").includes(q);
                invEl.classList.toggle("hidden", !match);
                if (match) groupHasMatch = true;
            });

            const groupMatch = !q || (groupEl.dataset.search || "").includes(q) || groupHasMatch;
            groupEl.classList.toggle("hidden", !groupMatch);
            groupEl.classList.toggle("open", !!q && groupMatch);
            if (groupMatch) categoryHasMatch = true;
        });

        catEl.classList.toggle("hidden", !categoryHasMatch);
        catEl.classList.toggle("open", !!q && categoryHasMatch);
    });
}

export function setAll(open) {
    document.querySelectorAll(".cat, .group, .inv").forEach(el => el.classList.toggle("open", open));
}
