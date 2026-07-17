(() => {
    document.addEventListener("click", event => {
        const backButton = event.target.closest("[data-back-button]");
        if (!backButton) return;

        event.preventDefault();

        if (window.history.length > 1) {
            window.history.back();
            return;
        }

        window.location.assign(backButton.href);
    });
})();
