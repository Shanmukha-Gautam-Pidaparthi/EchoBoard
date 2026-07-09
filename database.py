"""
database.py
EchoBoard - MongoDB Atlas & Local SQLite Fallback Database Layer

Stores captured "board keyframes" and metadata.
If MongoDB Atlas is unreachable (e.g. due to IP whitelisting issues),
it automatically and seamlessly falls back to a local SQLite database (echoboard_local.db).
"""

import os
import base64
import certifi
import sqlite3
import uuid
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
import pymongo.errors as mongo_errors
from bson import ObjectId
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# CONNECTION CONFIG — Loaded from .env file
# ---------------------------------------------------------------------------
MONGO_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("DATABASE_NAME", "EchoBoardDB")

if not MONGO_URI:
    raise RuntimeError(
        "MONGODB_URI not set! Create a .env file with your MongoDB Atlas connection string."
    )

# Global flag and local SQLite config
USE_SQLITE = False
DB_FILE = os.path.join(os.path.dirname(__file__), "echoboard_local.db")

_client = None

def get_db():
    """Return the MongoDB database handle, creating the client on first call."""
    global _client
    if _client is None:
        _client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,   # Fail fast instead of 30s default
            connectTimeoutMS=5000,
            socketTimeoutMS=20000,
        )
    return _client[DB_NAME]

def get_sqlite_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_sqlite_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create videos table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            filename TEXT,
            uploaded_at TEXT,
            duration_sec REAL,
            total_frames INTEGER,
            fps REAL,
            processing INTEGER
        )
    """)
    # Create keyframes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyframes (
            id TEXT PRIMARY KEY,
            video_id TEXT,
            frame_number INTEGER,
            timestamp_sec REAL,
            image_b64 TEXT,
            change_score REAL,
            ocr_text TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def init_db():
    """Create indexes for fast queries. Safe to call every run.
    
    If MongoDB Atlas is unreachable, falls back to SQLite.
    """
    global USE_SQLITE
    try:
        # Test connection by listing databases (forces a quick ping/handshake)
        test_client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        test_client.list_database_names()
        
        # If we got here, MongoDB Atlas is reachable!
        db = get_db()
        db.keyframes.create_index([("video_id", ASCENDING), ("timestamp_sec", ASCENDING)])
        db.keyframes.create_index([("ocr_text", ASCENDING)])
        db.videos.create_index([("uploaded_at", DESCENDING)])
        print(f"Connected to MongoDB Atlas - database: '{DB_NAME}'")
        USE_SQLITE = False
    except Exception as e:
        print(f"\nWARNING: Could not connect to MongoDB Atlas. Error: {e}")
        print(f"Falling back to local SQLite database: {DB_FILE}\n")
        USE_SQLITE = True
        init_sqlite_db()

# ---------------------------------------------------------------------------
# Video CRUD
# ---------------------------------------------------------------------------
def insert_video(filename, duration_sec, total_frames, fps, processing=False):
    """Insert a new video record and return its ID as a string."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
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
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB write failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    video_id = uuid.uuid4().hex[:24]
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO videos (id, filename, uploaded_at, duration_sec, total_frames, fps, processing) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (video_id, filename, datetime.utcnow().isoformat(), duration_sec, total_frames, fps, 1 if processing else 0)
    )
    conn.commit()
    conn.close()
    return video_id

