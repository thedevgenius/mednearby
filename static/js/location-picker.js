(() => {
    const sheet = document.getElementById("location-sheet");
    if (!sheet || sheet.dataset.locationPickerInitialized) return;
    sheet.dataset.locationPickerInitialized = "true";

    const STORAGE_KEY = "mednearby_selected_locality";
    const LAT_COOKIE = "mednearby_location_lat";
    const LNG_COOKIE = "mednearby_location_lng";
    const pickerName = document.getElementById("selected-location-name");
    const input = document.getElementById("locality-search");
    const results = document.getElementById("locality-search-results");
    const currentButton = document.getElementById("use-current-location");
    const currentLabel = currentButton.querySelector("span");
    const status = document.getElementById("location-status");
    let timer;
    let controller;

    const showStatus = (message, error = false) => {
        status.textContent = message;
        status.classList.toggle("hidden", !message);
        status.classList.toggle("text-red-600", error);
        status.classList.toggle("text-textMuted", !error);
    };

    const setCookie = (key, value) => {
        const secure = location.protocol === "https:" ? "; Secure" : "";
        document.cookie = `${key}=${encodeURIComponent(value)}; Max-Age=31536000; Path=/; SameSite=Lax${secure}`;
    };

    const getCookie = (key) => {
        const prefix = `${key}=`;
        const cookie = document.cookie
            .split(";")
            .map((item) => item.trim())
            .find((item) => item.startsWith(prefix));
        return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
    };

    const hasSavedCoordinates = () => {
        const savedLatitude = getCookie(LAT_COOKIE);
        const savedLongitude = getCookie(LNG_COOKIE);
        if (savedLatitude === null || savedLongitude === null) return false;
        const latitude = Number(savedLatitude);
        const longitude = Number(savedLongitude);
        return (
            Number.isFinite(latitude)
            && Number.isFinite(longitude)
            && latitude >= -90
            && latitude <= 90
            && longitude >= -180
            && longitude <= 180
        );
    };

    const saveLocality = (locality, updateCoordinateCookies = true) => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(locality));
        } catch (error) {
            // Continue when browser storage is unavailable.
        }
        if (pickerName) pickerName.textContent = locality.display_name;
        if (updateCoordinateCookies && locality.lat != null && locality.lng != null) {
            setCookie(LAT_COOKIE, locality.lat);
            setCookie(LNG_COOKIE, locality.lng);
        }
        document.dispatchEvent(new CustomEvent("location:selected", { detail: locality }));
    };

    const restoreLocality = () => {
        try {
            const locality = JSON.parse(localStorage.getItem(STORAGE_KEY));
            if (locality?.display_name && locality.lat != null && locality.lng != null) {
                if (pickerName) pickerName.textContent = locality.display_name;
            } else if (locality) {
                localStorage.removeItem(STORAGE_KEY);
            }
        } catch (error) {
            // Ignore unavailable or malformed browser storage.
        }
    };

    const createResult = (locality) => {
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("role", "option");
        button.className = "flex w-full items-center gap-3 px-1 py-3 text-left hover:bg-gray-50";

        const icon = document.createElement("span");
        icon.className = "grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-50 text-primary";
        icon.innerHTML = '<i class="fa-solid fa-location-dot" aria-hidden="true"></i>';
        const text = document.createElement("span");
        text.className = "min-w-0 flex-1";
        const name = document.createElement("strong");
        name.className = "block truncate text-sm text-textMain";
        name.textContent = locality.name;
        const context = document.createElement("small");
        context.className = "block truncate text-xs text-textMuted";
        context.textContent = `${locality.city}, ${locality.state}`;
        text.append(name, context);
        button.append(icon, text);
        button.addEventListener("click", () => {
            if (locality.lat == null || locality.lng == null) {
                showStatus("Coordinates are unavailable for this locality.", true);
                return;
            }
            saveLocality(locality);
            closeBottomSheet("location-sheet");
        });
        return button;
    };

    const search = async () => {
        const query = input.value.trim();
        controller?.abort();
        results.replaceChildren();
        if (query.length < 3) {
            showStatus(query ? "Enter at least 3 characters." : "");
            return;
        }

        controller = new AbortController();
        const url = new URL(sheet.dataset.searchUrl, location.origin);
        url.searchParams.set("q", query);
        showStatus("Searching…");
        try {
            const response = await fetch(url, { signal: controller.signal });
            if (!response.ok) throw new Error("Search failed");
            const data = await response.json();
            if (query !== input.value.trim()) return;
            results.append(...data.results.map(createResult));
            showStatus(data.results.length ? "" : "No matching localities found.");
        } catch (error) {
            if (error.name !== "AbortError") showStatus("Unable to search locations right now.", true);
        }
    };

    const findNearest = async (latitude, longitude, showFeedback) => {
        setCookie(LAT_COOKIE, latitude);
        setCookie(LNG_COOKIE, longitude);
        const url = new URL(sheet.dataset.nearestUrl, location.origin);
        url.searchParams.set("lat", latitude);
        url.searchParams.set("lng", longitude);
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error("Lookup failed");
            const data = await response.json();
            if (!data.result) throw new Error("No locality found");
            // Keep the exact browser coordinates already written above. The
            // database locality is used only as the selected display location.
            saveLocality(data.result, false);
            showStatus("");
            if (showFeedback) closeBottomSheet("location-sheet");
        } catch (error) {
            if (showFeedback) showStatus("We could not find a locality near those coordinates.", true);
        }
    };

    const requestCurrentLocation = (showFeedback = true) => {
        if (!navigator.geolocation) {
            if (showFeedback) showStatus("Location is not supported by this browser.", true);
            return;
        }
        currentButton.disabled = true;
        currentLabel.textContent = "Finding your location…";
        navigator.geolocation.getCurrentPosition(
            (position) => {
                findNearest(position.coords.latitude, position.coords.longitude, showFeedback)
                    .finally(() => {
                        currentButton.disabled = false;
                        currentLabel.textContent = "Use current location";
                    });
            },
            () => {
                currentButton.disabled = false;
                currentLabel.textContent = "Use current location";
                if (showFeedback) showStatus("Location permission was denied or unavailable.", true);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
        );
    };

    input.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(search, 250);
    });
    currentButton.addEventListener("click", () => requestCurrentLocation(true));
    restoreLocality();
    if (!hasSavedCoordinates()) requestCurrentLocation(false);
})();
