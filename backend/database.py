import os
import certifi
import uuid
from datetime import datetime
import threading
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId

from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# ===========================================================================
# Database Configuration
# ===========================================================================
MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DATABASE_NAME", "EchoBoardDB")

_client = None
_id_lock = threading.Lock()

def _create_mongo_client(timeout_ms=10000):
    try:
        client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=30000,
        )
        client.admin.command('ping')
        return client
    except Exception:
        pass
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=True,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=30000,
    )
    client.admin.command('ping')
    return client

def get_db():
    global _client
    if _client is None:
        if not MONGO_URI:
            raise Exception("MONGODB_URI is not set in environment variables.")
        _client = _create_mongo_client()
    return _client[DB_NAME]

def init_db():
    if not MONGO_URI:
        raise Exception("MONGODB_URI is not set.")
    db = get_db()
    db.dataset_images.create_index([("image_id", ASCENDING)], unique=True)
    db.dataset_images.create_index([("sequence_id", ASCENDING)])
    db.dataset_images.create_index([("subject", ASCENDING)])
    db.dataset_images.create_index([("annotation_status", ASCENDING)])
    db.dataset_images.create_index([("dataset_version", ASCENDING)])
    db.dataset_images.create_index([("writer_id", ASCENDING)])
    db.videos.create_index([("uploaded_at", DESCENDING)])
    if db.counters.find_one({"_id": "echd_image_id"}) is None:
        db.counters.insert_one({"_id": "echd_image_id", "seq": 0})
    print(f"  Database: MongoDB Atlas — '{DB_NAME}'")

def _next_echd_id():
    with _id_lock:
        db = get_db()
        result = db.counters.find_one_and_update(
            {"_id": "echd_image_id"},
            {"$inc": {"seq": 1}},
            return_document=True,
        )
        return f"ECHD{result['seq']:06d}"

def insert_video(filename, duration_sec, total_frames, fps, processing=False):
    db = get_db()
    result = db.videos.insert_one({
        "filename": filename,
        "uploaded_at": datetime.utcnow().isoformat(),
        "duration_sec": duration_sec,
        "total_frames": total_frames,
        "fps": fps,
        "processing": processing,
    })
    return str(result.inserted_id)

def update_video(video_id, duration_sec, total_frames, fps, processing=False):
    db = get_db()
    db.videos.update_one(
        {"_id": ObjectId(video_id)},
        {"$set": {
            "duration_sec": duration_sec,
            "total_frames": total_frames,
            "fps": fps,
            "processing": processing
        }}
    )

def get_video(video_id):
    db = get_db()
    v = db.videos.find_one({"_id": ObjectId(video_id)})
    if not v:
        return None
    return {
        "id": str(v["_id"]),
        "filename": v["filename"],
        "uploaded_at": v["uploaded_at"],
        "duration_sec": v["duration_sec"],
        "total_frames": v["total_frames"],
        "fps": v["fps"],
        "processing": v.get("processing", False),
    }

def get_videos(limit=50):
    db = get_db()
    rows = db.videos.find().sort("uploaded_at", DESCENDING).limit(limit)
    res = []
    for v in rows:
        res.append({
            "id": str(v["_id"]),
            "filename": v["filename"],
            "uploaded_at": v["uploaded_at"],
            "duration_sec": v["duration_sec"],
            "total_frames": v["total_frames"],
            "fps": v["fps"],
            "processing": v.get("processing", False),
        })
    return res

# Alias for backward compatibility with api.py
get_video_by_id = get_video

def delete_video(video_id):
    """Delete a video and all its associated dataset images."""
    db = get_db()
    db.dataset_images.delete_many({"video_id": video_id})
    db.videos.delete_one({"_id": ObjectId(video_id)})

# Alias
delete_video_cascading = delete_video

def insert_dataset_image(
    sequence_id: str,
    subject: str,
    board_type: str,
    writer_id: str,
    frame_index: int,
    timestamp_ms: int,
    image_path: str,
    dataset_version: str = "ECHD_v1",
    uploaded_by: str = "system",
    video_id: str = None,
    change_score: float = 0.0,
):
    image_id = _next_echd_id()
    now = datetime.utcnow().isoformat()
    doc = {
        "image_id": image_id,
        "sequence_id": sequence_id,
        "subject": subject,
        "board_type": board_type,
        "writer_id": writer_id,
        "frame_index": frame_index,
        "timestamp_ms": timestamp_ms,
        "image_path": image_path,
        "annotation_status": "Pending",
        "dataset_version": dataset_version,
        "created_at": now,
        "uploaded_by": uploaded_by,
        "upload_time": now,
        "video_id": video_id or "",
        "change_score": change_score,
    }
    db = get_db()
    result = db.dataset_images.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return doc

