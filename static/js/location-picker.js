(() => {
    const sheet = document.getElementById("location-sheet");
    if (!sheet || sheet.dataset.locationPickerInitialized) return;
    sheet.dataset.locationPickerInitialized = "true";

    const STORAGE_KEY = "mednearby_selected_locality";
    const LAST_LOCATION_SAVE_KEY = "mednearby_location_saved_at";
    const LAT_COOKIE = "mednearby_location_lat";
    const LNG_COOKIE = "mednearby_location_lng";
    const LOCATION_REFRESH_INTERVAL_MS = 15 * 60 * 1000;
    const LOCALITY_REFRESH_DISTANCE_METERS = 200;
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

    const getSavedCoordinates = () => {
        const savedLatitude = getCookie(LAT_COOKIE);
        const savedLongitude = getCookie(LNG_COOKIE);
        if (savedLatitude === null || savedLongitude === null) return null;
        const latitude = Number(savedLatitude);
        const longitude = Number(savedLongitude);
        const isValid = (
            Number.isFinite(latitude)
            && Number.isFinite(longitude)
            && latitude >= -90
            && latitude <= 90
            && longitude >= -180
            && longitude <= 180
        );
        return isValid ? { latitude, longitude } : null;
    };

    const saveLocationTimestamp = () => {
        try {
            localStorage.setItem(LAST_LOCATION_SAVE_KEY, String(Date.now()));
        } catch (error) {
            // Continue when browser storage is unavailable.
        }
    };

    const hasFreshSavedLocation = () => {
        if (!getSavedCoordinates()) return false;
        try {
            const savedAt = Number(localStorage.getItem(LAST_LOCATION_SAVE_KEY));
            const elapsed = Date.now() - savedAt;
            return (
                Number.isFinite(savedAt)
                && savedAt > 0
                && elapsed >= 0
                && elapsed < LOCATION_REFRESH_INTERVAL_MS
            );
        } catch (error) {
            return false;
        }
    };

    const distanceInMeters = (from, to) => {
        const earthRadiusMeters = 6371000;
        const toRadians = (degrees) => degrees * Math.PI / 180;
        const latitudeDelta = toRadians(to.latitude - from.latitude);
        const longitudeDelta = toRadians(to.longitude - from.longitude);
        const fromLatitude = toRadians(from.latitude);
        const toLatitude = toRadians(to.latitude);
        const haversine = (
            Math.sin(latitudeDelta / 2) ** 2
            + Math.cos(fromLatitude) * Math.cos(toLatitude)
            * Math.sin(longitudeDelta / 2) ** 2
        );
        return 2 * earthRadiusMeters * Math.asin(Math.sqrt(haversine));
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
            saveLocationTimestamp();
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

    const processCurrentCoordinates = (latitude, longitude, showFeedback) => {
        const savedCoordinates = getSavedCoordinates();
        const currentCoordinates = { latitude, longitude };

        // Always retain the latest device coordinates, even when the locality
        // is close enough that another backend lookup is unnecessary.
        setCookie(LAT_COOKIE, latitude);
        setCookie(LNG_COOKIE, longitude);

        const shouldRefreshLocality = (
            !savedCoordinates
            || distanceInMeters(savedCoordinates, currentCoordinates) > LOCALITY_REFRESH_DISTANCE_METERS
        );
        if (shouldRefreshLocality) {
            return findNearest(latitude, longitude, showFeedback);
        }

        showStatus("");
        document.dispatchEvent(new CustomEvent("location:coordinates-updated", {
            detail: currentCoordinates,
        }));
        if (showFeedback) closeBottomSheet("location-sheet");
        return Promise.resolve();
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
                saveLocationTimestamp();
                processCurrentCoordinates(position.coords.latitude, position.coords.longitude, showFeedback)
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
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    };

    input.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(search, 250);
    });
    currentButton.addEventListener("click", () => requestCurrentLocation(true));
    restoreLocality();
    if (!hasFreshSavedLocation()) requestCurrentLocation(false);
})();
