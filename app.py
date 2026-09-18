"""
CleanSpot - AI-Powered Garbage Reporting Platform (v2)
=======================================================

This builds on the original working prototype WITHOUT removing anything:
photo capture, GPS location, Google Maps link, and Gmail SMTP email with
an attached image all still work exactly as before.

New in v2:
    - YOLO (Ultralytics) detects waste categories in the uploaded photo,
      loaded ONCE at startup (not per-request), with class names read
      dynamically from whatever model file is placed in model/.
    - Gemini (Google AI Studio) writes a short, professional 2-line
      description of the report from the YOLO detections.
    - The report flow is now two steps instead of one:
        1. POST /analyze-image   -> runs YOLO, returns detections +
                                   an annotated (bounding-box) image,
                                   and a "report_token" for step 2.
        2. POST /submit-report   -> takes the report_token + GPS coords,
                                   asks Gemini for a description, and
                                   emails everything to the authority.
      This lets the UI show "AI ANALYSIS" results to the user BEFORE they
      commit to sending the report - matching the reporting experience in
      the smart report page.

Both AI components are OPTIONAL at runtime: if the YOLO weights file is
missing, or the Gemini API key isn't set, or either call fails, the app
keeps working and reports can still be submitted (with a safe fallback
description and no AI detections). Nothing about GPS or email changes.
"""

import os
import uuid
import smtplib
import time
import io
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# 1. Load configuration from the .env file
# ---------------------------------------------------------------------------

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# --- Email config (unchanged from v1) ---------------------------------------

SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
AUTHORITY_EMAIL = os.getenv("AUTHORITY_EMAIL")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


# --- YOLO config -------------------------------------------------------------

YOLO_MODEL_PATH = os.getenv(
    "YOLO_MODEL_PATH",
    "model/garbage_model.pt"
)

YOLO_CONFIDENCE_THRESHOLD = float(
    os.getenv("YOLO_CONFIDENCE_THRESHOLD", "0.45")
)


# --- Gemini config -----------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)


# ---------------------------------------------------------------------------
# 2. Basic Flask setup (unchanged from v1)
# ---------------------------------------------------------------------------

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit


def allowed_file(filename: str) -> bool:
    """Return True if the filename has an allowed image extension."""

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def is_valid_coordinate(value) -> bool:
    """Check that a value can be parsed as a number (latitude or longitude)."""

    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# 3. YOLO model loading - happens ONCE when Flask starts
# ---------------------------------------------------------------------------

yolo_model = None
yolo_class_names = {}
yolo_load_error = None


def load_yolo_model():
    """
    Loads the YOLO model from YOLO_MODEL_PATH exactly once at startup.

    Never raises - any failure just leaves yolo_model as None, and the rest
    of the app checks for that and degrades gracefully.
    """

    global yolo_model
    global yolo_class_names
    global yolo_load_error

    model_path = YOLO_MODEL_PATH

    if not os.path.isabs(model_path):
        model_path = os.path.join(BASE_DIR, model_path)

    if not os.path.exists(model_path):
        yolo_load_error = (
            f"YOLO model file not found at '{model_path}'. "
            f"Place your garbage-detection weights there "
            f"(see model/README.md) to enable AI detection. "
            f"Reports can still be submitted without it."
        )

        print(f"[SETUP NEEDED] {yolo_load_error}")
        return

    try:
        from ultralytics import YOLO

        model = YOLO(model_path)

        # Read the model's own class names rather than assuming
        # specific categories.
        yolo_class_names = model.names
        yolo_model = model

        print(f"[INFO] YOLO model loaded from '{model_path}'.")
        print(
            f"[INFO] Model classes: "
            f"{list(yolo_class_names.values())}"
        )

    except Exception as exc:
        yolo_load_error = (
            f"Failed to load YOLO model from "
            f"'{model_path}': {exc}"
        )

        print(f"[WARN] {yolo_load_error}")


load_yolo_model()


# ---------------------------------------------------------------------------
# 4. YOLO detection
# ---------------------------------------------------------------------------

