"""
database.py
EchoBoard Dataset — MongoDB Atlas Database Layer

Stores image metadata in MongoDB Atlas using the ECHD schema.
No SQLite fallback. If MongoDB is unreachable, the app will raise an error.
"""

import os
import certifi
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


def _create_mongo_client(timeout_ms=15000):
    """Try multiple TLS configurations to connect to MongoDB Atlas."""
    # Attempt 1: Standard TLS with system CA bundle
    try:
        client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=30000,
        )
        client.admin.command("ping")
        return client
    except Exception:
        pass

    # Attempt 2: TLS with relaxed certificate validation (for restrictive networks)
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=True,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=30000,
    )
    client.admin.command("ping")
    return client


def get_db():
    global _client
    if _client is None:
        if not MONGO_URI:
            raise Exception("MONGODB_URI is not set in environment variables.")
        _client = _create_mongo_client()
    return _client[DB_NAME]


def init_db():
    """Initialize MongoDB collections and indexes.
    If MongoDB is unreachable at startup, print a warning but don't crash.
    The connection will be retried when get_db() is called during upload.
    """
    if not MONGO_URI:
        raise Exception("MONGODB_URI is not set.")
    try:
        db = get_db()
        db.dataset_images.create_index([("image_id", ASCENDING)], unique=True)
        db.dataset_images.create_index([("created_at", DESCENDING)])
        if db.counters.find_one({"_id": "image_counter"}) is None:
            db.counters.insert_one({"_id": "image_counter", "seq": 0})
        if db.counters.find_one({"_id": "annotation_counter"}) is None:
            db.counters.insert_one({"_id": "annotation_counter", "seq": 0})
        print(f"  Database: MongoDB Atlas — '{DB_NAME}' ✓ Connected")
    except Exception as e:
        # Reset client so get_db() will retry on next call
        global _client
        _client = None
        print(f"  Database: MongoDB Atlas — DEFERRED (will retry on upload)")
        print(f"  Reason: {str(e)[:100]}")
        print(f"  Tip: Switch to mobile hotspot if on a restrictive network.")



# ---------------------------------------------------------------------------
# Sequential ID Generators
# ---------------------------------------------------------------------------
def _next_image_id():
    with _id_lock:
        db = get_db()
        result = db.counters.find_one_and_update(
            {"_id": "image_counter"},
            {"$inc": {"seq": 1}},
            return_document=True,
        )
        return f"IMG{result['seq']:04d}"


def _next_annotation_id():
    with _id_lock:
        db = get_db()
        result = db.counters.find_one_and_update(
            {"_id": "annotation_counter"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        return f"ANN{result['seq']:04d}"


# ---------------------------------------------------------------------------
# Core CRUD — Dataset Images (new ECHD schema)
# ---------------------------------------------------------------------------
def insert_dataset_image(
    image_name: str,
    image_path: str,
    width: int,
    height: int,
    format_type: str,
    size_kb: int,
    annotation_text: str = "",
    annotation_class: str = "Text",
):
    """Insert one image record using the ECHD schema."""
    image_id = _next_image_id()
    now = datetime.utcnow().isoformat() + "Z"

    # Build annotations array
    annotations = []
    if annotation_text.strip():
        ann_id = _next_annotation_id()
        annotations.append({
            "annotation_id": ann_id,
            "class": annotation_class,
            "bbox": [],
            "text": annotation_text,
            "latex": "",
            "confidence": 0.0,
        })

    doc = {
        "image_id": image_id,
        "image_name": image_name,
        "image_path": image_path,
        "image_metadata": {
            "width": width,
            "height": height,
            "format": format_type,
            "size_kb": size_kb,
        },
        "annotations": annotations,
        "quality_metadata": {
            "blur_score": 0.0,
            "lighting_score": 0,
            "duplicate": False,
            "occluded": False,
            "selected": True,
        },
        "processing_status": {
            "ocr_completed": False,
            "annotation_completed": bool(annotation_text.strip()),
            "reviewed": False,
        },
        "created_at": now,
        "updated_at": now,
    }
    db = get_db()
    result = db.dataset_images.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


def get_dataset_images(limit=500, **kwargs):
    """Return all dataset images, newest first."""
    db = get_db()
    query = {}
    rows = db.dataset_images.find(query).sort("created_at", DESCENDING).limit(limit)
    results = []
    for r in rows:
        r["_id"] = str(r["_id"])
        results.append(r)
    return results


def get_dataset_image_by_id(image_id):
    """Look up by ECHD image_id (e.g. IMG0001)."""
    db = get_db()
    r = db.dataset_images.find_one({"image_id": image_id})
    if r:
        r["_id"] = str(r["_id"])
    return r


def get_dataset_image_by_internal_id(internal_id):
    """Look up by MongoDB ObjectId string."""
    try:
        db = get_db()
        r = db.dataset_images.find_one({"_id": ObjectId(internal_id)})
        if r:
            r["_id"] = str(r["_id"])
        return r
    except Exception:
        return None


def delete_dataset_image(image_id):
    db = get_db()
    db.dataset_images.delete_one({"image_id": image_id})


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def get_stats():
    db = get_db()
    total = db.dataset_images.count_documents({})
    annotated = db.dataset_images.count_documents({"processing_status.annotation_completed": True})
    return {
        "total_images": total,
        "annotated_images": annotated,
        "pending_images": total - annotated,
    }


# ---------------------------------------------------------------------------
# Stub functions for legacy API endpoints (keeps api.py from crashing)
# ---------------------------------------------------------------------------
def get_videos(limit=50):
    return []

def get_video(video_id):
    return None

def insert_video(filename="", duration_sec=0, total_frames=0, fps=0, processing=True):
    return "stub_video_id"

def update_video(video_id="", duration_sec=0, total_frames=0, fps=0, processing=False):
    pass

def get_images_for_video(video_id):
    return []

def delete_video(video_id):
    pass

def get_current_version():
    return "ECHD_v1"

def get_all_versions():
    return [{"version_id": "ECHD_v1", "description": "Initial version"}]

def create_new_version(description=""):
    return "ECHD_v2"


# ---------------------------------------------------------------------------
# Data Purge (admin utility)
# ---------------------------------------------------------------------------
def purge_all():
    """Delete ALL data from ALL collections. Use with extreme caution."""
    db = get_db()
    db.dataset_images.drop()
    db.counters.drop()
    print("  All MongoDB collections purged.")
