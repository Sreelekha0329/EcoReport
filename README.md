# CleanSpot – AI-Powered Garbage Reporting Platform (v2)

This upgrades the original working prototype with **real AI**, while keeping
everything that already worked intact: photo capture, GPS location, the
Google Maps link, and Gmail SMTP email with an attached image.

## What's new in v2

- **YOLO garbage detection** (Ultralytics) — loaded once at startup, runs on
  the uploaded photo, returns detected waste categories + confidence scores
  + an annotated (bounding-box) image. Class names are read dynamically from
  whatever model file you place in `model/` — nothing is hard-coded.
- **Gemini (Google AI Studio)** — writes a short, professional 2-line
  description of the report from the YOLO detections, for the authority
  email. If Gemini is unavailable, a safe fallback message is used instead —
  the report always still gets sent.
- **Upgraded email** — now includes an "AI ANALYSIS" section, the Gemini
  description, and **both** the original photo and the AI-annotated photo
  as attachments.
- **Two-step report flow** — the photo is analyzed first (`/analyze-image`)
  so the user can review the AI's confidence bars and the annotated image
  *before* committing to send the report (`/submit-report`).
- **Redesigned UI** — eco-tech palette (deep forest green, dark green, fresh
  green, lime accent, off-white), a new hero section on the home page, and
  an AI results panel (confidence bars, spinner, annotated image) on the
  report page.

## What's intentionally NOT in this build yet

The original request describes a much larger citizen app: a live map, a
bottom nav, My Reports / Impact / Profile / Notifications pages, report
status tracking, achievements, and heavier scroll animations. Building all
of that in one pass — on top of AI integration that needed real testing —
would have meant a lot of screens that were never actually run end-to-end.
Per your own phased plan, this delivery covers **Phases 1–4** (YOLO →
Gemini → email upgrade → UI redesign of the existing two pages) and keeps
everything working and tested. **Phases 5–8** (map, My Reports, Impact /
Profile / Notifications, full responsive/animation polish) are a natural
next step — happy to build those next, the same way: one phase at a time,
verified against what already works.

## Folder Structure

```
garbage-reporting-system/
│
├── app.py                    # Flask backend: routes, YOLO, Gemini, email
├── requirements.txt
├── .env.example               # Copy to .env and fill in your values
├── .gitignore
│
├── model/
│   ├── garbage_model.pt       # ← you place your YOLO weights here
│   └── README.md              # explains where to get a model
│
├── templates/
│   ├── index.html             # Home page (hero)
│   └── report.html            # Report page (photo + GPS + AI + submit)
│
├── static/
│   ├── css/style.css
│   └── js/script.js
│
└── uploads/                   # Saved originals + annotated images
```

## 1. Installation From Scratch

```bash
cd garbage-reporting-system
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

`ultralytics` will also pull in PyTorch and OpenCV — this install can take a
few minutes and a few GB of disk on first run.

## 2. Configure `.env`

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux
```

Fill in:

```
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password
AUTHORITY_EMAIL=authority@example.com

YOLO_MODEL_PATH=model/garbage_model.pt
YOLO_CONFIDENCE_THRESHOLD=0.45

GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-2.5-flash
```

### Gmail App Password (unchanged from v1)

1. Turn on **2-Step Verification** on your Google account.
2. Go to https://myaccount.google.com/apppasswords and create an app
   password for "Mail".
3. Put the 16-character password in `SMTP_PASSWORD` — not your real Gmail
   password.

### Gemini API key

1. Go to https://aistudio.google.com/app/apikey and create a key.
2. Put it in `GEMINI_API_KEY`.
3. If this is missing, empty, or the API call fails for any reason, the app
   uses a safe fallback description automatically — reports still send.

### YOLO model

See `model/README.md`. In short: put your trained/pretrained garbage
detection weights at `model/garbage_model.pt` (or point `YOLO_MODEL_PATH`
elsewhere). If the file isn't there, the server logs a clear setup message
at startup, keeps running, and reports can still be submitted without AI
detections.

## 3. Run the App

```bash
python app.py
```

Watch the startup log — it will tell you clearly whether the YOLO model
loaded (and what classes it found) or whether it's missing, and whether the
Gemini client initialized.

## 4. Test on Desktop

1. Open `http://127.0.0.1:5000`, click **Report an Issue**.
2. Allow location permission.
3. Choose/upload a photo — analysis kicks off automatically:
   *"Analyzing image… Detecting waste… Identifying waste type… Preparing
   report…"* then confidence bars + (if detections exist) the annotated
   image appear.