def run_yolo_detection(image_path):
    """
    Runs YOLO detection on a saved image.

    Returns (detections, annotated_image_path):

        detections
            -> list of:
               {"label": str, "confidence": float}

               Confidence is returned as a 0-100 percentage.

        annotated_image_path
            -> absolute path to a saved image with bounding boxes,
               or None if there were no detections.

    Never raises - any inference failure is treated as "no detections".
    """

    if yolo_model is None:
        return [], None

    try:

        # IMPORTANT:
        # The standalone test showed that this waste scene is detected
        # correctly when using imgsz=1280.
        yolo_start = time.perf_counter()

        results = yolo_model.predict(
            source=image_path,
            conf=YOLO_CONFIDENCE_THRESHOLD,
            imgsz=1280,
            verbose=False
        )

        yolo_elapsed = time.perf_counter() - yolo_start
        print(f"[TIMING] YOLO detection: {yolo_elapsed:.2f} seconds")

        result = results[0]

        detections = []

        for box in result.boxes:

            class_id = int(box.cls[0])

            confidence_pct = round(
                float(box.conf[0]) * 100,
                1
            )

            label = yolo_class_names.get(
                class_id,
                f"class_{class_id}"
            )

            detections.append(
                {
                    "label": label,
                    "confidence": confidence_pct
                }
            )

        detections.sort(
            key=lambda d: d["confidence"],
            reverse=True
        )

        annotated_path = None

        if detections:

            # result.plot() returns a numpy BGR image
            # with bounding boxes and labels drawn.
            import cv2

            annotated_array = result.plot()

            annotated_filename = (
                f"annotated_{os.path.basename(image_path)}"
            )

            annotated_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                annotated_filename
            )

            cv2.imwrite(
                annotated_path,
                annotated_array
            )

        return detections, annotated_path

    except Exception as exc:
        print(
            f"[WARN] YOLO inference failed: {exc}"
        )

        return [], None


# ---------------------------------------------------------------------------
# 5. Gemini setup - generates the 2-line report description
# ---------------------------------------------------------------------------

gemini_client = None


if GEMINI_API_KEY:

    try:

        from google import genai

        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        print("[INFO] Gemini client initialized.")

    except Exception as exc:

        print(
            f"[WARN] Could not initialize Gemini client: {exc}"
        )

        gemini_client = None

else:

    print(
        "[INFO] GEMINI_API_KEY not set - "
        "AI descriptions will use a fallback message."
    )


FALLBACK_DESCRIPTION_WITH_DETECTIONS = (
    "Garbage has been reported at the specified location "
    "and requires attention.\n"
    "Please arrange an inspection and appropriate cleaning "
    "action at the earliest."
)


FALLBACK_DESCRIPTION_NO_DETECTIONS = (
    "A cleanliness issue has been reported at the specified "
    "location.\n"
    "Please arrange an inspection and appropriate action "
    "at the earliest."
)


def generate_ai_description(detections):
    """
    Asks Gemini for a professional, exactly-2-sentence description
    of the report based on YOLO's detections.

    Falls back to a safe generic message if Gemini isn't configured
    or the call fails.
    """

    fallback = (
        FALLBACK_DESCRIPTION_WITH_DETECTIONS
        if detections
        else FALLBACK_DESCRIPTION_NO_DETECTIONS
    )

    if gemini_client is None:
        return fallback

    labels_summary = (
        ", ".join(
            f"{d['label']} ({d['confidence']}% confidence)"
            for d in detections
        )
        if detections
        else
        "no specific waste type could be confidently identified"
    )

    prompt = (
        "Write exactly two short, professional sentences for a "
        "municipal cleanliness report email sent by a citizen "
        "reporting app to a local sanitation authority. "
        "Base the sentences only on the detected waste types "
        "listed below - do not invent or exaggerate anything. "
        "Do not mention AI, models, prompts, or confidence "
        "percentages in the sentences themselves. "
        "Do not use markdown, bullet points, or a greeting - "
        "just the two plain sentences.\n\n"
        f"Detected waste types: {labels_summary}\n\n"
        "Two sentences:"
    )

    try:

        gemini_start = time.perf_counter()

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=prompt
        )

        gemini_elapsed = time.perf_counter() - gemini_start
        print(f"[TIMING] Gemini description: {gemini_elapsed:.2f} seconds")

        text = (
            getattr(response, "text", None)
            or ""
        ).strip()

        return text if text else fallback

    except Exception as exc:

        print(
            f"[WARN] Gemini description generation failed: {exc}"
        )

        return fallback


# ---------------------------------------------------------------------------
# 6. In-memory pending-report store
# ---------------------------------------------------------------------------

# There's still no database, matching the prototype's original scope.
# We hold each analyzed-but-not-yet-submitted report in memory between
# /analyze-image and /submit-report.

PENDING_REPORTS = {}


# ---------------------------------------------------------------------------
# 7. Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    """Home / landing page."""

    return render_template("index.html")


