/**
 * ============================================================
 * CleanSpot - Report Page JavaScript
 * ============================================================
 *
 * Keeps:
 *  - Camera
 *  - Upload
 *  - Preview
 *  - GPS
 *  - Leaflet map
 *  - Google Maps
 *  - YOLO analysis
 *  - Annotated image
 *  - Simple detection count
 *  - Report token
 *  - Gmail submission
 *
 * Individual confidence values are NOT displayed.
 */

document.addEventListener("DOMContentLoaded", () => {


    /* =========================================================
       ELEMENTS
    ========================================================= */

    const imageInput =
        document.getElementById("imageInput");

    const openCameraBtn =
        document.getElementById("openCameraBtn");

    const uploadPhotoBtn =
        document.getElementById("uploadPhotoBtn");

    const photoButtons =
        document.getElementById("photoButtons");


    const imagePreviewWrapper =
        document.getElementById("imagePreviewWrapper");

    const imagePreview =
        document.getElementById("imagePreview");

    const retakeBtn =
        document.getElementById("retakeBtn");


    const locationStatus =
        document.getElementById("locationStatus");

    const locationCoords =
        document.getElementById("locationCoords");

    const mapsLink =
        document.getElementById("mapsLink");

    const refreshLocationBtn =
        document.getElementById("refreshLocationBtn");


    const mapElement =
        document.getElementById("map");

    const mapLoading =
        document.getElementById("mapLoading");


    const aiSection =
        document.getElementById("aiSection");

    const aiAnalyzing =
        document.getElementById("aiAnalyzing");

    const aiAnalyzingText =
        document.getElementById("aiAnalyzingText");

    const aiResults =
        document.getElementById("aiResults");

    const annotatedImage =
        document.getElementById("annotatedImage");

    const aiSummaryLabel =
        document.getElementById("aiSummaryLabel");

    const aiDetectionList =
        document.getElementById("aiDetectionList");

    const aiNote =
        document.getElementById("aiNote");


    const messageBox =
        document.getElementById("messageBox");

    const sendReportBtn =
        document.getElementById("sendReportBtn");


    /* =========================================================
       STATE
    ========================================================= */

    let currentLocation = null;

    let currentReportToken = null;

    let analysisInFlight = false;

    let locationInFlight = false;

    let cleanSpotMap = null;

    let currentMarker = null;

    let accuracyCircle = null;


    /* =========================================================
       MAP LOADING
    ========================================================= */

    function setMapLoading(
        visible,
        message = "Finding your location..."
    ) {

        if (!mapLoading) return;

        const text =
            mapLoading.querySelector("span");

        if (text) {
            text.textContent = message;
        }

        mapLoading.classList.toggle(
            "hidden",
            !visible
        );
    }


    /* =========================================================
       MAP INITIALIZATION
    ========================================================= */

    function initializeMap() {

        if (!mapElement) return;


        if (typeof L === "undefined") {

            console.warn(
                "Leaflet is not available."
            );

            setMapLoading(false);

            return;
        }


        try {

            cleanSpotMap =
                L.map(
                    mapElement,
                    {
                        zoomControl: true,
                        attributionControl: true,
                        scrollWheelZoom: true
                    }
                ).setView(
                    [12.9716, 77.5946],
                    13
                );


            L.tileLayer(
                "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                {
                    maxZoom: 19,

                    attribution:
                        "&copy; OpenStreetMap contributors"
                }
            ).addTo(
                cleanSpotMap
            );


            setTimeout(() => {

                if (cleanSpotMap) {

                    cleanSpotMap.invalidateSize();

                }

            }, 250);


        } catch (error) {

            console.error(
                "Map initialization failed:",
                error
            );

            setMapLoading(false);

        }

    }


    /* =========================================================
       UPDATE MAP
    ========================================================= */

    function updateMapLocation(
        latitude,
        longitude,
        accuracy
    ) {

        if (!cleanSpotMap) return;


        const position = [
            latitude,
            longitude
        ];


        cleanSpotMap.setView(
            position,
            16,
            {
                animate: true
            }
        );


        if (currentMarker) {

            currentMarker.setLatLng(
                position
            );

        } else {

            currentMarker =
                L.marker(
                    position,
                    {
                        title:
                            "Your current location"
                    }
                ).addTo(
                    cleanSpotMap
                );

        }


        currentMarker
            .bindPopup(
                "<strong>📍 Your current location</strong>"
            )
            .openPopup();


        if (
            accuracy &&
            Number.isFinite(accuracy)
        ) {

            if (accuracyCircle) {

                accuracyCircle.setLatLng(
                    position
                );

                accuracyCircle.setRadius(
                    accuracy
                );

            } else {

                accuracyCircle =
                    L.circle(
                        position,
                        {
                            radius: accuracy,

                            color:
                                "#2f9b63",

                            fillColor:
                                "#63c174",

                            fillOpacity:
                                0.12,

                            weight: 1
                        }
                    ).addTo(
                        cleanSpotMap
                    );

            }

        }


        setTimeout(() => {

            if (cleanSpotMap) {

                cleanSpotMap.invalidateSize();

            }

        }, 150);

    }


    /* =========================================================
       CAMERA
    ========================================================= */

    if (
        openCameraBtn &&
        imageInput
    ) {

        openCameraBtn.addEventListener(
            "click",
            () => {

                imageInput.setAttribute(
                    "capture",
                    "environment"
                );

                imageInput.click();

            }
        );

    }


    /* =========================================================
       UPLOAD
    ========================================================= */

    if (
        uploadPhotoBtn &&
        imageInput
    ) {

        uploadPhotoBtn.addEventListener(
            "click",
            () => {

                imageInput.removeAttribute(
                    "capture"
                );

                imageInput.click();

            }
        );

    }


    /* =========================================================
       IMAGE SELECTED
    ========================================================= */

    if (imageInput) {

        imageInput.addEventListener(
            "change",
            () => {

                const file =
                    imageInput.files &&
                    imageInput.files[0];


                if (!file) return;


                if (
                    !file.type.startsWith(
                        "image/"
                    )
                ) {

                    showMessage(
                        "⚠️ Please select a valid image.",
                        "error"
                    );

                    imageInput.value = "";

                    return;
                }


                /* Preview */

                const reader =
                    new FileReader();


                reader.onload =
                    (event) => {

                        if (imagePreview) {

                            imagePreview.src =
                                event.target.result;

                        }

                    };


                reader.readAsDataURL(
                    file
                );


                if (imagePreviewWrapper) {

                    imagePreviewWrapper
                        .classList
                        .remove("hidden");

                }


                if (photoButtons) {

                    photoButtons
                        .classList
                        .add("hidden");

                }


                resetAiResults();


                currentReportToken =
                    null;


                updateSubmitButtonState();


                analyzeImage(file);

            }
        );

    }


    /* =========================================================
       RETAKE / CHOOSE ANOTHER
    ========================================================= */

    if (retakeBtn) {

        retakeBtn.addEventListener(
            "click",
            () => {

                if (imageInput) {

                    imageInput.value = "";

                }


                if (imagePreview) {

                    imagePreview.src = "";

                }


                if (imagePreviewWrapper) {

                    imagePreviewWrapper
                        .classList
                        .add("hidden");

                }


                if (photoButtons) {

                    photoButtons
                        .classList
                        .remove("hidden");

                }


                resetAiResults();


                currentReportToken =
                    null;


                clearMessage();


                updateSubmitButtonState();

            }
        );

    }


    /* =========================================================
       GPS
    ========================================================= */

    function detectLocation() {

        if (locationInFlight) return;


        locationInFlight = true;

        currentLocation = null;


        if (locationStatus) {

            locationStatus.textContent =
                "📍 Finding your current location...";

        }


        if (locationCoords) {

            locationCoords.textContent = "";

            locationCoords
                .classList
                .add("hidden");

        }


        if (mapsLink) {

            mapsLink
                .classList
                .add("hidden");

            mapsLink.removeAttribute(
                "href"
            );

        }


        setMapLoading(
            true,
            "Finding your location..."
        );


        updateSubmitButtonState();


        if (
            !("geolocation" in navigator)
        ) {

            locationInFlight = false;

            setMapLoading(
                false,
                "Location unavailable"
            );


            if (locationStatus) {

                locationStatus.textContent =
                    "⚠️ Your browser does not support location.";

            }


            updateSubmitButtonState();

            return;
        }


        navigator.geolocation.getCurrentPosition(

            (position) => {

                const latitude =
                    position.coords.latitude;

                const longitude =
                    position.coords.longitude;

                const accuracy =
                    position.coords.accuracy;


                currentLocation = {

                    latitude,

                    longitude,

                    accuracy

                };


                updateMapLocation(
                    latitude,
                    longitude,
                    accuracy
                );


                if (locationStatus) {

                    locationStatus.textContent =
                        "📍 Your current location";

                }


                if (locationCoords) {

                    locationCoords.textContent =
                        `Lat ${latitude.toFixed(6)}  •  Lng ${longitude.toFixed(6)}`;

                    locationCoords
                        .classList
                        .remove("hidden");

                }


                if (mapsLink) {

                    mapsLink.href =
                        `https://www.google.com/maps?q=${latitude},${longitude}`;

                    mapsLink
                        .classList
                        .remove("hidden");

                }


                setMapLoading(false);


                locationInFlight = false;


                updateSubmitButtonState();

            },


            (error) => {

                console.error(
                    "Geolocation error:",
                    error
                );


                currentLocation = null;

                locationInFlight = false;


                setMapLoading(
                    false,
                    "Location unavailable"
                );


                if (locationStatus) {

                    if (
                        error.code ===
                        error.PERMISSION_DENIED
                    ) {

                        locationStatus.textContent =
                            "⚠️ Location permission is required to submit a report.";

                    }

                    else if (
                        error.code ===
                        error.POSITION_UNAVAILABLE
                    ) {

                        locationStatus.textContent =
                            "⚠️ Your location is currently unavailable. Try again.";

                    }

                    else if (
                        error.code ===
                        error.TIMEOUT
                    ) {

                        locationStatus.textContent =
                            "⚠️ Location request timed out. Try again.";

                    }

                    else {

                        locationStatus.textContent =
                            "⚠️ Unable to detect your location. Please try again.";

                    }

                }


                updateSubmitButtonState();

            },


            {
                enableHighAccuracy: true,

                timeout: 15000,

                maximumAge: 0
            }

        );

    }


    /* =========================================================
       INITIALIZE LOCATION
    ========================================================= */

    initializeMap();

    detectLocation();


    if (refreshLocationBtn) {

        refreshLocationBtn.addEventListener(
            "click",
            detectLocation
        );

    }


    /* =========================================================
       AI LOADING MESSAGES
    ========================================================= */

    const ANALYSIS_MESSAGES = [

        "Analyzing image...",

        "Detecting visible waste...",

        "Identifying waste items...",

        "Preparing your report..."

    ];


    /* =========================================================
       RESET AI
    ========================================================= */

    function resetAiResults() {

        if (aiSection) {

            aiSection
                .classList
                .add("hidden");

        }


        if (aiAnalyzing) {

            aiAnalyzing
                .classList
                .add("hidden");

        }


        if (aiResults) {

            aiResults
                .classList
                .add("hidden");

        }


        if (annotatedImage) {

            annotatedImage
                .classList
                .add("hidden");

            annotatedImage
                .removeAttribute("src");

        }


        if (aiDetectionList) {

            aiDetectionList.innerHTML = "";

            aiDetectionList
                .classList
                .add("hidden");

        }


        if (aiSummaryLabel) {

            aiSummaryLabel.textContent =
                "";

        }


        if (aiNote) {

            aiNote
                .classList
                .add("hidden");

            aiNote.textContent =
                "";

        }

    }


    /* =========================================================
       ANALYZE IMAGE
    ========================================================= */

    async function analyzeImage(file) {

        clearMessage();


        if (!file) return;


        if (aiSection) {

            aiSection
                .classList
                .remove("hidden");

        }


        if (aiAnalyzing) {

            aiAnalyzing
                .classList
                .remove("hidden");

        }


        if (aiResults) {

            aiResults
                .classList
                .add("hidden");

        }


        analysisInFlight = true;

        currentReportToken = null;


        updateSubmitButtonState();


        let messageIndex = 0;


        if (aiAnalyzingText) {

            aiAnalyzingText.textContent =
                ANALYSIS_MESSAGES[0];

        }


        const messageInterval =
            setInterval(
                () => {

                    messageIndex =
                        (
                            messageIndex + 1
                        ) %
                        ANALYSIS_MESSAGES.length;


                    if (aiAnalyzingText) {

                        aiAnalyzingText.textContent =
                            ANALYSIS_MESSAGES[
                                messageIndex
                            ];

                    }

                },
                700
            );


        const formData =
            new FormData();


        formData.append(
            "image",
            file
        );


        try {

            const response =
                await fetch(
                    "/analyze-image",
                    {
                        method: "POST",
                        body: formData
                    }
                );


            let data;


            try {

                data =
                    await response.json();

            } catch (error) {

                throw new Error(
                    `Server returned an invalid response (${response.status}).`
                );

            }


            if (
                !response.ok ||
                !data.success
            ) {

                showMessage(
                    data.message ||
                        "⚠️ Something went wrong while analyzing the image.",
                    "error"
                );


                currentReportToken =
                    null;


                return;
            }


            currentReportToken =
                data.report_token;


            renderAiResults(data);


        }

        catch (error) {

            console.error(
                "Image analysis error:",
                error
            );


            showMessage(
                "⚠️ Could not reach the server to analyze the image. Please try again.",
                "error"
            );


            currentReportToken =
                null;

        }

        finally {

            clearInterval(
                messageInterval
            );


            if (aiAnalyzing) {

                aiAnalyzing
                    .classList
                    .add("hidden");

            }


            analysisInFlight =
                false;


            updateSubmitButtonState();

        }

    }


    /* =========================================================
       RENDER AI RESULT
    ========================================================= */

    function renderAiResults(data) {

        if (!aiResults) return;


        aiResults
            .classList
            .remove("hidden");


        if (
            data.annotated_image_url &&
            annotatedImage
        ) {

            annotatedImage.src =
                data.annotated_image_url;


            annotatedImage
                .classList
                .remove("hidden");

        }


        const detections =
            Array.isArray(
                data.detections
            )
                ? data.detections
                : [];


        if (aiSummaryLabel) {

            if (detections.length > 0) {

                aiSummaryLabel.textContent =
                    `♻️ ${detections.length} waste items detected`;

            }

            else {

                aiSummaryLabel.textContent =
                    "♻️ No waste confidently detected";

            }

        }


        if (aiDetectionList) {

            aiDetectionList.innerHTML =
                "";

            aiDetectionList
                .classList
                .add("hidden");

        }


        if (aiNote) {

            if (data.message) {

                aiNote.textContent =
                    data.message;

                aiNote
                    .classList
                    .remove("hidden");

            }

            else {

                aiNote
                    .classList
                    .add("hidden");

                aiNote.textContent =
                    "";

            }

        }

    }


    /* =========================================================
       MESSAGES
    ========================================================= */

    function showMessage(
        text,
        type
    ) {

        if (!messageBox) return;


        messageBox.textContent =
            text;


        messageBox.className =
            `message-box ${type}`;


        messageBox
            .classList
            .remove("hidden");

    }


    function clearMessage() {

        if (!messageBox) return;


        messageBox
            .classList
            .add("hidden");


        messageBox.textContent =
            "";

    }


    /* =========================================================
       SUBMIT BUTTON STATE
    ========================================================= */

    function updateSubmitButtonState() {

        if (!sendReportBtn) return;


        const hasImage =
            !!(
                imageInput &&
                imageInput.files &&
                imageInput.files.length
            );


        const ready =
            hasImage &&
            !!currentLocation &&
            !!currentReportToken &&
            !analysisInFlight &&
            !locationInFlight;


        sendReportBtn.disabled =
            !ready;

    }


    /* =========================================================
       SUBMIT REPORT
    ========================================================= */

    if (sendReportBtn) {

        sendReportBtn.addEventListener(
            "click",
            async () => {

                clearMessage();


                if (
                    !imageInput ||
                    !imageInput.files[0]
                ) {

                    showMessage(
                        "⚠️ Please capture or select a garbage image.",
                        "error"
                    );

                    return;
                }


                if (!currentLocation) {

                    showMessage(
                        "⚠️ Unable to detect your location. Please try again.",
                        "error"
                    );

                    return;
                }


                if (!currentReportToken) {

                    showMessage(
                        "⚠️ Please wait for image analysis to finish before submitting.",
                        "error"
                    );

                    return;
                }


                const formData =
                    new FormData();


                formData.append(
                    "report_token",
                    currentReportToken
                );


                formData.append(
                    "latitude",
                    currentLocation.latitude
                );


                formData.append(
                    "longitude",
                    currentLocation.longitude
                );


                sendReportBtn.disabled =
                    true;


                const originalHTML =
                    sendReportBtn.innerHTML;


                sendReportBtn.innerHTML =
                    "⏳ Sending Report...";


                try {

                    const response =
                        await fetch(
                            "/submit-report",
                            {
                                method: "POST",
                                body: formData
                            }
                        );


                    let data;


                    try {

                        data =
                            await response.json();

                    }

                    catch (error) {

                        throw new Error(
                            `Invalid server response (${response.status}).`
                        );

                    }


                    if (
                        response.ok &&
                        data.success
                    ) {

                        showMessage(
                            data.message ||
                                "✅ Your report has been sent successfully.",
                            "success"
                        );


                        /*
                         * Clear the report after successful
                         * submission.
                         */

                        if (retakeBtn) {

                            retakeBtn.click();

                        }

                    }

                    else {

                        showMessage(
                            data.message ||
                                "⚠️ Your report could not be sent. Please try again.",
                            "error"
                        );

                    }


                }

                catch (error) {

                    console.error(
                        "Submit error:",
                        error
                    );


                    showMessage(
                        "⚠️ Could not reach the server. Please check your connection and try again.",
                        "error"
                    );

                }

                finally {

                    sendReportBtn.innerHTML =
                        originalHTML;


                    updateSubmitButtonState();

                }

            }
        );

    }


    /* =========================================================
       INITIAL STATE
    ========================================================= */

    updateSubmitButtonState();

});
