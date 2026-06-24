import logging
import mimetypes
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_S3_REGION = "us-east-1"
DEFAULT_VIDEO_S3_PREFIX = "videos"
DEFAULT_VIDEO_CONTENT_TYPE = "video/mp4"
DEFAULT_VIDEO_SIGNED_URL_SECONDS = 60 * 60 * 24
SUPABASE_KEY_ENV_VARS = (
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SECRET_KEY",
)


@dataclass(frozen=True)
class StoredVideo:
    bucket: str
    key: str
    s3_uri: str
    public_url: Optional[str]
    signed_url: Optional[str]
    content_type: str
    size_bytes: int
    metadata: Dict[str, str]

    def response_metadata(self) -> Dict[str, Any]:
        return {
            "bucket": self.bucket,
            "key": self.key,
            "s3Uri": self.s3_uri,
            "publicUrl": self.public_url,
            "signedUrl": self.signed_url,
            "url": self.public_url or self.signed_url,
            "contentType": self.content_type,
            "sizeBytes": self.size_bytes,
            "metadata": self.metadata,
        }


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def _first_env(names: tuple[str, ...], default: Optional[str] = None) -> Optional[str]:
    for name in names:
        value = _env(name)
        if value is not None:
            return value
    return default


def _safe_path_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-._")
    return cleaned or fallback


def _video_prefix() -> str:
    prefix = _env("VIDEO_S3_PREFIX", DEFAULT_VIDEO_S3_PREFIX) or DEFAULT_VIDEO_S3_PREFIX
    return "/".join(_safe_path_part(part, "videos") for part in prefix.split("/") if part.strip())


def _public_url(public_base_url: str, key: str) -> str:
    return f"{public_base_url.rstrip('/')}/{quote(key, safe='/')}"


def _has_aws_credential_source() -> bool:
    if _env("AWS_ACCESS_KEY_ID") and _env("AWS_SECRET_ACCESS_KEY"):
        return True
    credential_envs = (
        "AWS_PROFILE",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_ROLE_ARN",
    )
    return any(_env(name) for name in credential_envs)


def _supabase_url() -> Optional[str]:
    return _env("SUPABASE_URL") or _env("NEXT_PUBLIC_SUPABASE_URL")


def _supabase_service_key() -> Optional[str]:
    return _first_env(SUPABASE_KEY_ENV_VARS)


def _supabase_client_enabled() -> bool:
    return bool(_supabase_url() and _supabase_service_key())


def _supabase_storage_bucket(bucket: str):
    supabase_url = _supabase_url()
    service_key = _supabase_service_key()
    if not supabase_url or not service_key:
        raise RuntimeError("Supabase video upload requires SUPABASE_URL plus SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY.")

    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError("Supabase client is not installed. Run pip install -r backend/requirements.txt.") from exc

    return create_client(supabase_url, service_key).storage.from_(bucket)


def _signed_url_seconds() -> int:
    raw_value = _env("VIDEO_SIGNED_URL_SECONDS")
    if raw_value:
        try:
            return max(60, int(raw_value))
        except ValueError:
            pass
    return DEFAULT_VIDEO_SIGNED_URL_SECONDS


def create_signed_video_url(bucket: str, key: str, expires_in: Optional[int] = None) -> Optional[str]:
    if not bucket or not key or not _supabase_client_enabled():
        return None
    signed = _supabase_storage_bucket(bucket).create_signed_url(key, expires_in or _signed_url_seconds())
    return signed.get("signedURL") or signed.get("signedUrl")


def get_video_storage_config() -> Dict[str, Any]:
    bucket = _env("VIDEO_S3_BUCKET")
    region = _env("VIDEO_S3_REGION", DEFAULT_VIDEO_S3_REGION) or DEFAULT_VIDEO_S3_REGION
    public_base_url = _env("VIDEO_S3_PUBLIC_BASE_URL")
    endpoint_url = _env("VIDEO_S3_ENDPOINT_URL") or _env("AWS_ENDPOINT_URL_S3")
    has_static_keys = bool(_env("AWS_ACCESS_KEY_ID") and _env("AWS_SECRET_ACCESS_KEY"))
    has_credential_source = _has_aws_credential_source()
    supabase_client_enabled = _supabase_client_enabled()
    return {
        "enabled": bool(bucket and region and (has_credential_source or supabase_client_enabled)),
        "bucket": bucket,
        "region": region,
        "prefix": _video_prefix(),
        "public_base_url": public_base_url.rstrip("/") if public_base_url else None,
        "endpoint_url": endpoint_url,
        "write_method": "s3" if has_credential_source else "supabase-client" if supabase_client_enabled else None,
        "bucket_configured": bool(bucket),
        "region_configured": bool(region),
        "static_access_key_configured": has_static_keys,
        "credential_source_configured": has_credential_source,
        "supabase_url_configured": bool(_supabase_url()),
        "supabase_service_key_configured": bool(_supabase_service_key()),
    }