@app.route("/report")
def report_page():
    """Reporting page."""

    return render_template("report.html")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """
    Serves saved images (originals + annotated)
    so the frontend can show them.
    """

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# ---------------------------------------------------------------------------
# 8. Step 1: POST /analyze-image
# ---------------------------------------------------------------------------

@app.route("/analyze-image", methods=["POST"])
def analyze_image():
    """
    Receives just the photo (multipart/form-data, field "image").

    Runs YOLO and returns:

        {
            success: true,
            report_token: "...",
            ai_available: true/false,
            detections: [
                {
                    label: "...",
                    confidence: ...
                }
            ],
            annotated_image_url: "/uploads/xyz.jpg",
            message: "..."
        }
    """

    if (
        "image" not in request.files
        or request.files["image"].filename == ""
    ):
        return jsonify(
            success=False,
            message="⚠️ Please capture or select a garbage image."
        ), 400

    image_file = request.files["image"]

    if not allowed_file(image_file.filename):

        return jsonify(
            success=False,
            message=(
                "⚠️ Invalid image format. "
                "Please use JPG, PNG, GIF, or WEBP."
            )
        ), 400

    # Never trust the client's filename directly.
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S%f"
    )

    safe_name = secure_filename(
        image_file.filename
    )

    saved_filename = (
        f"report_{timestamp}_{safe_name}"
    )

    saved_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        saved_filename
    )

    image_file.save(saved_path)

    # Run YOLO
    analysis_start = time.perf_counter()

    detections, annotated_path = run_yolo_detection(
        saved_path
    )

    # Generate the Gemini description NOW, while the user is already
    # waiting for AI analysis. This prevents Gemini from delaying
    # the final "Send Report" button.
    ai_description = generate_ai_description(
        detections
    )

    analysis_elapsed = time.perf_counter() - analysis_start
    print(
        f"[TIMING] Total /analyze-image processing: "
        f"{analysis_elapsed:.2f} seconds"
    )

    # Create token for step 2
    report_token = uuid.uuid4().hex

    PENDING_REPORTS[report_token] = {
        "original_path": saved_path,
        "annotated_path": annotated_path,
        "detections": detections,
        "ai_description": ai_description
    }

    response = {
        "success": True,
        "report_token": report_token,
        "ai_available": yolo_model is not None,
        "detections": detections,
        "ai_description": ai_description,
        "annotated_image_url": (
            f"/uploads/{os.path.basename(annotated_path)}"
            if annotated_path
            else None
        )
    }

    if yolo_model is None:

        response["message"] = (
            "AI analysis is temporarily unavailable. "
            "Your report can still be submitted."
        )

    elif not detections:

        response["message"] = (
            "No waste was confidently detected in this image. "
            "You can still submit the report, or try a clearer photo."
        )

    return jsonify(response), 200


# ---------------------------------------------------------------------------
# 9. Step 2: POST /submit-report
# ---------------------------------------------------------------------------

@app.route("/submit-report", methods=["POST"])
def submit_report():
    """
    Receives:

        report_token
        latitude
        longitude

    Uses the Gemini description that was already generated during
    /analyze-image, builds the email, sends it, and returns success/failure.
    """

    report_token = request.form.get(
        "report_token"
    )

    latitude = request.form.get(
        "latitude"
    )

    longitude = request.form.get(
        "longitude"
    )

    if (
        not report_token
        or report_token not in PENDING_REPORTS
    ):
        return jsonify(
            success=False,
            message="⚠️ Please capture or select a garbage image."
        ), 400

    if not latitude or not longitude:

        return jsonify(
            success=False,
            message=(
                "⚠️ Unable to detect your location. "
                "Please try again."
            )
        ), 400

    if (
        not is_valid_coordinate(latitude)
        or not is_valid_coordinate(longitude)
    ):

        return jsonify(
            success=False,
            message=(
                "⚠️ Location data looks invalid. "
                "Please refresh your location and try again."
            )
        ), 400

    lat_f = float(latitude)
    lng_f = float(longitude)

    if (
        not (-90 <= lat_f <= 90)
        or not (-180 <= lng_f <= 180)
    ):

        return jsonify(
            success=False,
            message=(
                "⚠️ Location data is out of range. "
                "Please refresh your location and try again."
            )
        ), 400

    report_data = PENDING_REPORTS[
        report_token
    ]

    detections = report_data[
        "detections"
    ]

    maps_link = (
        f"https://www.google.com/maps?"
        f"q={lat_f},{lng_f}"
    )

    now = datetime.now()

    date_str = now.strftime(
        "%d %B %Y"
    )

    time_str = now.strftime(
        "%I:%M %p"
    )

    # Gemini was already run during /analyze-image.
    # Reuse the saved description so clicking "Send Report"
    # does not wait for another Gemini API request.
    ai_description = report_data.get(
        "ai_description",
        (
            FALLBACK_DESCRIPTION_WITH_DETECTIONS
            if detections
            else FALLBACK_DESCRIPTION_NO_DETECTIONS
        )
    )

    try:

        email_start = time.perf_counter()

        send_report_email(
            original_image_path=report_data[
                "original_path"
            ],

            annotated_image_path=report_data[
                "annotated_path"
            ],

            detections=detections,

            ai_description=ai_description,

            latitude=lat_f,

            longitude=lng_f,

            maps_link=maps_link,

            date_str=date_str,

            time_str=time_str
        )

        email_elapsed = time.perf_counter() - email_start
        print(
            f"[TIMING] Email sending: "
            f"{email_elapsed:.2f} seconds"
        )

    except Exception as exc:

        print(
            f"[ERROR] Failed to send email: {exc}"
        )

        return jsonify(
            success=False,
            message=(
                "⚠️ Your report could not be sent. "
                "Please try again."
            )
        ), 500

    # The report has been emailed.
    PENDING_REPORTS.pop(
        report_token,
        None
    )

    return jsonify(
        success=True,
        message=(
            "✅ Garbage report submitted successfully! "
            "The report has been sent to the concerned authority."
        )
    ), 200


