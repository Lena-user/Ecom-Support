"""Lưu trữ file đính kèm (ảnh) do khách hàng gửi kèm khiếu nại — chỉ lưu &
hiển thị, không phân tích nội dung ảnh."""

import uuid
from pathlib import Path

UPLOAD_DIR = Path("uploads")

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_SIZE = 5 * 1024 * 1024  # 5MB


def save_upload(content: bytes, content_type: str) -> str:
    """Validate và lưu file, trả về URL public (`/uploads/<filename>`)."""
    if content_type not in ALLOWED_TYPES:
        raise ValueError(f"Định dạng file không được hỗ trợ: {content_type}")
    if len(content) > MAX_SIZE:
        raise ValueError("File vượt quá dung lượng cho phép (5MB)")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"
    (UPLOAD_DIR / filename).write_bytes(content)
    return f"/uploads/{filename}"