4. Click **Send Report**. Check the authority inbox: subject *"CleanSpot
   Garbage Report – New Issue Detected"*, AI analysis section, Gemini's
   2-line description, location, map link, date/time, status, and **two**
   image attachments (original + annotated).

## 5. Test on Mobile (ngrok, unchanged from v1)

```bash
ngrok http 5000
```

Open the `https://...ngrok-free.app` URL on your phone — camera and GPS
only work over HTTPS or `localhost`, so a plain LAN IP (`http://192.168.x.x`)
won't work for those APIs on most mobile browsers.

* **Open Camera** hints the browser to launch the rear camera directly.
* **Upload Photo** opens the gallery/file picker instead.

## 6. Full Request Flow

```
Frontend (report.html)
   ↓ user picks/captures a photo
JavaScript → POST /analyze-image
   ↓
Flask: saves photo → runs YOLO (if available) → builds annotated image
   ↓
Response: detections + confidence + annotated image + report_token
   ↓
Frontend shows confidence bars + annotated image; user reviews
   ↓ user taps "Send Report"
JavaScript → POST /submit-report (report_token + GPS coords)
   ↓
Flask: looks up the pending report → asks Gemini for a 2-line description
        (falls back safely if Gemini fails) → builds the email → sends via
        smtplib (original + annotated images attached)
   ↓
Authority Email received
   ↓
Frontend shows the success message
```

## 7. Key Functions, Briefly

* **`app.py` → `load_yolo_model()`** — loads the `.pt` file once at Flask
  startup; reads `model.names` directly rather than assuming class names.
* **`app.py` → `run_yolo_detection()`** — runs inference, builds the
  `{label, confidence}` list, and saves an annotated image via
  `result.plot()` + OpenCV. Never raises — failures become "no detections".
* **`app.py` → `generate_ai_description()`** — calls Gemini with the
  detections, asks for exactly two plain sentences, and falls back to a
  safe generic message on any failure.
* **`app.py` → `/analyze-image`** — step 1: saves the photo, runs YOLO,
  stores the result in an in-memory `PENDING_REPORTS` dict keyed by a
  random token, and returns that token + the AI results to the frontend.
* **`app.py` → `/submit-report`** — step 2: validates GPS, looks up the
  pending report by token, generates the Gemini description, sends the
  email with both images attached.
* **`static/js/script.js` → `analyzeImage()`** — uploads the photo to
  `/analyze-image`, shows the rotating "Analyzing…" messages, then renders
  the confidence bars via `renderAiResults()`.

## 8. Error Handling Reference

| Situation | Behavior |
|---|---|
| No image selected | "⚠️ Please capture or select a garbage image." |
| Location denied | "⚠️ Location permission is required to submit a report." |
| YOLO model file missing | Logged clearly at startup; `/analyze-image` returns `ai_available: false` with a friendly note; report can still be sent |
| YOLO detects nothing | "No waste was confidently detected in this image…"; report can still be sent |
| Gemini call fails | Falls back to a safe generic description; email still sends |
| SMTP fails | "⚠️ Your report could not be sent. Please try again." |

## 9. Common Errors & Fixes

| Problem | Likely Cause | Fix |
|---|---|---|
| `ultralytics` install is slow / huge | It pulls in PyTorch + OpenCV | Expected — first install only, be patient |
| "YOLO model file not found" at startup | No weights placed yet | Add `model/garbage_model.pt` (see `model/README.md`) |
| Gemini description always looks generic | `GEMINI_API_KEY` missing/invalid, or network blocked | Check the key at aistudio.google.com; check server logs for the exact error |
| "⚠️ The report could not be emailed" | Wrong `SMTP_PASSWORD`, not using an App Password | Regenerate the Gmail App Password |
| Camera doesn't open on phone | Testing over plain `http://` | Use ngrok (HTTPS) — see section 5 |
| "Address already in use" | Port 5000 already used | Stop the other process, or `app.run(port=5001)` |

## 10. Security Notes

* API keys and SMTP credentials live only in `.env`, never in code or the
  frontend; `.env` and `model/*.pt` are both git-ignored.
* Uploaded filenames are sanitized (`secure_filename`) before saving.
* Only `.png/.jpg/.jpeg/.gif/.webp` extensions are accepted.
* Uploads are capped at 10 MB.
* `PENDING_REPORTS` is in-memory only (no database yet, matching the
  original prototype's scope) — fine for a single-process prototype, but a
  real deployment should add expiry/cleanup for old, unsubmitted analyses.