# ---------------------------------------------------------------------------
# 10. Email
# ---------------------------------------------------------------------------

def _prepare_email_image(image_path, max_dimension=1600, quality=75):
    """
    Prepare a compact JPEG copy of an image for email.

    The original files on disk are never changed.
    This prevents large MIME/base64 messages from causing Gmail
    to disconnect while receiving the DATA payload.
    """

    import cv2

    image = cv2.imread(image_path)

    if image is None:
        raise RuntimeError(
            f"Could not read image for email: {image_path}"
        )

    height, width = image.shape[:2]

    longest_side = max(height, width)

    if longest_side > max_dimension:
        scale = max_dimension / float(longest_side)

        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))

        image = cv2.resize(
            image,
            (new_width, new_height),
            interpolation=cv2.INTER_AREA
        )

    success, encoded = cv2.imencode(
        ".jpg",
        image,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            quality
        ]
    )

    if not success:
        raise RuntimeError(
            f"Could not compress image for email: {image_path}"
        )

    return encoded.tobytes()


def send_report_email(
    original_image_path,
    annotated_image_path,
    detections,
    ai_description,
    latitude,
    longitude,
    maps_link,
    date_str,
    time_str
):
    """
    Sends the CleanSpot report through Gmail SMTP.

    The original files are kept unchanged on disk, but compact JPEG
    copies are attached to the email so the SMTP message remains small.

    Email contains:
        - Formal greeting
        - AI-generated description
        - Google Maps live location link
        - Date and time
        - Request for action

    Latitude/longitude and YOLO confidence values are NOT displayed.

    Attachments:
        1. Original image
        2. AI annotated image
    """

    if (
        not SMTP_EMAIL
        or not SMTP_PASSWORD
        or not AUTHORITY_EMAIL
    ):
        raise RuntimeError(
            "Email is not configured. "
            "Please check SMTP_EMAIL, SMTP_PASSWORD, "
            "and AUTHORITY_EMAIL in your .env file."
        )

    subject = "CleanSpot – Garbage Report"

    body = f"""Respected Sir/Madam,

I would like to bring to your attention a garbage and cleanliness issue reported through the CleanSpot platform.

{ai_description}

Live Location:
{maps_link}

Date: {date_str}
Time: {time_str}

Kindly look into this matter and take the necessary action at the earliest.

Thank you for your attention and support.

Regards,
CleanSpot
Garbage Reporting System
"""

    msg = MIMEMultipart()

    msg["From"] = SMTP_EMAIL
    msg["To"] = AUTHORITY_EMAIL
    msg["Subject"] = subject

    msg.attach(
        MIMEText(
            body,
            "plain"
        )
    )

    # ---------------------------------------------------------
    # COMPRESS BOTH ATTACHMENTS FOR EMAIL
    # ---------------------------------------------------------
    #
    # This does NOT modify the images shown in the CleanSpot UI.
    # It only creates smaller in-memory JPEG versions for SMTP.
    #

    print("[EMAIL] Preparing original image attachment...")

    original_email_data = _prepare_email_image(
        original_image_path,
        max_dimension=1600,
        quality=75
    )

    msg.attach(
        MIMEImage(
            original_email_data,
            _subtype="jpeg",
            name=(
                "original_"
                + os.path.splitext(
                    os.path.basename(original_image_path)
                )[0]
                + ".jpg"
            )
        )
    )

    print(
        f"[EMAIL] Original attachment size: "
        f"{len(original_email_data) / 1024 / 1024:.2f} MB"
    )

    # ---------------------------------------------------------
    # AI ANNOTATED IMAGE
    # ---------------------------------------------------------

    if (
        annotated_image_path
        and os.path.exists(annotated_image_path)
    ):

        print("[EMAIL] Preparing annotated image attachment...")

        annotated_email_data = _prepare_email_image(
            annotated_image_path,
            max_dimension=1600,
            quality=75
        )

        msg.attach(
            MIMEImage(
                annotated_email_data,
                _subtype="jpeg",
                name=(
                    "annotated_"
                    + os.path.splitext(
                        os.path.basename(original_image_path)
                    )[0]
                    + ".jpg"
                )
            )
        )

        print(
            f"[EMAIL] Annotated attachment size: "
            f"{len(annotated_email_data) / 1024 / 1024:.2f} MB"
        )

    # ---------------------------------------------------------
    # SERIALIZE MESSAGE ONCE
    # ---------------------------------------------------------

    message_bytes = msg.as_bytes()

    message_size_mb = len(message_bytes) / 1024 / 1024

    print(
        f"[EMAIL] Total email size: "
        f"{message_size_mb:.2f} MB"
    )

    # Gmail's normal attachment/message limit is around 25 MB.
    # Stay comfortably below it because MIME/base64 encoding adds overhead.
    if message_size_mb > 20:
        raise RuntimeError(
            f"Email is still too large ({message_size_mb:.2f} MB). "
            f"Please use a smaller image."
        )

    # ---------------------------------------------------------
    # GMAIL SMTP WITH RETRY
    # ---------------------------------------------------------

    smtp_start = time.perf_counter()

    last_error = None

    for attempt in range(1, 3):

        server = None

        try:

            print(
                f"[EMAIL] SMTP attempt {attempt}/2..."
            )

            if SMTP_PORT == 465:

                print(
                    "[EMAIL] Using Gmail SMTP SSL on port 465..."
                )

                server = smtplib.SMTP_SSL(
                    SMTP_SERVER,
                    SMTP_PORT,
                    timeout=60
                )

            else:

                print(
                    "[EMAIL] Using Gmail SMTP STARTTLS "
                    f"on port {SMTP_PORT}..."
                )

                server = smtplib.SMTP(
                    SMTP_SERVER,
                    SMTP_PORT,
                    timeout=60
                )

                server.ehlo()

                print("[EMAIL] Starting TLS...")

                server.starttls()

                server.ehlo()

                print("[EMAIL] TLS connection established.")

            print("[EMAIL] SMTP connection established.")

            print("[EMAIL] Logging in...")

            server.login(
                SMTP_EMAIL,
                SMTP_PASSWORD
            )

            print("[EMAIL] Login successful.")

            print("[EMAIL] Sending email...")

            server.sendmail(
                SMTP_EMAIL,
                [AUTHORITY_EMAIL],
                message_bytes
            )

            email_elapsed = time.perf_counter() - smtp_start

            print(
                f"[TIMING] Email sending: "
                f"{email_elapsed:.2f} seconds"
            )

            print("[EMAIL] Email sent successfully.")

            return

        except smtplib.SMTPServerDisconnected as exc:

            last_error = exc

            print(
                f"[WARN] Gmail disconnected during "
                f"attempt {attempt}/2: {exc}"
            )

            if attempt < 2:
                print(
                    "[EMAIL] Reconnecting and retrying..."
                )
                time.sleep(2)

        except Exception as exc:

            last_error = exc

            print(
                f"[ERROR] SMTP error type: "
                f"{type(exc).__name__}"
            )

            print(
                f"[ERROR] SMTP error details: "
                f"{exc}"
            )

            break

        finally:

            if server is not None:

                try:
                    server.quit()
                except Exception:
                    pass

    email_elapsed = time.perf_counter() - smtp_start

    print(
        f"[TIMING] Email failed after "
        f"{email_elapsed:.2f} seconds"
    )

    raise last_error if last_error else RuntimeError(
        "Email could not be sent."
    )


# ---------------------------------------------------------------------------
# 11. Run the app
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )