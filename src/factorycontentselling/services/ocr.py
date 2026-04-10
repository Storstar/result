from __future__ import annotations

from pathlib import Path


class OCRAdapter:
    def __init__(self) -> None:
        self._engine = None
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            self._engine = RapidOCR()
        except Exception:
            self._engine = None

    @property
    def available(self) -> bool:
        return self._engine is not None

    def extract_text(self, image_path: Path) -> list[str]:
        if not self._engine:
            return []
        try:
            results, _ = self._engine(str(image_path))
        except Exception:
            return []
        if not results:
            return []
        lines: list[str] = []
        for item in results:
            if len(item) < 2:
                continue
            text = str(item[1]).strip()
            if text:
                lines.append(text)
        return lines