def get_dataset_images(
    subject=None,
    sequence_id=None,
    writer_id=None,
    annotation_status=None,
    dataset_version=None,
    video_id=None,
    limit=200,
):
    db = get_db()
    query = {}
    if subject: query["subject"] = subject
    if sequence_id: query["sequence_id"] = sequence_id
    if writer_id: query["writer_id"] = writer_id
    if annotation_status: query["annotation_status"] = annotation_status
    if dataset_version: query["dataset_version"] = dataset_version
    if video_id: query["video_id"] = video_id

    rows = db.dataset_images.find(query).sort("created_at", ASCENDING).limit(limit)
    results = []
    for r in rows:
        results.append({
            "id": str(r["_id"]),
            "image_id": r["image_id"],
            "sequence_id": r["sequence_id"],
            "subject": r["subject"],
            "board_type": r["board_type"],
            "writer_id": r["writer_id"],
            "frame_index": r["frame_index"],
            "timestamp_ms": r["timestamp_ms"],
            "image_path": r["image_path"],
            "annotation_status": r["annotation_status"],
            "dataset_version": r["dataset_version"],
            "created_at": r["created_at"],
            "uploaded_by": r["uploaded_by"],
            "upload_time": r["upload_time"],
            "video_id": r["video_id"],
            "change_score": r.get("change_score", 0.0),
        })
    return results

def _format_dataset_image(r):
    """Helper to convert a MongoDB document to a dict."""
    if not r:
        return None
    return {
        "id": str(r["_id"]),
        "image_id": r["image_id"],
        "sequence_id": r["sequence_id"],
        "subject": r["subject"],
        "board_type": r["board_type"],
        "writer_id": r["writer_id"],
        "frame_index": r["frame_index"],
        "timestamp_ms": r["timestamp_ms"],
        "image_path": r["image_path"],
        "annotation_status": r["annotation_status"],
        "dataset_version": r["dataset_version"],
        "created_at": r["created_at"],
        "uploaded_by": r["uploaded_by"],
        "upload_time": r["upload_time"],
        "video_id": r["video_id"],
        "change_score": r.get("change_score", 0.0),
    }

def get_dataset_image_by_id(image_id):
    """Find a dataset image by its ECHD image_id (e.g. ECHD000001)."""
    db = get_db()
    r = db.dataset_images.find_one({"image_id": image_id})
    return _format_dataset_image(r)

def get_dataset_image_by_internal_id(internal_id):
    """Find a dataset image by its MongoDB _id (used for image serving)."""
    db = get_db()
    try:
        r = db.dataset_images.find_one({"_id": ObjectId(internal_id)})
    except Exception:
        return None
    return _format_dataset_image(r)

def update_annotation_status(image_id, status):
    db = get_db()
    db.dataset_images.update_one(
        {"image_id": image_id},
        {"$set": {"annotation_status": status}}
    )

def delete_dataset_image(image_id):
    db = get_db()
    db.dataset_images.delete_one({"image_id": image_id})

def get_images_for_video(video_id):
    return get_dataset_images(video_id=video_id, limit=10000)

def get_current_version():
    return "ECHD_v1"

def get_all_versions():
    # Placeholder for versions in MongoDB
    return [{"version_id": "ECHD_v1", "description": "Initial Database Version"}]

def create_new_version(description=""):
    # Return a dummy string for now
    return "ECHD_v2"

def upgrade_dataset_version(old_version, new_version):
    db = get_db()
    db.dataset_images.update_many(
        {"dataset_version": old_version},
        {"$set": {"dataset_version": new_version}}
    )

def get_stats():
    db = get_db()
    total_videos = db.videos.count_documents({})
    total_images = db.dataset_images.count_documents({})
    pending = db.dataset_images.count_documents({"annotation_status": "Pending"})
    annotated = db.dataset_images.count_documents({"annotation_status": "Completed"})
    subjects = db.dataset_images.distinct("subject")
    writers = db.dataset_images.distinct("writer_id")
    
    return {
        "total_videos": total_videos,
        "total_images": total_images,
        "pending_annotations": pending,
        "completed_annotations": annotated,
        "subjects": subjects,
        "writers": writers,
        "current_version": get_current_version(),
    }
