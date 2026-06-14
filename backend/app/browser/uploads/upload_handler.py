import os
import tempfile
import httpx
import structlog
from app.email.utils.mime import validate_attachment_content
from app.core.exceptions import InvalidAttachmentError, EmailConnectionResetError, EmailTimeoutError

logger = structlog.get_logger(__name__)

class UploadHandler:
    """
    Handles downloading resume and cover letter files from storage and preparing them for form upload.
    """

    def __init__(self) -> None:
        self._temp_files = []

    async def download_file(self, url: str, filename: str) -> str:
        """
        Downloads a file from storage and saves it to a local temporary path.
        Returns the absolute local path.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url)
                res.raise_for_status()
                content = res.content
        except httpx.TimeoutException as e:
            logger.error("browser.upload.download_timeout", url=url, error=str(e))
            raise EmailTimeoutError(f"Timeout while downloading asset: {e}")
        except Exception as e:
            logger.error("browser.upload.download_failed", url=url, error=str(e))
            raise EmailConnectionResetError(f"Failed to download asset: {e}")

        # MIME and size validation reuse from Phase B
        mime_type = "application/pdf"
        if filename.lower().endswith(".docx"):
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            
        is_valid, reason = validate_attachment_content(content, filename, mime_type)
        if not is_valid:
            logger.error("browser.upload.validation_failed", filename=filename, reason=reason)
            raise InvalidAttachmentError(f"File validation failed: {reason}")

        # Write to temp file
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, filename)
        with open(temp_path, "wb") as f:
            f.write(content)

        self._temp_files.append(temp_path)
        logger.info("browser.upload.downloaded_temp", filename=filename, temp_path=temp_path)
        return temp_path

    def cleanup(self) -> None:
        """
        Deletes all downloaded temporary files.
        """
        for path in self._temp_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info("browser.upload.temp_cleaned", path=path)
                except Exception as e:
                    logger.warning("browser.upload.cleanup_error", path=path, error=str(e))
        self._temp_files.clear()
