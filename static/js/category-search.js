(() => {
    const sheet = document.getElementById("search-sheet");
    if (!sheet || sheet.dataset.searchInitialized) return;
    sheet.dataset.searchInitialized = "true";

    const input = document.getElementById("global-category-search");
    const results = document.getElementById("global-category-search-results");
    const status = document.getElementById("global-category-search-status");
    let timer;
    let controller;

    const showStatus = (message, error = false) => {
        status.textContent = message;
        status.classList.toggle("hidden", !message);
        status.classList.toggle("text-red-600", error);
        status.classList.toggle("text-textMuted", !error);
    };

    const createResult = (item) => {
        const link = document.createElement("a");
        link.href = item.url;
        link.setAttribute("role", "option");
        link.className = "flex items-center gap-3 border-b border-gray-100 px-3 py-3 transition-colors last:border-b-0 hover:bg-gray-50";

        const iconBox = document.createElement("span");
        iconBox.className = "flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600";
        const icon = document.createElement("i");
        icon.className = item.icon || (item.type === "specialty" ? "fa-solid fa-user-doctor" : "fa-solid fa-store");
        iconBox.appendChild(icon);

        const text = document.createElement("span");
        text.className = "min-w-0 flex-1";
        const name = document.createElement("strong");
        name.className = "block truncate text-sm font-extrabold text-textMain";
        name.textContent = item.type === "specialty" && item.synonyms
            ? `${item.label} (${item.synonyms})`
            : item.label;
        const type = document.createElement("small");
        type.className = "block text-xs font-semibold text-textMuted";
        type.textContent = item.type_label;
        text.append(name, type);

        const arrow = document.createElement("i");
        arrow.className = "fa-solid fa-arrow-right text-xs text-gray-300";
        link.append(iconBox, text, arrow);
        return link;
    };

    const search = async () => {
        const query = input.value.trim();
        controller?.abort();
        results.replaceChildren();
        if (!query) {
            showStatus("");
            return;
        }

        controller = new AbortController();
        const url = new URL(sheet.dataset.searchUrl, location.origin);
        url.searchParams.set("q", query);
        showStatus("Searching...");
        try {
            const response = await fetch(url, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                signal: controller.signal,
            });
            if (!response.ok) throw new Error("Search failed");
            const data = await response.json();
            if (query !== input.value.trim()) return;
            if (data.results.length) {
                results.classList.remove("hidden");
                results.append(...data.results.map(createResult));
                showStatus("");
            } else {
                showStatus("No matching categories found.");
            }
        } catch (error) {
            if (error.name !== "AbortError") showStatus("Unable to search right now.", true);
        }
    };

    input.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(search, 250);
    });
    results.addEventListener("click", event => {
        if (!event.target.closest("a")) return;
        window.closeBottomSheet?.(sheet);
    });
    sheet.addEventListener("bottomsheet:open", () => {
        requestAnimationFrame(() => {
            input.focus({ preventScroll: true });
        });
        if (!input.value.trim()) showStatus("");
    });
    sheet.addEventListener("bottomsheet:close", () => {
        clearTimeout(timer);
        controller?.abort();
        controller = null;
        input.value = "";
        results.replaceChildren();
        results.classList.add("hidden");
        showStatus("");
    });
})();
