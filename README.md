# EchoBoard — MVP Implementation

*Every Lesson Preserved. Every Concept Searchable.*

This is a working starting point for the EchoBoard system described in your
report: it watches a classroom video, figures out when the board's writing
has "settled" (finished changing), saves that moment as a keyframe, and
stores it in a searchable database — instead of keeping the whole raw video.

## What's included

| File | Purpose |
|---|---|
| `video_processor.py` | Core engine. Reads a video, detects board keyframes using frame-difference motion detection, saves them as JPGs. |
| `database.py` | SQLite database layer. Stores videos + keyframes (path, timestamp, change score, OCR text placeholder). |
| `app.py` | Streamlit UI: upload a video, tune sensitivity, process it, browse/replay the timeline, search. |
| `requirements.txt` | Python dependencies. |

## 1. How the capture algorithm works (the "novelty" part)

Rather than saving every frame or one frame every N seconds, it tracks the
board's **state**:

1. Compare each sampled frame to the **previous** sampled frame → measures
   how much is currently changing (a hand writing, chalk moving, an eraser
   passing through).
2. While that change is above `motion_threshold`, the board is "dirty" —
   we do **not** save, since it's mid-write and would look blurry/incomplete.
3. Once several consecutive samples come back calm (`stable_frames_required`),
   the board has "settled."
4. Before saving, compare the settled frame to the **last saved keyframe**.
   If it's basically the same board, skip it (avoids duplicate saves of an
   unchanged board sitting in view).
5. Save the frame + metadata (timestamp, frame number, change score) to disk
   and the database.

This is pure OpenCV frame-differencing, so it runs on CPU with no GPU or
trained model required — a genuine MVP. Your report's stack
(YOLOv8-nano for active-region detection, TrOCR/handwriting recognition,
Potrace for vector outlines) plugs in as upgrades later without changing the
overall pipeline: they'd replace *how a frame is judged worth saving* and
*what happens to a saved frame*, not the surrounding architecture.

## 2. Setup

```bash
# 1. Create and activate a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize the database (creates echoboard.db)
python database.py
```

## 3. Run the app

```bash
streamlit run app.py
```

This opens a browser tab (usually `http://localhost:8501`) with three tabs:

- **Upload & Process** — upload a classroom video, tune sensitivity sliders,
  click "Process Video". Keyframes are extracted and saved automatically.
- **Lesson Library** — pick a processed video, scrub through a timeline
  slider to replay how the board evolved, or view all keyframes as a grid.
- **Search** — text search over keyframes' `ocr_text` field (empty until you
  plug in a handwriting/OCR model — see Step 5).

## 4. Testing without a real classroom video

You can generate a synthetic test video to confirm everything works before
using a real recording:

```python
import cv2, numpy as np

w, h, fps = 320, 240, 25
out = cv2.VideoWriter('test_board.mp4', cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

def frame(lines):
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    y = 40
    for line in lines:
        cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20,20,20), 2)
        y += 40
    return img

for _ in range(fps): out.write(frame([]))                       # blank
for _ in range(fps*2): out.write(frame(['E=mc^2']))              # write + hold
for _ in range(fps*2): out.write(frame(['E=mc^2', 'F=ma']))      # write + hold
out.release()
```

Then run `python video_processor.py test_board.mp4` directly, or upload it
through the Streamlit UI.

## 5. Suggested next implementation steps (matching your report's roadmap)

1. **Handwriting/formula recognition** — feed each saved keyframe image
   through a model (e.g. TrOCR, or a custom CRNN as implied by your
   PyTorch/Timm stack) and store the result in `keyframes.ocr_text` via
   `database.py`. This immediately powers the Search tab.
2. **Active-region detection (YOLOv8-nano)** — instead of diffing the whole
   frame, restrict the diff/crop to the detected board region, so a person
   walking in front of the camera doesn't get mistaken for "writing."
3. **Vector/diagram extraction (scikit-image + Potrace)** — for keyframes
   with diagrams, generate an SVG outline alongside the JPG and store its
   path in the database.
4. **Live camera input** — swap `cv2.VideoCapture(video_path)` for
   `cv2.VideoCapture(0)` (or an RTSP/IP camera URL) in `video_processor.py`
   to move from "process an uploaded video" to "watch the board live."
   You'd run the capture loop in a background thread/process and use
   WebSockets (as in your report) to push new keyframes to the Streamlit
   UI in real time.
5. **Swap SQLite → Postgres** once multiple classrooms/users need concurrent
   access — only `database.py` needs to change; `video_processor.py` and
   `app.py` are unaffected.

## 6. Tuning tips

- If too many keyframes are captured: raise `motion_threshold` and/or
  `new_content_threshold`.
- If keyframes are captured *too late* / miss content: lower
  `stable_frames_required`.
- If the video is high-resolution and processing is slow: increase
  `sample_every_n_frames`.

All of these are exposed as sliders in the Upload tab, so you can tune them
interactively per video before settling on defaults for your dataset.
