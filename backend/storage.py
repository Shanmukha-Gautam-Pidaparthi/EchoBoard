"""
storage.py
EchoBoard Dataset Creation Module — Image Storage Layer

Stores original keyframe images in MinIO object storage.
If MinIO is not available, falls back to local filesystem storage
under dataset/echoboard-dataset/ mirroring the MinIO bucket structure.

IMPORTANT: Images are stored as-is — NO compression, NO cropping, NO modification.
"""

import os
import io
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# ---------------------------------------------------------------------------
# MinIO Configuration — Loaded from .env
# ---------------------------------------------------------------------------
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "echoboard-dataset")

# Local fallback directory (mirrors MinIO bucket structure)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATASET_DIR = os.path.join(os.path.dirname(BASE_DIR), "dataset", "echoboard-dataset")

USE_MINIO = False
_minio_client = None


def _get_minio_client():
    """Return the MinIO client, creating it on first call."""
    global _minio_client
    if _minio_client is None:
        try:
            from minio import Minio
            _minio_client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
            )
        except ImportError:
            raise RuntimeError("minio package not installed. Run: pip install minio")
    return _minio_client


def init_storage():
    """Initialize storage backend. Try MinIO first, fall back to local filesystem."""
    global USE_MINIO

    try:
        client = _get_minio_client()
        # Test connection by checking if bucket exists
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
            print(f"  Created MinIO bucket: '{MINIO_BUCKET}'")
        else:
            print(f"  MinIO bucket '{MINIO_BUCKET}' ready.")
        USE_MINIO = True
        print(f"  Storage: MinIO ({MINIO_ENDPOINT})")
    except Exception as e:
        print(f"\n  WARNING: MinIO not available ({e})")
        print(f"  Falling back to local storage: {LOCAL_DATASET_DIR}\n")
        USE_MINIO = False
        os.makedirs(LOCAL_DATASET_DIR, exist_ok=True)


def store_image(image_bytes: bytes, subject: str, sequence_id: str,
                filename: str) -> str:
    """
    Store an original image in the dataset.

    Path structure: echoboard-dataset/<subject>/<sequence_id>/<filename>

    Returns the full object path (relative to the bucket root).

    IMPORTANT: The image is stored AS-IS — no compression, no cropping,
    no modification of any kind.
    """
    object_path = f"{subject}/{sequence_id}/{filename}"

    if USE_MINIO:
        try:
            client = _get_minio_client()
            data = io.BytesIO(image_bytes)
            client.put_object(
                MINIO_BUCKET,
                object_path,
                data,
                length=len(image_bytes),
                content_type="image/jpeg",
            )
            return object_path
        except Exception as e:
            print(f"  MinIO upload failed: {e}. Falling back to local storage.")

    # Local filesystem fallback
    local_path = os.path.join(LOCAL_DATASET_DIR, object_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(image_bytes)
    return object_path


def get_image(object_path: str) -> bytes:
    """
    Retrieve an image by its object path.
    Returns the raw image bytes.
    """
    if USE_MINIO:
        try:
            client = _get_minio_client()
            response = client.get_object(MINIO_BUCKET, object_path)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as e:
            print(f"  MinIO read failed: {e}. Trying local storage.")

    # Local filesystem fallback
    local_path = os.path.join(LOCAL_DATASET_DIR, object_path.replace("/", os.sep))
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            return f.read()
    return b""


def delete_image(object_path: str):
    """Delete an image from storage."""
    if USE_MINIO:
        try:
            client = _get_minio_client()
            client.remove_object(MINIO_BUCKET, object_path)
            return
        except Exception as e:
            print(f"  MinIO delete failed: {e}. Trying local storage.")

    # Local filesystem fallback
    local_path = os.path.join(LOCAL_DATASET_DIR, object_path.replace("/", os.sep))
    if os.path.exists(local_path):
        os.unlink(local_path)


def list_images(subject: str = None, sequence_id: str = None) -> list:
    """List all image object paths, optionally filtered by subject/sequence."""
    prefix = ""
    if subject:
        prefix = f"{subject}/"
        if sequence_id:
            prefix = f"{subject}/{sequence_id}/"

    if USE_MINIO:
        try:
            client = _get_minio_client()
            objects = client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects if obj.object_name.endswith((".jpg", ".jpeg", ".png"))]
        except Exception as e:
            print(f"  MinIO list failed: {e}. Trying local storage.")

    # Local filesystem fallback
    results = []
    search_dir = os.path.join(LOCAL_DATASET_DIR, prefix.replace("/", os.sep))
    if os.path.exists(search_dir):
        for root, dirs, files in os.walk(search_dir):
            for f in files:
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, LOCAL_DATASET_DIR).replace(os.sep, "/")
                    results.append(rel)
    return results
