"""
PDF 파일 → 텍스트 추출.

engine 인자로 추출 방식을 선택한다.

지원 엔진:
    "pdfplumber" (기본) — 표/레이아웃 보존에 강함
    "pypdf2"            — 경량, 단순 텍스트 추출
    "pymupdf"           — 빠르고 정확 (fitz 패키지 필요)
    "pdfminer"          — 복잡한 레이아웃 분석에 강함
    "auto"              — pdfplumber → pymupdf → pdfminer → pypdf2 순으로 폴백

사용 예:
    doc = load_pdf("report.pdf")                        # 기본(pdfplumber)
    doc = load_pdf("report.pdf", engine="pymupdf")      # 엔진 지정
    doc = load_pdf("report.pdf", engine="auto")         # 자동 폴백
    docs = load_from_collected(pdf_files_data)          # pdf_files.json 일괄 로딩
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Callable

from .models import Document

# ──────────────────────────────────────────
# 엔진별 추출 함수
# ──────────────────────────────────────────

def _with_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError as e:
        raise ImportError("pip install pdfplumber") from e

    texts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            texts.append((page.extract_text() or "").strip())
    return "\n\n".join(t for t in texts if t)


def _with_pypdf2(path: Path) -> str:
    try:
        from PyPDF2 import PdfReader
    except ImportError as e:
        raise ImportError("pip install PyPDF2") from e

    reader = PdfReader(str(path))
    texts: list[str] = []
    for page in reader.pages:
        texts.append((page.extract_text() or "").strip())
    return "\n\n".join(t for t in texts if t)


def _with_pymupdf(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ImportError("pip install pymupdf") from e

    texts: list[str] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            texts.append(page.get_text().strip())
    return "\n\n".join(t for t in texts if t)


def _with_pdfminer(path: Path) -> str:
    try:
        from pdfminer.high_level import extract_text
    except ImportError as e:
        raise ImportError("pip install pdfminer.six") from e

    return (extract_text(str(path)) or "").strip()


# 엔진 이름 → 추출 함수 레지스트리
_ENGINES: dict[str, Callable[[Path], str]] = {
    "pdfplumber": _with_pdfplumber,
    "pypdf2":     _with_pypdf2,
    "pymupdf":    _with_pymupdf,
    "pdfminer":   _with_pdfminer,
}

# "auto" 모드에서 시도할 순서
_AUTO_ORDER = ["pdfplumber", "pymupdf", "pdfminer", "pypdf2"]


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ──────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────

def load_pdf(
    path: str | Path,
    metadata: dict | None = None,
    engine: str = "pdfplumber",
) -> Document | None:
    """
    단일 PDF 파일 → Document.

    Args:
        path:     PDF 파일 경로
        metadata: 추가 메타정보 (ticker, category 등)
        engine:   추출 엔진 선택
                  "pdfplumber" | "pypdf2" | "pymupdf" | "pdfminer" | "auto"

    Returns:
        Document 또는 None (파일 없음 / 추출 실패)

    Raises:
        ValueError: 알 수 없는 engine 값
    """
    file_path = Path(path)
    if not file_path.exists():
        return None

    if engine not in (*_ENGINES, "auto"):
        raise ValueError(
            f"지원하지 않는 엔진: {engine!r}. "
            f"사용 가능: {list(_ENGINES)} + ['auto']"
        )

    text = ""
    if engine == "auto":
        for eng_name in _AUTO_ORDER:
            try:
                text = _clean(_ENGINES[eng_name](file_path))
                if text:
                    break
            except Exception:
                continue
    else:
        try:
            text = _clean(_ENGINES[engine](file_path))
        except Exception:
            return None

    if not text:
        return None

    return Document(
        text=text,
        source=str(file_path.resolve()),
        source_type="pdf",
        metadata={
            **(metadata or {}),
            "filename": file_path.name,
            "engine": engine,
        },
    )


def load_pdfs_from_dir(
    directory: str | Path,
    glob_pattern: str = "**/*.pdf",
    engine: str = "pdfplumber",
    metadata_fn=None,
) -> list[Document]:
    """
    디렉터리 내 모든 PDF → Document 리스트.

    Args:
        directory:    탐색할 폴더 경로
        glob_pattern: 파일 탐색 패턴 (기본: 모든 하위 폴더 포함)
        engine:       추출 엔진 (load_pdf 와 동일 옵션)
        metadata_fn:  (Path) → dict, 파일별 메타정보 생성 함수 (선택)
    """
    base = Path(directory)
    documents: list[Document] = []

    for pdf_path in sorted(base.glob(glob_pattern)):
        meta = metadata_fn(pdf_path) if metadata_fn else {}
        doc = load_pdf(pdf_path, metadata=meta, engine=engine)
        if doc:
            documents.append(doc)

    return documents


def load_from_collected(
    pdf_files_data: dict,
    engine: str = "pdfplumber",
) -> list[Document]:
    """
    collected_datas/.../pdf_files.json 의 data 딕셔너리를 받아
    각 PDF 파일을 로딩해 Document 리스트로 반환.

    Args:
        pdf_files_data: fetch_pdf_files()가 반환한 dict
                        {"directory": str, "count": int,
                         "files": [{"filename": str, "path": str, "size_kb": float}, ...]}
        engine:         추출 엔진 (load_pdf 와 동일 옵션)
    """
    documents: list[Document] = []

    for file_info in pdf_files_data.get("files", []):
        path = file_info.get("path", "")
        if not path:
            continue
        doc = load_pdf(
            path=path,
            metadata={
                "filename": file_info.get("filename", ""),
                "size_kb": file_info.get("size_kb", 0),
            },
            engine=engine,
        )
        if doc:
            documents.append(doc)

    return documents
