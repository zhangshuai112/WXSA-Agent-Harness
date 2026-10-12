"""Standalone multimodal document extraction tool powered by PaddleOCR.

The public ``extract_multimodal_file`` function accepts a local image/PDF path,
Base64 content, or a data URI and returns JSON-serializable OCR/layout data.
PaddleOCR is imported lazily so this module can be imported before the optional
OCR dependencies are installed.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PaddleOCRExtractionInput(BaseModel):
    """Input schema exposed to agent tool integrations."""

    file: str = Field(
        ...,
        description=(
            "Local image/PDF path, a Base64 string, or a data URI such as "
            "data:image/png;base64,..."
        ),
    )
    lang: str = Field(default="ch", description="PaddleOCR language, for example ch or en")
    use_layout: bool = Field(default=True, description="Enable document layout/table extraction")
    use_doc_orientation: bool = Field(default=True, description="Enable document orientation correction")
    use_doc_unwarping: bool = Field(default=True, description="Enable document image unwarping")
    use_textline_orientation: bool = Field(default=True, description="Enable text-line orientation detection")


def _require_paddleocr() -> Any:
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:  # pragma: no cover - depends on optional runtime
        raise RuntimeError(
            "PaddleOCR is required. Install a compatible PaddlePaddle runtime and "
            "PaddleOCR first: pip install paddlepaddle paddleocr"
        ) from exc
    return PaddleOCR


def _materialize_input(value: str) -> tuple[str, str | None, bool]:
    """Return a path, optional temporary path, and whether it is temporary."""
    candidate = Path(value)
    if candidate.is_file():
        return str(candidate), None, False

    raw = value
    suffix = ".png"
    if raw.startswith("data:"):
        try:
            header, encoded = raw.split(",", 1)
            mime = header[5:].split(";", 1)[0]
            suffix = mimetypes.guess_extension(mime) or suffix
            raw = encoded
        except ValueError as exc:
            raise ValueError("Invalid data URI") from exc

    try:
        content = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FileNotFoundError(
            f"Input is not an existing file or valid Base64 payload: {value[:80]}"
        ) from exc

    if content[:4] == b"%PDF":
        suffix = ".pdf"
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        handle.write(content)
    finally:
        handle.close()
    return handle.name, handle.name, True


def _to_jsonable(value: Any) -> Any:
    """Convert PaddleOCR result objects and numpy values to JSON-compatible data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _to_jsonable(value.tolist())
    if hasattr(value, "to_dict"):
        return _to_jsonable(value.to_dict())
    if hasattr(value, "__dict__"):
        return _to_jsonable({key: item for key, item in vars(value).items() if not key.startswith("_")})
    return str(value)


def _extract_text(result: Any) -> list[dict[str, Any]]:
    data = _to_jsonable(result)
    if isinstance(data, list):
        # PaddleOCR 2.x: [[[[x1, y1], ...], [text, score]], ...]
        items = []
        for line in data:
            if not isinstance(line, list) or len(line) < 2:
                continue
            box, recognition = line[0], line[1]
            if isinstance(recognition, list) and recognition:
                item: dict[str, Any] = {"text": str(recognition[0]), "box": box}
                if len(recognition) > 1:
                    item["confidence"] = float(recognition[1])
                items.append(item)
        return items
    if not isinstance(data, dict):
        return []
    texts = data.get("rec_texts") or data.get("texts") or []
    scores = data.get("rec_scores") or data.get("scores") or []
    boxes = data.get("rec_polys") or data.get("dt_polys") or data.get("boxes") or []
    items = []
    for index, text in enumerate(texts):
        item: dict[str, Any] = {"text": str(text)}
        if index < len(scores):
            item["confidence"] = float(scores[index])
        if index < len(boxes):
            item["box"] = boxes[index]
        items.append(item)
    return items


def _build_ocr(options: PaddleOCRExtractionInput) -> Any:
    PaddleOCR = _require_paddleocr()
    kwargs = {"lang": options.lang}
    # PaddleOCR 3.x uses these names. Keep construction isolated for compatibility.
    if options.use_layout:
        kwargs.update(
            use_doc_orientation_classify=options.use_doc_orientation,
            use_doc_unwarping=options.use_doc_unwarping,
            use_textline_orientation=options.use_textline_orientation,
        )
    try:
        return PaddleOCR(**kwargs)
    except TypeError:
        legacy = {"lang": options.lang, "use_angle_cls": options.use_textline_orientation}
        return PaddleOCR(**legacy)


