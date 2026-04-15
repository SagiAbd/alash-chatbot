"""OCR PDF pages concurrently using a vision-capable LLM."""

import asyncio
import base64
import logging
from typing import List

import fitz  # pymupdf
from langchain_core.messages import HumanMessage

from app.services.llm.llm_factory import LLMFactory

logger = logging.getLogger(__name__)

_MAX_CONCURRENCY = 6
_RENDER_DPI = 180
_OCR_PROMPT = (
    "Transcribe every readable word from this page image exactly as it appears. "
    "Preserve line breaks and original language. Do not add commentary, "
    "translations, or summaries. If the page is blank or unreadable, respond "
    "with an empty string."
)


def _render_pdf_pages(file_path: str) -> List[bytes]:
    """Rasterise every PDF page to PNG bytes."""
    document = fitz.open(file_path)
    try:
        return [page.get_pixmap(dpi=_RENDER_DPI).tobytes("png") for page in document]
    finally:
        document.close()


def _coerce_text(content) -> str:
    """Flatten a LangChain message ``content`` field into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)


async def _ocr_page(
    index: int, image_bytes: bytes, semaphore: asyncio.Semaphore
) -> dict:
    """OCR a single page image via the configured vision LLM."""
    async with semaphore:
        llm = LLMFactory.create(temperature=0, streaming=False)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        message = HumanMessage(
            content=[
                {"type": "text", "text": _OCR_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
            ]
        )
        try:
            response = await llm.ainvoke([message])
            text = _coerce_text(getattr(response, "content", response))
            return {"page": index + 1, "text": text.strip()}
        except Exception as exc:
            logger.warning("Vision OCR failed on PDF page %d: %s", index + 1, exc)
            return {"page": index + 1, "text": ""}


async def _extract_pages_async(file_path: str) -> List[dict]:
    images = await asyncio.to_thread(_render_pdf_pages, file_path)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
    results = await asyncio.gather(
        *[_ocr_page(idx, image, semaphore) for idx, image in enumerate(images)]
    )
    return [page for page in results if page["text"]]


def extract_pages_from_pdf(file_path: str) -> List[dict]:
    """Synchronous wrapper that runs vision-LLM OCR for every page in the PDF."""
    return asyncio.run(_extract_pages_async(file_path))