def get_all_videos():
    """Return all videos as a list of dicts, newest first."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
            db = get_db()
            rows = db.videos.find().sort("uploaded_at", DESCENDING)
            videos = []
            for v in rows:
                videos.append({
                    "id": str(v["_id"]),
                    "filename": v["filename"],
                    "uploaded_at": v["uploaded_at"],
                    "duration_sec": v["duration_sec"],
                    "total_frames": v["total_frames"],
                    "fps": v["fps"],
                    "processing": v.get("processing", False),
                })
            return videos
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB query failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM videos ORDER BY uploaded_at DESC")
    rows = cursor.fetchall()
    videos = []
    for r in rows:
        videos.append({
            "id": r["id"],
            "filename": r["filename"],
            "uploaded_at": r["uploaded_at"],
            "duration_sec": r["duration_sec"],
            "total_frames": r["total_frames"],
            "fps": r["fps"],
            "processing": bool(r["processing"]),
        })
    conn.close()
    return videos

# ---------------------------------------------------------------------------
# Keyframe CRUD
# ---------------------------------------------------------------------------
def insert_keyframe(video_id, frame_number, timestamp_sec, image_path,
                    change_score, ocr_text=""):
    """
    Insert a keyframe document into the database.
    Reads the image file from disk and encodes it as base64.
    """
    global USE_SQLITE
    image_b64 = ""
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

    if not USE_SQLITE:
        try:
            db = get_db()
            result = db.keyframes.insert_one({
                "video_id": video_id,
                "frame_number": frame_number,
                "timestamp_sec": timestamp_sec,
                "image_b64": image_b64,
                "change_score": change_score,
                "ocr_text": ocr_text or "",
                "created_at": datetime.utcnow().isoformat(),
            })
            return str(result.inserted_id)
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB write failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    kf_id = uuid.uuid4().hex[:24]
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO keyframes (id, video_id, frame_number, timestamp_sec, image_b64, change_score, ocr_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (kf_id, video_id, frame_number, timestamp_sec, image_b64, change_score, ocr_text, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return kf_id

def get_keyframes_for_video(video_id):
    """Return all keyframes for a given video, sorted by timestamp."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
            db = get_db()
            rows = db.keyframes.find(
                {"video_id": video_id}
            ).sort("timestamp_sec", ASCENDING)

            keyframes = []
            for kf in rows:
                entry = {
                    "id": str(kf["_id"]),
                    "video_id": kf["video_id"],
                    "frame_number": kf["frame_number"],
                    "timestamp_sec": kf["timestamp_sec"],
                    "change_score": kf.get("change_score"),
                    "ocr_text": kf.get("ocr_text", ""),
                    "created_at": kf.get("created_at", ""),
                }
                if kf.get("image_b64"):
                    entry["image_bytes"] = base64.b64decode(kf["image_b64"])
                keyframes.append(entry)
            return keyframes
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB query failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keyframes WHERE video_id = ? ORDER BY timestamp_sec ASC", (video_id,))
    rows = cursor.fetchall()
    keyframes = []
    for r in rows:
        entry = {
            "id": r["id"],
            "video_id": r["video_id"],
            "frame_number": r["frame_number"],
            "timestamp_sec": r["timestamp_sec"],
            "change_score": r["change_score"],
            "ocr_text": r["ocr_text"] or "",
            "created_at": r["created_at"] or "",
        }
        if r["image_b64"]:
            entry["image_bytes"] = base64.b64decode(r["image_b64"])
        keyframes.append(entry)
    conn.close()
    return keyframes

def search_keyframes(query):
    """Search keyframes by OCR text (case-insensitive regex match)."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
            db = get_db()
            rows = db.keyframes.find({
                "ocr_text": {"$regex": query, "$options": "i"}
            }).sort("timestamp_sec", ASCENDING)

            results = []
            video_cache = {}
            for kf in rows:
                vid = kf["video_id"]
                if vid not in video_cache:
                    v = db.videos.find_one({"_id": ObjectId(vid)})
                    video_cache[vid] = v["filename"] if v else "Unknown"

                entry = {
                    "id": str(kf["_id"]),
                    "video_filename": video_cache[vid],
                    "timestamp_sec": kf["timestamp_sec"],
                    "frame_number": kf.get("frame_number"),
                    "ocr_text": kf.get("ocr_text", ""),
                }
                if kf.get("image_b64"):
                    entry["image_bytes"] = base64.b64decode(kf["image_b64"])
                results.append(entry)
            return results
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB search failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT k.*, v.filename as video_filename FROM keyframes k JOIN videos v ON k.video_id = v.id WHERE k.ocr_text LIKE ? ORDER BY k.timestamp_sec ASC",
        (f"%{query}%",)
    )
    rows = cursor.fetchall()
    results = []
    for r in rows:
        entry = {
            "id": r["id"],
            "video_filename": r["video_filename"],
            "timestamp_sec": r["timestamp_sec"],
            "frame_number": r["frame_number"],
            "ocr_text": r["ocr_text"] or "",
        }
        if r["image_b64"]:
            entry["image_bytes"] = base64.b64decode(r["image_b64"])
        results.append(entry)
    conn.close()
    return results

# ---------------------------------------------------------------------------
# Lookups, deletion, updates, stats
# ---------------------------------------------------------------------------
def get_video_by_id(video_id):
    """Return a single video dict, or None."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
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
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB query failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    v = cursor.fetchone()
    if not v:
        conn.close()
        return None
    res = {
        "id": v["id"],
        "filename": v["filename"],
        "uploaded_at": v["uploaded_at"],
        "duration_sec": v["duration_sec"],
        "total_frames": v["total_frames"],
        "fps": v["fps"],
        "processing": bool(v["processing"]),
    }
    conn.close()
    return res

