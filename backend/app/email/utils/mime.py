import os
from typing import Tuple

# Standard constraints
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

def validate_attachment_content(content: bytes, filename: str, mime_type: str) -> Tuple[bool, str]:
    """
    Validate attachment content, filename extension, size, and magic bytes.

    Returns:
        Tuple[bool, str]: (is_valid, error_reason)
    """
    if not content:
        return False, "Attachment content is empty."

    # Size check
    if len(content) > MAX_FILE_SIZE_BYTES:
        return False, f"File size ({len(content)} bytes) exceeds the limit of 5MB."

    # Extension check
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Extension {ext} is not allowed. Only PDF and DOCX are allowed."

    # MIME type check
    if mime_type.lower() not in ALLOWED_MIME_TYPES:
        return False, f"MIME type {mime_type} is not allowed."

    # Magic bytes verification
    if ext == ".pdf":
        if not content.startswith(b"%PDF"):
            return False, "Invalid PDF: Content does not start with %PDF magic bytes."
    elif ext == ".docx":
        # DOCX is essentially a zip archive containing XML structures
        if not content.startswith(b"PK\x03\x04"):
            return False, "Invalid DOCX: Content does not start with PK ZIP archive magic bytes."

    return True, ""