def ensure_video_storage_configured() -> Dict[str, Any]:
    config = get_video_storage_config()
    if not config["bucket_configured"]:
        raise RuntimeError("Video S3 storage is missing VIDEO_S3_BUCKET.")
    if not config["region_configured"]:
        raise RuntimeError("Video S3 storage is missing VIDEO_S3_REGION.")
    if not config["credential_source_configured"] and config["write_method"] != "supabase-client":
        raise RuntimeError("Video S3 storage requires AWS credentials or SUPABASE_URL plus SUPABASE_SERVICE_ROLE_KEY before calling GMI.")
    return config


def _content_type_from_url(video_url: str) -> str:
    path = urlparse(video_url).path
    guessed, _ = mimetypes.guess_type(path)
    if guessed and guessed.startswith("video/"):
        return guessed
    return DEFAULT_VIDEO_CONTENT_TYPE


def _download_video(video_url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(video_url, headers={"User-Agent": "Blueprint-OSS/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        content = response.read()
        content_type = response.headers.get_content_type() or _content_type_from_url(video_url)
    if not content:
        raise RuntimeError("Generated video download was empty.")
    if not content_type.startswith("video/"):
        content_type = DEFAULT_VIDEO_CONTENT_TYPE
    return content, content_type


def build_video_object_key(project_id: str, request_id: str, index: int = 0) -> str:
    if not project_id or not str(project_id).strip():
        raise ValueError("Video upload requires projectId.")
    if not request_id or not str(request_id).strip():
        raise ValueError("Video upload requires requestId.")

    prefix = _video_prefix()
    project_part = _safe_path_part(project_id, "project")
    request_part = _safe_path_part(request_id, "request")
    suffix = "" if index == 0 else f"-{index + 1}"
    return f"{prefix}/{project_part}/{request_part}{suffix}.mp4"


def _legacy_video_object_key(project_id: str, request_id: str, index: int = 0) -> str:
    project_part = _safe_path_part(project_id, "project")
    request_part = _safe_path_part(request_id, "request")
    suffix = "" if index == 0 else f"-{index + 1}"
    return f"projects/{project_part}/videos/{request_part}{suffix}.mp4"


def _stored_video_from_key(
    *,
    bucket: str,
    key: str,
    content_type: str = DEFAULT_VIDEO_CONTENT_TYPE,
    size_bytes: int = 0,
    metadata: Optional[Dict[str, str]] = None,
) -> StoredVideo:
    config = get_video_storage_config()
    public_url = _public_url(config["public_base_url"], key) if config.get("public_base_url") else None
    signed_url = create_signed_video_url(bucket, key)
    return StoredVideo(
        bucket=bucket,
        key=key,
        s3_uri=f"s3://{bucket}/{key}",
        public_url=public_url,
        signed_url=signed_url,
        content_type=content_type,
        size_bytes=size_bytes,
        metadata=metadata or {},
    )


def _stored_video_from_supabase_key(bucket: str, key: str, metadata: Optional[Dict[str, str]] = None) -> StoredVideo:
    content_type = DEFAULT_VIDEO_CONTENT_TYPE
    size_bytes = 0
    try:
        item = _supabase_storage_bucket(bucket).info(key)
        item_content_type, item_size_bytes = _metadata_from_storage_item(item)
        content_type = item_content_type or content_type
        size_bytes = item_size_bytes
    except Exception:
        pass
    return _stored_video_from_key(
        bucket=bucket,
        key=key,
        content_type=content_type,
        size_bytes=size_bytes,
        metadata=metadata,
    )


def _existing_or_legacy_supabase_video(
    *,
    bucket: str,
    project_id: str,
    request_id: str,
    key: str,
    metadata: Dict[str, str],
    index: int,
) -> Optional[StoredVideo]:
    bucket_proxy = _supabase_storage_bucket(bucket)
    try:
        if bucket_proxy.exists(key):
            return _stored_video_from_supabase_key(bucket, key, metadata)
    except Exception:
        pass

    legacy_key = _legacy_video_object_key(project_id, request_id, index)
    if legacy_key == key:
        return None

    try:
        if not bucket_proxy.exists(legacy_key):
            return None
        try:
            bucket_proxy.copy(legacy_key, key)
        except Exception as exc:
            if "already exists" not in str(exc).lower() and "duplicate" not in str(exc).lower():
                raise
        return _stored_video_from_supabase_key(bucket, key, metadata)
    except Exception:
        logger.exception(
            "Legacy video copy failed for project_id=%s request_id=%s source_key=%s destination_key=%s",
            project_id,
            request_id,
            legacy_key,
            key,
        )
        return None


def upload_generated_video_to_s3(
    video_url: str,
    *,
    project_id: str,
    request_id: str,
    model: str,
    index: int = 0,
) -> StoredVideo:
    import boto3

    config = ensure_video_storage_configured()
    key = build_video_object_key(project_id, request_id, index)
    metadata = {
        "projectId": str(project_id),
        "requestId": str(request_id),
        "model": str(model),
        "source": "gmi-cloud",
    }

    if config["write_method"] == "supabase-client":
        existing_video = _existing_or_legacy_supabase_video(
            bucket=config["bucket"],
            project_id=project_id,
            request_id=request_id,
            key=key,
            metadata=metadata,
            index=index,
        )
        if existing_video:
            return existing_video

        content, content_type = _download_video(video_url)
        bucket_proxy = _supabase_storage_bucket(config["bucket"])
        bucket_proxy.upload(
            key,
            content,
            file_options={
                "content-type": content_type,
                "cache-control": "31536000",
                "upsert": "true",
                "metadata": metadata,
            },
        )
        return _stored_video_from_key(
            bucket=config["bucket"],
            key=key,
            content_type=content_type,
            size_bytes=len(content),
            metadata=metadata,
        )

    content, content_type = _download_video(video_url)
    client_kwargs: Dict[str, Any] = {"region_name": config["region"]}
    if config.get("endpoint_url"):
        client_kwargs["endpoint_url"] = config["endpoint_url"]
    client = boto3.client("s3", **client_kwargs)
    client.put_object(
        Bucket=config["bucket"],
        Key=key,
        Body=content,
        ContentType=content_type,
        Metadata=metadata,
    )

    public_url = _public_url(config["public_base_url"], key) if config.get("public_base_url") else None
    return StoredVideo(
        bucket=config["bucket"],
        key=key,
        s3_uri=f"s3://{config['bucket']}/{key}",
        public_url=public_url,
        signed_url=None,
        content_type=content_type,
        size_bytes=len(content),
        metadata=metadata,
    )


def upload_generated_videos_to_s3(
    video_urls: List[str],
    *,
    project_id: str,
    request_id: str,
    model: str,
) -> List[StoredVideo]:
    stored: List[StoredVideo] = []
    for index, video_url in enumerate(video_urls):
        try:
            stored.append(
                upload_generated_video_to_s3(
                    video_url,
                    project_id=project_id,
                    request_id=request_id,
                    model=model,
                    index=index,
                )
            )
        except Exception:
            logger.exception(
                "Video S3 upload failed for project_id=%s request_id=%s source_url=%s",
                project_id,
                request_id,
                video_url,
            )
            raise
    return stored


def _metadata_from_storage_item(item: Dict[str, Any]) -> tuple[str, int]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    content_type = metadata.get("mimetype") or metadata.get("contentType") or DEFAULT_VIDEO_CONTENT_TYPE
    size_bytes = metadata.get("size") or item.get("size") or 0
    try:
        size_bytes = int(size_bytes)
    except (TypeError, ValueError):
        size_bytes = 0
    return str(content_type), size_bytes


def _list_supabase_project_videos(config: Dict[str, Any], project_id: str) -> List[StoredVideo]:
    project_part = _safe_path_part(project_id, "project")
    folders = [f"{config['prefix']}/{project_part}"]
    legacy_folder = f"projects/{project_part}/videos"
    if legacy_folder not in folders:
        folders.append(legacy_folder)

    bucket_proxy = _supabase_storage_bucket(config["bucket"])
    videos: List[StoredVideo] = []
    seen_keys = set()
    seen_names = set()
    for folder in folders:
        try:
            items = bucket_proxy.list(
                folder,
                {
                    "limit": 100,
                    "sortBy": {"column": "created_at", "order": "desc"},
                },
            )
        except Exception:
            logger.exception("Video gallery list failed for bucket=%s folder=%s", config["bucket"], folder)
            continue

        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"]
            if not name.lower().endswith((".mp4", ".mov", ".webm", ".m4v")):
                continue
            key = f"{folder}/{name}"
            if key in seen_keys or name in seen_names:
                continue
            seen_keys.add(key)
            seen_names.add(name)
            content_type, size_bytes = _metadata_from_storage_item(item)
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            videos.append(
                _stored_video_from_key(
                    bucket=config["bucket"],
                    key=key,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    metadata={str(k): str(v) for k, v in metadata.items()},
                )
            )

    return videos


def _list_s3_project_videos(config: Dict[str, Any], project_id: str) -> List[StoredVideo]:
    import boto3

    project_part = _safe_path_part(project_id, "project")
    prefix = f"{config['prefix']}/{project_part}/"
    client_kwargs: Dict[str, Any] = {"region_name": config["region"]}
    if config.get("endpoint_url"):
        client_kwargs["endpoint_url"] = config["endpoint_url"]
    client = boto3.client("s3", **client_kwargs)
    response = client.list_objects_v2(Bucket=config["bucket"], Prefix=prefix, MaxKeys=100)
    contents = response.get("Contents") or []
    videos: List[StoredVideo] = []
    for item in contents:
        key = item.get("Key")
        if not isinstance(key, str) or not key.lower().endswith((".mp4", ".mov", ".webm", ".m4v")):
            continue
        videos.append(
            _stored_video_from_key(
                bucket=config["bucket"],
                key=key,
                content_type=DEFAULT_VIDEO_CONTENT_TYPE,
                size_bytes=int(item.get("Size") or 0),
            )
        )
    return videos


def list_project_videos(project_id: str) -> List[StoredVideo]:
    if not project_id or not str(project_id).strip():
        raise ValueError("Video gallery requires projectId.")

    config = ensure_video_storage_configured()
    if config["write_method"] == "supabase-client":
        return _list_supabase_project_videos(config, project_id)
    return _list_s3_project_videos(config, project_id)
