"""Ephemeral, session-owned images, normalized before any model or browser use."""

from __future__ import annotations

import io
import secrets
import shutil
import tempfile
import threading
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from campuspilot.llm.chat_model import IMAGE_MIME_TYPES, MAX_MODEL_IMAGE_BYTES, ImageInput

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_DECODE_PIXELS = 20_000_000
MAX_DECODE_SIDE = 10_000
MAX_IMAGE_SIDE = 2048


class AttachmentError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Attachment:
    attachment_id: str
    name: str
    mime_type: str
    size: int
    user: str = field(repr=False)
    expires: float = field(repr=False)
    path: Path = field(repr=False)

    def public(self) -> dict[str, str | int]:
        return {
            "attachment_id": self.attachment_id,
            "name": self.name,
            "mime_type": self.mime_type,
            "size": self.size,
        }


def normalize_image(data: bytes, mime_type: str) -> tuple[bytes, str]:
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise AttachmentError("attachment_size", "每张图片需在 10MB 以内。", 413)
    if mime_type not in IMAGE_MIME_TYPES:
        raise AttachmentError("attachment_format", "图片仅支持 JPEG、PNG、WebP。", 415)
    formats = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                width, height = original.size
                if (
                    formats.get(original.format or "") != mime_type
                    or width * height > MAX_DECODE_PIXELS
                    or max(width, height) > MAX_DECODE_SIDE
                    or getattr(original, "n_frames", 1) != 1
                ):
                    raise ValueError
                original.load()
                oriented = ImageOps.exif_transpose(original)
                oriented.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
                # Rebuild pixels so EXIF, location, comments and PNG text cannot be retained.
                rgba = oriented.convert("RGBA")
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                buffer = io.BytesIO()
                output_mime = "image/png" if mime_type != "image/jpeg" else "image/jpeg"
                if output_mime == "image/png":
                    clean.save(buffer, format="PNG")
                else:
                    clean.save(buffer, format="JPEG", quality=88)
                if buffer.tell() > MAX_MODEL_IMAGE_BYTES:
                    buffer = io.BytesIO()
                    clean.save(buffer, format="JPEG", quality=82)
                    output_mime = "image/jpeg"
                if buffer.tell() > MAX_MODEL_IMAGE_BYTES:
                    raise ValueError
                return buffer.getvalue(), output_mime
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
        SyntaxError,
    ):
        raise AttachmentError(
            "attachment_invalid", "图片损坏、格式不符、尺寸过大或包含多帧，请换一张图片。", 422
        ) from None


class AttachmentStore:
    """One process owns a private temp directory; IDs have no meaning after restart."""

    def __init__(
        self,
        *,
        directory: Path | None = None,
        session_capacity_bytes: int = 32 * 1024 * 1024,
        total_capacity_bytes: int = 256 * 1024 * 1024,
        max_session_images: int = 24,
    ) -> None:
        if min(session_capacity_bytes, total_capacity_bytes, max_session_images) < 1:
            raise ValueError("Attachment capacity must be positive")
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix="campuspilot-images-", dir=directory))
        self.directory.chmod(0o700)
        self.session_capacity_bytes = session_capacity_bytes
        self.total_capacity_bytes = total_capacity_bytes
        self.max_session_images = max_session_images
        self._items: dict[str, Attachment] = {}
        self._lock = threading.RLock()
        self._decoders = threading.BoundedSemaphore(2)
        self._closed = False

    def add(
        self, user: str, expires: float, data: bytes, mime_type: str, name: str
    ) -> Attachment:
        if not self._decoders.acquire(blocking=False):
            raise AttachmentError("attachment_busy", "图片正在处理中，请稍后重试。", 429)
        try:
            normalized, mime_type = normalize_image(data, mime_type)
        finally:
            self._decoders.release()
        name = name.replace("\\", "/").rsplit("/", 1)[-1].strip()[:160]
        if not name or any(ord(c) < 32 or ord(c) == 127 for c in name):
            name = "图片"
        with self._lock:
            if self._closed or expires <= time.monotonic():
                raise AttachmentError("attachment_expired", "本次会话已过期，请开启新对话。", 401)
            self.prune()
            owned = [item for item in self._items.values() if item.user == user]
            if (
                len(owned) >= self.max_session_images
                or sum(item.size for item in owned) + len(normalized) > self.session_capacity_bytes
                or sum(item.size for item in self._items.values()) + len(normalized)
                > self.total_capacity_bytes
            ):
                raise AttachmentError(
                    "attachment_capacity", "临时图片容量已满，请移除图片或开启新对话。", 429
                )
            identifier = secrets.token_urlsafe(24)
            path = self.directory / identifier
            try:
                path.write_bytes(normalized)
                path.chmod(0o600)
            except OSError:
                path.unlink(missing_ok=True)
                raise AttachmentError(
                    "attachment_unavailable", "图片暂时无法保存，请稍后重试。", 503
                ) from None
            item = Attachment(identifier, name, mime_type, len(normalized), user, expires, path)
            self._items[identifier] = item
            return item

    def get(self, user: str, identifier: str) -> Attachment:
        with self._lock:
            item = self._items.get(identifier)
            if item is not None and item.expires <= time.monotonic():
                self._remove(identifier)
                item = None
            if item is None or item.user != user:
                raise AttachmentError("attachment_missing", "图片已删除、已过期或无法访问。", 404)
            return item

    def read(self, user: str, identifier: str) -> ImageInput:
        with self._lock:
            item = self.get(user, identifier)
            try:
                data = item.path.read_bytes()
            except OSError:
                self._remove(identifier)
                raise AttachmentError(
                    "attachment_missing", "图片已不可用，请重新上传。", 404
                ) from None
            return ImageInput(item.attachment_id, item.mime_type, data)

    def delete(self, user: str, identifier: str) -> None:
        with self._lock:
            self.get(user, identifier)
            self._remove(identifier)

    def _remove(self, identifier: str) -> None:
        item = self._items.pop(identifier, None)
        if item is not None:
            item.path.unlink(missing_ok=True)

    def cleanup_session(self, user: str) -> None:
        with self._lock:
            for identifier, item in tuple(self._items.items()):
                if item.user == user:
                    self._remove(identifier)

    def prune(self, active_users: set[str] | None = None) -> None:
        with self._lock:
            now = time.monotonic()
            for identifier, item in tuple(self._items.items()):
                if item.expires <= now or (
                    active_users is not None and item.user not in active_users
                ):
                    self._remove(identifier)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._items.clear()
            shutil.rmtree(self.directory, ignore_errors=True)
