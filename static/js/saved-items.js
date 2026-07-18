(() => {
    const storageKey = "mednearby_saved_items";
    const emptyState = () => ({ doctors: [], businesses: [] });

    const slugFromLegacyItem = item => {
        if (typeof item === "string") return item;
        if (typeof item?.slug === "string") return item.slug;
        if (typeof item?.url === "string") return item.url.split("/").filter(Boolean).pop() || "";
        return "";
    };

    const read = () => {
        try {
            const value = JSON.parse(localStorage.getItem(storageKey));
            const normalized = {
                doctors: Array.isArray(value?.doctors) ? [...new Set(value.doctors.map(slugFromLegacyItem).filter(Boolean))] : [],
                businesses: Array.isArray(value?.businesses) ? [...new Set(value.businesses.map(slugFromLegacyItem).filter(Boolean))] : [],
            };
            if (JSON.stringify(value) !== JSON.stringify(normalized)) write(normalized);
            return normalized;
        } catch (_) {
            return emptyState();
        }
    };

    const write = value => {
        try {
            localStorage.setItem(storageKey, JSON.stringify(value));
            return true;
        } catch (_) {
            return false;
        }
    };

    const collectionName = type => type === "doctor" ? "doctors" : "businesses";
    const isSaved = (type, slug, state = read()) => state[collectionName(type)].includes(slug);

    const updateButton = (button, state = read()) => {
        const saved = isSaved(button.dataset.saveType, button.dataset.saveSlug, state);
        button.setAttribute("aria-pressed", String(saved));
        button.setAttribute("aria-label", `${saved ? "Remove" : "Save"} ${button.dataset.saveName || "item"}`);
        const icon = button.querySelector("i");
        icon?.classList.toggle("fa-regular", !saved);
        icon?.classList.toggle("fa-solid", saved);
        button.classList.toggle("text-rose-500", saved);
    };

    const refresh = root => {
        const state = read();
        (root || document).querySelectorAll("[data-save-item]").forEach(button => updateButton(button, state));
    };

    document.addEventListener("click", event => {
        const button = event.target.closest("[data-save-item]");
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();

        const type = button.dataset.saveType;
        const slug = button.dataset.saveSlug;
        if (!slug || !["doctor", "business"].includes(type)) return;
        const state = read();
        const collection = collectionName(type);
        const index = state[collection].indexOf(slug);
        if (index >= 0) {
            state[collection].splice(index, 1);
        } else {
            state[collection].unshift(slug);
        }
        if (write(state)) {
            refresh(document);
            document.dispatchEvent(new CustomEvent("saved-items:changed", { detail: state }));
        }
    });

    window.MedNearbySaved = { read, refresh };
    document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", () => refresh(document)) : refresh(document);
})();
