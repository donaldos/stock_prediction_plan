"""
중앙 로깅 설정.

로그 포맷: 시각 [레벨] 모듈.함수명:줄번호 — 메시지
로그 출력: 콘솔(StreamHandler) + 파일(logs/YYYY_MMDD.log)

사용법:
    # 각 모듈 최상단에 한 줄만 추가
    import logging
    logger = logging.getLogger(__name__)

    # main.py 시작 시 한 번만 호출
    from src.logger import setup_logging
    setup_logging()
"""

from __future__ import annotations
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

# 프로젝트 루트 기준 로그 디렉터리
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _PROJECT_ROOT / "logs"

# 로그 포맷 — 시각 [레벨] 모듈.함수명:줄번호 — 메시지
_FMT = "%(asctime)s [%(levelname)-8s] %(module)s.%(funcName)s:%(lineno)d — %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO,
    log_to_file: bool = True,
) -> None:
    """
    루트 로거를 설정한다. main.py 시작 시 한 번만 호출.

    Args:
        level:       로그 레벨 (기본 INFO, 디버그 시 DEBUG)
        log_to_file: True 이면 logs/YYYY_MMDD.log 에도 기록
    """
    root = logging.getLogger()

    # 이미 핸들러가 등록된 경우 중복 방지
    if root.handlers:
        return

    root.setLevel(level)
    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    # ── 콘솔 핸들러 ─────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # ── 파일 핸들러 ─────────────────────────────────────────────
    if log_to_file:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _LOG_DIR / f"{datetime.now().strftime('%Y_%m%d')}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=7,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.info("로깅 초기화 완료 — level=%s, log_file=%s",
              logging.getLevelName(level),
              _LOG_DIR / f"{datetime.now().strftime('%Y_%m%d')}.log" if log_to_file else "없음")


def get_logger(name: str) -> logging.Logger:
    """
    모듈 전용 로거 반환 편의 함수.
    logging.getLogger(__name__) 와 동일하지만 타입 힌트 보장.
    """
    return logging.getLogger(name)