def extract_multimodal_file(
    file: str,
    lang: str = "ch",
    use_layout: bool = True,
    use_doc_orientation: bool = True,
    use_doc_unwarping: bool = True,
    use_textline_orientation: bool = True,
) -> dict[str, Any]:
    """Extract text, boxes, layout and table data from an image or PDF.

    The result is JSON-serializable and keeps PaddleOCR's complete structured
    output under ``pages``. PDF page handling is delegated to the installed
    PaddleOCR version.
    """
    options = PaddleOCRExtractionInput(
        file=file,
        lang=lang,
        use_layout=use_layout,
        use_doc_orientation=use_doc_orientation,
        use_doc_unwarping=use_doc_unwarping,
        use_textline_orientation=use_textline_orientation,
    )
    source, temporary_path, is_temporary = _materialize_input(options.file)
    try:
        ocr = _build_ocr(options)
        if hasattr(ocr, "predict"):
            raw_results = ocr.predict(source)
        else:  # PaddleOCR 2.x compatibility
            raw_results = ocr.ocr(source, cls=options.use_textline_orientation)

        if isinstance(raw_results, dict):
            raw_results = [raw_results]
        pages = []
        all_text: list[dict[str, Any]] = []
        for page_number, result in enumerate(raw_results or [], start=1):
            structured = _to_jsonable(result)
            text_items = _extract_text(result)
            all_text.extend(text_items)
            pages.append({"page": page_number, "text": text_items, "result": structured})
        return {
            "success": True,
            "source": source if not is_temporary else "<base64-input>",
            "text": all_text,
            "text_content": "\n".join(item["text"] for item in all_text),
            "pages": pages,
        }
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def paddleocr_multimodal_tool(
    file: str | PaddleOCRExtractionInput | dict[str, Any],
    lang: str = "ch",
    use_layout: bool = True,
    use_doc_orientation: bool = True,
    use_doc_unwarping: bool = True,
    use_textline_orientation: bool = True,
) -> str:
    """Agent-friendly wrapper returning recognized text only.

    ``StructuredTool`` passes schema fields as keyword arguments, so the public
    signature must expose ``file`` and the optional OCR settings explicitly.
    """
    if isinstance(file, PaddleOCRExtractionInput):
        options = file
    elif isinstance(file, dict):
        options = PaddleOCRExtractionInput(**file)
    else:
        options = PaddleOCRExtractionInput(
            file=file,
            lang=lang,
            use_layout=use_layout,
            use_doc_orientation=use_doc_orientation,
            use_doc_unwarping=use_doc_unwarping,
            use_textline_orientation=use_textline_orientation,
        )
    result = extract_multimodal_file(**options.model_dump())
    return result["text_content"]


async def paddleocr_multimodal_tool_async(
    file: str | PaddleOCRExtractionInput | dict[str, Any],
    lang: str = "ch",
    use_layout: bool = True,
    use_doc_orientation: bool = True,
    use_doc_unwarping: bool = True,
    use_textline_orientation: bool = True,
) -> str:
    """Async wrapper: run OCR off the event loop."""
    return await asyncio.to_thread(
        paddleocr_multimodal_tool,
        file,
        lang,
        use_layout,
        use_doc_orientation,
        use_doc_unwarping,
        use_textline_orientation,
    )


try:
    from langchain_core.tools import StructuredTool

    paddleocr_tool = StructuredTool.from_function(
        func=paddleocr_multimodal_tool,
        coroutine=paddleocr_multimodal_tool_async,
        name="paddleocr_multimodal_extract",
        description="使用 PaddleOCR 从图片或 PDF 文件中提取多模态信息，包括文本内容、"
        "文字位置、识别置信度、分页结果以及版面/表格结构化信息。"
        "支持本地文件路径、Base64 字符串和 Data URI。",
        args_schema=PaddleOCRExtractionInput,
    )
except Exception:  # pragma: no cover - LangChain is optional for standalone use
    paddleocr_tool = paddleocr_multimodal_tool


__all__ = [
    "PaddleOCRExtractionInput",
    "extract_multimodal_file",
    "paddleocr_multimodal_tool",
    "paddleocr_multimodal_tool_async",
    "paddleocr_tool",
]

# if __name__ == '__main__':
#     print(paddleocr_tool.invoke(PaddleOCRExtractionInput(file=r"D:\Harness_hand_write\Harness_hand_write\test_datas\img.png")))
if __name__ == "__main__":
    result = paddleocr_tool.invoke({
        "file": r"D:\Harness_hand_write\Harness_hand_write\test_datas\img.png"
    })
    print(result)
