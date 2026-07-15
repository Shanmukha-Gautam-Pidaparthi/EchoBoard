"""
api.py
EchoBoard Dataset Creation Module — FastAPI REST API

Provides REST endpoints for the React dashboard to:
  - Upload videos and extract intelligent keyframes (Stages 1-3)
  - Upload individual board images directly (Stage 4)
  - Store original images in MinIO / local storage (Stage 5)
  - Register dataset metadata in MongoDB / SQLite (Stage 6)
  - Manage the annotation queue (Stage 7)
  - Export dataset versions (Stages 9-12)

Run with:
    uvicorn backend.api:app --reload --port 8000

IMPORTANT: This module does NOT perform OCR, handwriting recognition,
YOLO, MobileNet, or Bi-LSTM inference. Those belong to later phases.
"""

import io
import os
import sys
import shutil
import tempfile
import threading
import zipfile

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import Optional

# Add parent directory to path so we can import backend modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db
import storage
from video_processor import process_video

app = FastAPI(
    title="EchoBoard Dataset Creation API",
    description="REST API for the EchoBoard Classroom Handwriting Dataset (ECHD) creation module.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    print("\n=== EchoBoard Dataset Creation Module ===")
    print("  Initializing database...")
    db.init_db()
    print("  Initializing storage...")
    storage.init_storage()
    print("  Ready!\n")


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------
class UrlRequest(BaseModel):
    url: str
    subject: str = "General"
    board_type: str = "Blackboard"
    writer_id: str = "unknown"
    sample_every_n_frames: int = 3
    motion_threshold: float = 0.03
    stable_frames_required: int = 4
    new_content_threshold: float = 0.05


class DatasetUploadRequest(BaseModel):
    """POST /dataset/upload body for direct image upload metadata."""
    sequence_id: str
    subject: str
    board_type: str = "Blackboard"
    writer_id: str = "unknown"


class VersionRequest(BaseModel):
    description: str = ""


# ---------------------------------------------------------------------------
# Dashboard Stats
# ---------------------------------------------------------------------------
@app.get("/api/stats")
def get_stats():
    """Return dashboard statistics for the dataset."""
    return db.get_stats()


# ---------------------------------------------------------------------------
# Video Management (source videos for keyframe extraction)
# ---------------------------------------------------------------------------
@app.get("/api/videos")
def list_videos():
    """List all source videos."""
    return db.get_videos()


@app.get("/api/videos/{video_id}")
def get_video(video_id: str):
    v = db.get_video(video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


@app.delete("/api/videos/{video_id}")
def delete_video_endpoint(video_id: str):
    v = db.get_video(video_id)
    if not v:
        raise HTTPException(404, "Video not found")

    # Also delete associated images from storage
    images = db.get_images_for_video(video_id)
    for img in images:
        try:
            storage.delete_image(img["image_path"])
        except Exception:
            pass

    db.delete_video(video_id)
    return {"message": f"Deleted '{v['filename']}' and its dataset images"}


# ---------------------------------------------------------------------------
# Dataset Images (keyframes stored in the ECHD dataset)
# ---------------------------------------------------------------------------
@app.get("/api/videos/{video_id}/keyframes")
def get_keyframes(video_id: str):
    """Return all dataset images associated with a video."""
    return db.get_images_for_video(video_id)


@app.get("/api/dataset/images/{image_id}/raw")
def get_image_raw(image_id: str):
    """Serve the original raw image by its ECHD image_id."""
    record = db.get_dataset_image_by_id(image_id)
    if not record:
        raise HTTPException(404, "Image not found")
    data = storage.get_image(record["image_path"])
    if not data:
        raise HTTPException(404, "Image file not found in storage")
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/keyframes/{image_id}/image")
def get_keyframe_image(image_id: str):
    """
    Serve an image by its internal DB id or ECHD image_id.
    Uses efficient MongoDB _id lookup — no full table scan.
    """
    # Try by internal MongoDB _id first (this is what the frontend sends)
    record = db.get_dataset_image_by_internal_id(image_id)
    if record:
        data = storage.get_image(record["image_path"])
        if data:
            return Response(content=data, media_type="image/jpeg")

    # Try by ECHD image_id (e.g. ECHD000001)
    record = db.get_dataset_image_by_id(image_id)
    if record:
        data = storage.get_image(record["image_path"])
        if data:
            return Response(content=data, media_type="image/jpeg")

    raise HTTPException(404, "Image not found")


# ---------------------------------------------------------------------------
# Dataset Upload: Direct Image (Stage 4)
# ---------------------------------------------------------------------------
@app.post("/dataset/upload")
async def dataset_upload(
    image: UploadFile = File(...),
    sequence_id: str = Form(...),
    subject: str = Form(...),
    board_type: str = Form("Blackboard"),
    writer_id: str = Form("unknown"),
):
    """
    Upload a single board image directly into the ECHD dataset.

    This is the Stage 4 endpoint. The image is stored unmodified in MinIO/local
    storage and metadata is registered in MongoDB/SQLite.
    """
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Empty image file")

    # Determine filename
    ext = os.path.splitext(image.filename or ".jpg")[1] or ".jpg"
    version = db.get_current_version()

    # Store original image in MinIO/local (Stage 5)
    # Path: echoboard-dataset/<subject>/<sequence_id>/<filename>
    safe_subject = "".join(c if c.isalnum() or c in " _-" else "_" for c in subject).strip().lower().replace(" ", "_")
    fname = f"frame_{len(db.get_dataset_images(sequence_id=sequence_id)) + 1:04d}{ext}"
    image_path = storage.store_image(image_bytes, safe_subject, sequence_id, fname)

    # Register in MongoDB/SQLite (Stage 6)
    record = db.insert_dataset_image(
        sequence_id=sequence_id,
        subject=subject,
        board_type=board_type,
        writer_id=writer_id,
        frame_index=0,
        timestamp_ms=0,
        image_path=image_path,
        dataset_version=version,
        uploaded_by=writer_id,
    )

    return {
        "image_id": record["image_id"],
        "image_path": image_path,
        "annotation_status": "Pending",
        "dataset_version": version,
    }


# ---------------------------------------------------------------------------
# Upload: Video File → Keyframe Extraction (Stages 1-3)
# ---------------------------------------------------------------------------
@app.post("/api/upload/video")
async def upload_video(
    file: UploadFile = File(...),
    subject: str = Form("General"),
    board_type: str = Form("Blackboard"),
    writer_id: str = Form("unknown"),
    sample_every_n_frames: int = Form(3),
    motion_threshold: float = Form(0.03),
    stable_frames_required: int = Form(4),
    new_content_threshold: float = Form(0.05),
):
    """Upload a video file, extract keyframes, store them in the dataset."""
    suffix = os.path.splitext(file.filename or ".mp4")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    video_id = db.insert_video(
        filename=file.filename or "Uploaded Video",
        duration_sec=0, total_frames=0, fps=0,
    )

    version = db.get_current_version()
    safe_subject = "".join(c if c.isalnum() or c in " _-" else "_" for c in subject).strip().lower().replace(" ", "_")
    sequence_id = f"{safe_subject}_{video_id[:8]}"
    kf_counter = [0]

    def on_keyframe(kf):
        kf_counter[0] += 1
        # Read the temporary image file
        with open(kf["image_path"], "rb") as f:
            image_bytes = f.read()

        # Store original image in MinIO/local (Stage 5)
        fname = f"frame{kf_counter[0]:04d}.jpg"
        stored_path = storage.store_image(image_bytes, safe_subject, sequence_id, fname)

        # Register in MongoDB/SQLite (Stage 6) — annotation_status = "Pending" (Stage 7)
        db.insert_dataset_image(
            sequence_id=sequence_id,
            subject=subject,
            board_type=board_type,
            writer_id=writer_id,
            frame_index=kf["frame_number"],
            timestamp_ms=kf.get("timestamp_ms", int(kf["timestamp_sec"] * 1000)),
            image_path=stored_path,
            dataset_version=version,
            uploaded_by=writer_id,
            video_id=video_id,
            change_score=kf["change_score"],
        )

        # Clean up temporary frame file
        if os.path.exists(kf["image_path"]):
            os.unlink(kf["image_path"])

    try:
        result = process_video(
            tmp_path, video_id=video_id,
            sample_every_n_frames=sample_every_n_frames,
            motion_threshold=motion_threshold,
            stable_frames_required=stable_frames_required,
            new_content_threshold=new_content_threshold,
            on_keyframe=on_keyframe,
        )
        db.update_video(
            video_id=video_id,
            duration_sec=result["duration_sec"],
            total_frames=result["total_frames"],
            fps=result["fps"],
        )
        return {
            "video_id": video_id,
            "filename": file.filename,
            "sequence_id": sequence_id,
            "duration_sec": result["duration_sec"],
            "keyframes_captured": len(result["keyframes"]),
        }
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Upload: Direct Images (batch board photos)
# ---------------------------------------------------------------------------
@app.post("/api/upload/images")
async def upload_images(
    files: list[UploadFile] = File(...),
    subject: str = Form("General"),
    board_type: str = Form("Blackboard"),
    writer_id: str = Form("unknown"),
    sequence_id: str = Form(""),
):
    """Upload multiple board images directly into the ECHD dataset."""
    if not files:
        raise HTTPException(400, "No files provided")

    video_id = db.insert_video(
        filename=f"Image Upload ({len(files)} images)",
        duration_sec=0, total_frames=len(files), fps=0,
        processing=False,
    )

    version = db.get_current_version()
    safe_subject = "".join(c if c.isalnum() or c in " _-" else "_" for c in subject).strip().lower().replace(" ", "_")
    if not sequence_id:
        sequence_id = f"{safe_subject}_{video_id[:8]}"

    for i, img in enumerate(files):
        image_bytes = await img.read()
        ext = os.path.splitext(img.filename or ".jpg")[1] or ".jpg"
        fname = f"frame{i + 1:04d}{ext}"
        stored_path = storage.store_image(image_bytes, safe_subject, sequence_id, fname)

        db.insert_dataset_image(
            sequence_id=sequence_id,
            subject=subject,
            board_type=board_type,
            writer_id=writer_id,
            frame_index=i + 1,
            timestamp_ms=0,
            image_path=stored_path,
            dataset_version=version,
            uploaded_by=writer_id,
            video_id=video_id,
        )

    return {
        "video_id": video_id,
        "sequence_id": sequence_id,
        "images_stored": len(files),
    }


# ---------------------------------------------------------------------------
# Upload: URL → Background Processing
# ---------------------------------------------------------------------------
running_tasks = {}  # video_id -> threading.Event


def background_process_url(
    video_id: str,
    url: str,
    subject: str,
    board_type: str,
    writer_id: str,
    sample_every_n_frames: int,
    motion_threshold: float,
    stable_frames_required: int,
    new_content_threshold: float,
):
    """Background task: download video from URL and extract keyframes."""
    stop_event = running_tasks.get(video_id)

    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "video.mkv")
    dl_thread = None

    version = db.get_current_version()
    safe_subject = "".join(c if c.isalnum() or c in " _-" else "_" for c in subject).strip().lower().replace(" ", "_")
    sequence_id = f"{safe_subject}_{video_id[:8]}"
    kf_counter = [0]

    try:
        import yt_dlp

        def on_keyframe(kf):
            kf_counter[0] += 1
            with open(kf["image_path"], "rb") as f:
                image_bytes = f.read()

            fname = f"frame{kf_counter[0]:04d}.jpg"
            stored_path = storage.store_image(image_bytes, safe_subject, sequence_id, fname)

            db.insert_dataset_image(
                sequence_id=sequence_id,
                subject=subject,
                board_type=board_type,
                writer_id=writer_id,
                frame_index=kf["frame_number"],
                timestamp_ms=kf.get("timestamp_ms", int(kf["timestamp_sec"] * 1000)),
                image_path=stored_path,
                dataset_version=version,
                uploaded_by=writer_id,
                video_id=video_id,
                change_score=kf["change_score"],
            )
            if os.path.exists(kf["image_path"]):
                os.unlink(kf["image_path"])

        def run_download():
            dl_opts = {
                "format": "bestvideo[height<=720]/best[height<=720]/best",
                "outtmpl": tmp_path,
                "merge_output_format": "mkv",
                "nopart": True,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                ydl.download([url])

        dl_thread = threading.Thread(target=run_download)
        dl_thread.start()

        result = process_video(
            tmp_path, video_id=video_id,
            sample_every_n_frames=sample_every_n_frames,
            motion_threshold=motion_threshold,
            stable_frames_required=stable_frames_required,
            new_content_threshold=new_content_threshold,
            on_keyframe=on_keyframe,
            download_thread=dl_thread,
            stop_event=stop_event,
        )

        db.update_video(
            video_id=video_id,
            duration_sec=result["duration_sec"],
            total_frames=result["total_frames"],
            fps=result["fps"],
            processing=False,
        )
    except Exception as e:
        print(f"Error in background_process_url: {e}", flush=True)
        db.update_video(video_id, 0, 0, 0, processing=False)
    finally:
        running_tasks.pop(video_id, None)
        if dl_thread and dl_thread.is_alive():
            dl_thread.join(timeout=5.0)
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.post("/api/upload/url")
def upload_url(req: UrlRequest, background_tasks: BackgroundTasks):
    """Download a video from URL and extract keyframes in the background."""
    try:
        import yt_dlp
    except ImportError:
        raise HTTPException(500, "yt-dlp not installed")

    try:
        ydl_opts = {
            "format": "bestvideo[height<=720]/best[height<=720]/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            title = info.get("title", "Downloaded Video")
            duration = info.get("duration", 0)
            fps = info.get("fps", 0)

        video_id = db.insert_video(
            filename=title,
            duration_sec=duration or 0,
            total_frames=0,
            fps=fps or 25.0,
            processing=True,
        )

        stop_event = threading.Event()
        running_tasks[video_id] = stop_event

        background_tasks.add_task(
            background_process_url,
            video_id, req.url,
            req.subject, req.board_type, req.writer_id,
            req.sample_every_n_frames, req.motion_threshold,
            req.stable_frames_required, req.new_content_threshold,
        )

        return {
            "video_id": video_id,
            "title": title,
            "status": "processing",
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/videos/{video_id}/stop")
def stop_video_processing(video_id: str):
    """Send a stop signal to a currently processing video."""
    if video_id in running_tasks:
        running_tasks[video_id].set()
        db.update_video(video_id, 0, 0, 0, processing=False)
        return {"message": "Stop signal sent successfully."}
    else:
        db.update_video(video_id, 0, 0, 0, processing=False)
        raise HTTPException(404, "Video is not currently processing.")


# ---------------------------------------------------------------------------
# Dataset Explorer & Export
# ---------------------------------------------------------------------------
@app.get("/api/dataset/images")
def list_dataset_images(
    subject: str = Query(None),
    sequence_id: str = Query(None),
    writer_id: str = Query(None),
    annotation_status: str = Query(None),
    dataset_version: str = Query(None),
    limit: int = Query(200),
):
    """List dataset images with optional filtering."""
    return db.get_dataset_images(
        subject=subject,
        sequence_id=sequence_id,
        writer_id=writer_id,
        annotation_status=annotation_status,
        dataset_version=dataset_version,
        limit=limit,
    )


@app.get("/api/dataset/images/{image_id}")
def get_dataset_image(image_id: str):
    """Get a single dataset image record by its ECHD image_id."""
    record = db.get_dataset_image_by_id(image_id)
    if not record:
        raise HTTPException(404, "Dataset image not found")
    return record


@app.delete("/api/dataset/images/{image_id}")
def delete_dataset_image(image_id: str):
    """Delete a single dataset image and its storage file."""
    record = db.get_dataset_image_by_id(image_id)
    if not record:
        raise HTTPException(404, "Dataset image not found")
    try:
        storage.delete_image(record["image_path"])
    except Exception:
        pass
    db.delete_dataset_image(image_id)
    return {"message": f"Deleted {image_id}"}


# ---------------------------------------------------------------------------
# Dataset Version Management
# ---------------------------------------------------------------------------
@app.get("/api/dataset/versions")
def list_versions():
    """List all dataset versions."""
    return db.get_all_versions()


@app.post("/api/dataset/versions")
def create_version(req: VersionRequest):
    """Create a new dataset version. Never overwrites previous versions."""
    new_version = db.create_new_version(description=req.description)
    return {"version": new_version, "message": f"Created {new_version}"}


# ---------------------------------------------------------------------------
# Dataset ZIP Download
# ---------------------------------------------------------------------------
@app.get("/api/videos/{video_id}/download")
def download_video_zip(video_id: str):
    """Download all keyframe images of a single video as a ZIP."""
    v = db.get_video(video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    images = db.get_images_for_video(video_id)
    if not images:
        raise HTTPException(404, "No images found")

    buf = io.BytesIO()
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in v["filename"])
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in images:
            data = storage.get_image(img["image_path"])
            if data:
                fname = f"{safe_name}/{img['image_id']}_f{img['frame_index']}.jpg"
                zf.writestr(fname, data)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )


@app.get("/api/download/dataset")
def download_full_dataset():
    """Download the entire ECHD dataset as a ZIP (Stage 12 output)."""
    images = db.get_dataset_images(limit=100000)
    if not images:
        raise HTTPException(404, "No images in dataset")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in images:
            data = storage.get_image(img["image_path"])
            if data:
                # Mirror MinIO bucket structure
                fname = img["image_path"]
                zf.writestr(fname, data)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="echoboard_dataset.zip"'},
    )
