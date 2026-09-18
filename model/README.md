# YOLO Model Folder

Place your trained/pretrained garbage-detection weights here as:

```
model/garbage_model.pt
```

The path is configurable via `YOLO_MODEL_PATH` in `.env` if you want to name
it differently or point elsewhere.

## Where to get a model

You have two options:

1. **A garbage/waste-specific YOLO model you already trained or downloaded**
   (e.g. from Roboflow Universe, Kaggle, or your own training run). Export or
   copy the `.pt` weights file into this folder.
2. **A general-purpose Ultralytics YOLO model** (e.g. `yolov8n.pt`,
   `yolov8s.pt`) as a placeholder while you source a real garbage-specific
   model. General COCO-trained models don't have "plastic/paper/cardboard"
   classes — they detect generic objects (bottle, cup, etc.) — but they let
   you test the full pipeline (loading, inference, bounding boxes, email)
   before swapping in a purpose-built model.

## Important: classes are NOT hard-coded

`app.py` reads `model.names` directly from whatever `.pt` file you place
here at startup, and uses those names as-is everywhere (in the API
response, the UI, and the email). It does **not** assume specific class
names like "Plastic" or "Paper" — if your model's classes are different,
the app will still work and will just show whatever labels the model
actually reports.

## If this file is missing

The Flask app checks for `garbage_model.pt` (or your configured path) at
startup. If it's not found:

- The server **does not crash**.
- `/analyze-image` will respond with `ai_available: false` and a message
  explaining the model is not configured.
- Users can still submit reports — the report is simply sent without AI
  detections and with a fallback description in the email.
