from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.config import Settings


class AppStorage:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def is_remote(self) -> bool:
        return self.settings.storage_backend == "r2"

    @property
    def description(self) -> str:
        if not self.is_remote:
            return str(self.settings.storage_dir)
        prefix = _clean_prefix(self.settings.r2_prefix)
        suffix = f"/{prefix}" if prefix else ""
        return f"r2://{self._bucket_name()}{suffix}"

    def url_for_path(self, path: Path | str) -> str:
        key = self.key_for_path(path)
        if self.is_remote and self.settings.r2_public_base_url:
            return f"{self.settings.r2_public_base_url.rstrip('/')}/{quote(self._object_prefix(key))}"
        if self.is_remote:
            return f"/api/v1/storage/files/{quote(key)}"
        return f"/storage/{quote(key)}"

    def key_for_path(self, path: Path | str) -> str:
        raw_path = Path(path)
        if raw_path.is_absolute():
            try:
                relative = raw_path.resolve().relative_to(self.settings.storage_dir.resolve())
            except ValueError as exc:
                raise ValueError("Storage path escapes the configured storage root.") from exc
            return relative.as_posix()
        return _clean_key(str(path))

    def local_path_for_key(self, key: str) -> Path:
        clean_key = _clean_key(key)
        candidate = (self.settings.storage_dir / clean_key).resolve()
        try:
            candidate.relative_to(self.settings.storage_dir.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid storage path.") from exc
        return candidate

    def usage_bytes(self) -> int:
        if not self.is_remote:
            return _directory_size(self.settings.storage_dir)

        total = 0
        client = self._r2_client()
        bucket = self._bucket_name()
        token: str | None = None
        prefix = self._object_prefix("")
        while True:
            kwargs: dict[str, object] = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            total += sum(int(item.get("Size", 0)) for item in response.get("Contents", []))
            if not response.get("IsTruncated"):
                return total
            token = response.get("NextContinuationToken")

    def job_count(self) -> int:
        if not self.is_remote:
            jobs_dir = self.settings.storage_dir / "jobs"
            if not jobs_dir.exists():
                return 0
            return sum(1 for item in jobs_dir.iterdir() if item.is_dir())

        client = self._r2_client()
        response = client.list_objects_v2(
            Bucket=self._bucket_name(),
            Prefix=self._object_prefix("jobs/"),
            Delimiter="/",
        )
        return len(response.get("CommonPrefixes", []))

    def upload_file(self, path: Path | str, *, content_type: str | None = None) -> None:
        if not self.is_remote:
            return
        local_path = Path(path)
        key = self.key_for_path(local_path)
        extra_args = {"ContentType": content_type or _guess_content_type(local_path.name)}
        self._r2_client().upload_file(
            str(local_path),
            self._bucket_name(),
            self._object_prefix(key),
            ExtraArgs=extra_args,
        )

    def upload_tree(self, root: Path) -> None:
        if not self.is_remote or not root.exists():
            return
        for item in root.rglob("*"):
            if item.is_file():
                self.upload_file(item)

    def download_file(self, key: str, destination: Path) -> bool:
        if not self.is_remote:
            return destination.is_file()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._r2_client().download_file(
                self._bucket_name(),
                self._object_prefix(key),
                str(destination),
            )
            return True
        except Exception as exc:
            if _is_not_found_error(exc):
                return False
            raise

    def delete_prefix(self, key_prefix: str) -> None:
        if not self.is_remote:
            return
        client = self._r2_client()
        bucket = self._bucket_name()
        prefix = self._object_prefix(key_prefix)
        token: str | None = None
        while True:
            kwargs: dict[str, object] = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            if not response.get("IsTruncated"):
                return
            token = response.get("NextContinuationToken")

    def response_for_path(
        self,
        path: Path | str,
        *,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> FileResponse | StreamingResponse:
        key = self.key_for_path(path)
        local_path = self.local_path_for_key(key)
        content_type = media_type or _guess_content_type(local_path.name)
        if not self.is_remote:
            if not local_path.is_file():
                raise HTTPException(status_code=404, detail="Storage object not found.")
            return FileResponse(local_path, media_type=content_type, filename=filename)

        try:
            obj = self._r2_client().get_object(Bucket=self._bucket_name(), Key=self._object_prefix(key))
        except Exception as exc:
            if _is_not_found_error(exc):
                raise HTTPException(status_code=404, detail="Storage object not found.") from exc
            raise

        headers = {}
        if filename:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return StreamingResponse(
            _iter_body(obj["Body"]),
            media_type=obj.get("ContentType") or content_type,
            headers=headers,
        )

    def _object_prefix(self, key: str) -> str:
        clean_prefix = _clean_prefix(self.settings.r2_prefix)
        clean_key = _clean_key(key)
        return f"{clean_prefix}/{clean_key}" if clean_prefix and clean_key else clean_prefix or clean_key

    def _bucket_name(self) -> str:
        if not self.settings.r2_bucket_name:
            raise RuntimeError("VEINCAD_R2_BUCKET_NAME is required when VEINCAD_STORAGE_BACKEND=r2.")
        return self.settings.r2_bucket_name

    def _r2_client(self):
        if not self.settings.r2_endpoint_url:
            raise RuntimeError("VEINCAD_R2_ACCOUNT_ID is required when VEINCAD_STORAGE_BACKEND=r2.")
        if not self.settings.r2_access_key_id:
            raise RuntimeError("VEINCAD_R2_ACCESS_KEY_ID is required when VEINCAD_STORAGE_BACKEND=r2.")
        if not self.settings.r2_secret_access_key:
            raise RuntimeError("VEINCAD_R2_SECRET_ACCESS_KEY is required when VEINCAD_STORAGE_BACKEND=r2.")

        import boto3

        return boto3.client(
            "s3",
            endpoint_url=self.settings.r2_endpoint_url,
            aws_access_key_id=self.settings.r2_access_key_id,
            aws_secret_access_key=self.settings.r2_secret_access_key,
            region_name="auto",
        )


def _clean_prefix(value: str | None) -> str:
    if not value:
        return ""
    return _clean_key(value)


def _clean_key(value: str) -> str:
    key = value.replace("\\", "/").strip("/")
    parts = [part for part in key.split("/") if part and part not in {".", ".."}]
    return "/".join(parts)


def _guess_content_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _iter_body(body: BinaryIO):
    try:
        while chunk := body.read(1024 * 1024):
            yield chunk
    finally:
        body.close()


def _is_not_found_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {})
    code = str(error.get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}
