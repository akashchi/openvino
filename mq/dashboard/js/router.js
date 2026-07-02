// Minimal hash-based router. Two routes:
//   #/               -> Kanban board of category cards (home)
//   #/cat/<category> -> dedicated page for that category
// Hash routing keeps the app fully static (works on GitHub Pages).

import { renderBoard } from "./render-board.js";
import { renderCategoryPage, wireCategoryPage } from "./render-category-page.js";

function parseHash() {
    const raw = location.hash.replace(/^#\/?/, "");
    if (raw.startsWith("cat/")) {
        return { view: "category", category: decodeURIComponent(raw.slice(4)) };
    }
    return { view: "board" };
}

export function initRouter(model) {
    const app = document.getElementById("app");

    const render = () => {
        const route = parseHash();
        if (route.view === "category" && model.byCat[route.category]) {
            app.innerHTML = renderCategoryPage(model, route.category);
            wireCategoryPage();
        } else {
            app.innerHTML = renderBoard(model);
        }
        window.scrollTo(0, 0);
    };

    window.addEventListener("hashchange", render);
    render();
}
