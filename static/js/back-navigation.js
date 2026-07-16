(() => {
    document.addEventListener("click", event => {
        const backButton = event.target.closest("[data-back-button]");
        if (!backButton) return;

        event.preventDefault();

        if (document.referrer) {
            try {
                const previousUrl = new URL(document.referrer);
                if (previousUrl.origin === window.location.origin) {
                    window.history.back();
                    return;
                }
            } catch (error) {
                // Use the button's home fallback for an invalid referrer.
            }
        }

        window.location.assign(backButton.href);
    });
})();