def get_keyframe_by_id(kf_id):
    """Return a single keyframe dict (with image_bytes), or None."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
            db = get_db()
            kf = db.keyframes.find_one({"_id": ObjectId(kf_id)})
            if not kf:
                return None
            entry = {
                "id": str(kf["_id"]),
                "video_id": kf["video_id"],
                "frame_number": kf["frame_number"],
                "timestamp_sec": kf["timestamp_sec"],
                "change_score": kf.get("change_score"),
                "ocr_text": kf.get("ocr_text", ""),
            }
            if kf.get("image_b64"):
                entry["image_bytes"] = base64.b64decode(kf["image_b64"])
            return entry
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB query failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM keyframes WHERE id = ?", (kf_id,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        return None
    entry = {
        "id": r["id"],
        "video_id": r["video_id"],
        "frame_number": r["frame_number"],
        "timestamp_sec": r["timestamp_sec"],
        "change_score": r["change_score"],
        "ocr_text": r["ocr_text"] or "",
    }
    if r["image_b64"]:
        entry["image_bytes"] = base64.b64decode(r["image_b64"])
    conn.close()
    return entry

def delete_video(video_id):
    """Delete a video and all its keyframes."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
            db = get_db()
            db.keyframes.delete_many({"video_id": video_id})
            db.videos.delete_one({"_id": ObjectId(video_id)})
            return
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB delete failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM keyframes WHERE video_id = ?", (video_id,))
    cursor.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()

def update_video(video_id, duration_sec, total_frames, fps, processing=False):
    """Update video duration and frame counts (used after progressive processing)."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
            db = get_db()
            db.videos.update_one(
                {"_id": ObjectId(video_id)},
                {"$set": {
                    "duration_sec": duration_sec,
                    "total_frames": total_frames,
                    "fps": fps,
                    "processing": processing,
                }}
            )
            return
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB update failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE videos SET duration_sec = ?, total_frames = ?, fps = ?, processing = ? WHERE id = ?",
        (duration_sec, total_frames, fps, 1 if processing else 0, video_id)
    )
    conn.commit()
    conn.close()

def get_stats():
    """Return dashboard statistics."""
    global USE_SQLITE
    if not USE_SQLITE:
        try:
            db = get_db()
            return {
                "total_videos": db.videos.count_documents({}),
                "total_keyframes": db.keyframes.count_documents({}),
            }
        except mongo_errors.PyMongoError as e:
            print(f"MongoDB query failed: {e}. Switching to local SQLite.")
            USE_SQLITE = True
            init_sqlite_db()

    # SQLite fallback
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM videos")
    total_videos = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM keyframes")
    total_keyframes = cursor.fetchone()[0]
    conn.close()
    return {
        "total_videos": total_videos,
        "total_keyframes": total_keyframes,
    }

# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("Database initialization successful!")
    print(f"Using SQLite: {USE_SQLITE}")
    if USE_SQLITE:
        conn = get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM videos")
        print(f"  Local videos count:   {cursor.fetchone()[0]}")
        conn.close()
    else:
        db = get_db()
        print(f"  Videos collection count:    {db.videos.count_documents({})}")
        print(f"  Keyframes collection count: {db.keyframes.count_documents({})}")
