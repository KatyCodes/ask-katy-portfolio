import base64
import binascii
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader

MAX_FILE_BYTES = 5 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


# Signals that an uploaded career source cannot be safely read.
class ProfileImportError(ValueError):
    pass


# Decodes and extracts text from a supported document without writing it to disk.
def extract_uploaded_text(filename: str, encoded_content: str) -> str:
    extension = Path(filename).suffix.casefold()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ProfileImportError("Upload a PDF, DOCX, TXT, or Markdown file")
    try:
        content = base64.b64decode(encoded_content, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProfileImportError("That file could not be read") from exc
    if not content or len(content) > MAX_FILE_BYTES:
        raise ProfileImportError("Files must be between 1 byte and 5 MB")
    try:
        if extension in {".txt", ".md"}:
            text = content.decode("utf-8")
        elif extension == ".pdf":
            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        else:
            text = "\n".join(paragraph.text for paragraph in Document(BytesIO(content)).paragraphs)
    except Exception as exc:
        raise ProfileImportError("That file appears damaged or unreadable") from exc
    cleaned = text.strip()
    if not cleaned:
        raise ProfileImportError("No readable text was found in that file")
    return cleaned[:60000]
