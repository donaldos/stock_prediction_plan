"""
Slack 리포트 발송 모듈.

orchestration_result.json 의 report 딕셔너리를 Block Kit 메시지로 변환 후
Incoming Webhook 으로 전송한다.

사용:
    from src.pipeline.notification.slack import send_report
    send_report(report_dict, webhook_url)
"""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 예측 결과 → 이모지/레이블 매핑
_PREDICTION_EMOJI = {
    "상승": "📈",
    "하락": "📉",
    "보합": "➡️",
}

# 신뢰도 구간 → 색상 (Block Kit attachment 사이드바용)
def _confidence_color(score: int) -> str:
    if score >= 8:
        return "#2ecc71"   # 초록
    if score >= 6:
        return "#f1c40f"   # 노랑
    return "#e74c3c"       # 빨강


def format_report(report: dict[str, Any]) -> dict:
    """
    report 딕셔너리 → Slack Block Kit payload 변환.

    Args:
        report: orchestration_result.json 의 "report" 키 값

    Returns:
        Slack API 에 전달할 JSON 딕셔너리
    """
    ticker         = report.get("ticker", "N/A")
    date           = report.get("date", "N/A")
    prediction     = report.get("prediction", "N/A")
    confidence     = report.get("confidence_score", 0)
    scenario       = report.get("scenario_type", "일반")
    bull_case      = report.get("bull_case", "")
    bear_case      = report.get("bear_case", "")
    key_refs       = report.get("key_references", [])
    evidence_count = report.get("evidence_count", 0)
    low_confidence = report.get("low_confidence", False)
    retry_count    = report.get("retry_count", 0)

    pred_emoji = _PREDICTION_EMOJI.get(prediction, "❓")
    conf_bar   = "●" * confidence + "○" * (10 - confidence)

    blocks: list[dict] = []

    # ── 저신뢰도 경고 배너 ─────────────────────────────────────
    if low_confidence:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *신뢰도 낮음* — {retry_count}회 재시도 후 강제 생성된 결과입니다. 참고용으로만 사용하세요.",
            },
        })
        blocks.append({"type": "divider"})

    # ── 헤더 ─────────────────────────────────────────────────
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"📊 [{ticker}] 주가 예측 리포트 · {date}",
            "emoji": True,
        },
    })

    # ── 핵심 요약 (예측 / 신뢰도 / 시나리오) ────────────────────
    blocks.append({
        "type": "section",
        "fields": [
            {
                "type": "mrkdwn",
                "text": f"*예측*\n{pred_emoji} {prediction}",
            },
            {
                "type": "mrkdwn",
                "text": f"*신뢰도*\n`{conf_bar}` {confidence}/10",
            },
            {
                "type": "mrkdwn",
                "text": f"*시나리오*\n{scenario}",
            },
            {
                "type": "mrkdwn",
                "text": f"*근거 수*\n{evidence_count}건",
            },
        ],
    })

    blocks.append({"type": "divider"})

    # ── 강세 근거 ─────────────────────────────────────────────
    if bull_case:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🟢 *강세 근거*\n{bull_case}",
            },
        })

    # ── 약세 리스크 ───────────────────────────────────────────
    if bear_case:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔴 *약세 리스크*\n{bear_case}",
            },
        })

    # ── 참고 자료 ─────────────────────────────────────────────
    if key_refs:
        refs_text = "\n".join(f"• {ref}" for ref in key_refs)
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📎 *참고 자료* ({len(key_refs)}건)\n{refs_text}",
            },
        })

    # ── 컨텍스트 (생성 메타) ──────────────────────────────────
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"종목코드: `{ticker}` | 예측일: {date} | 재시도: {retry_count}회",
            }
        ],
    })

    return {
        "attachments": [
            {
                "color":  _confidence_color(confidence),
                "blocks": blocks,
            }
        ]
    }


def send_report(
    report: dict[str, Any],
    webhook_url: str,
) -> None:
    """
    Slack Incoming Webhook 으로 리포트 전송.

    Args:
        report:      orchestration_result.json 의 "report" 딕셔너리
        webhook_url: Slack Incoming Webhook URL

    Raises:
        RuntimeError: 전송 실패 (HTTP 오류 또는 네트워크 오류)
    """
    payload = format_report(report)
    body    = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url=webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    logger.info(
        "[Slack] 리포트 전송 시작 — ticker=%s  prediction=%s  confidence=%d",
        report.get("ticker"), report.get("prediction"), report.get("confidence_score", 0),
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            if resp_body != "ok":
                raise RuntimeError(f"Slack Webhook 응답 이상: {resp_body!r}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Slack Webhook HTTP 오류: {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Slack Webhook 네트워크 오류: {exc.reason}") from exc

    logger.info("[Slack] 전송 완료")


def send_from_result_file(result_path: Path, webhook_url: str) -> None:
    """
    orchestration_result.json 파일 경로를 받아 Slack 전송.

    Args:
        result_path: orchestration_result.json 경로
        webhook_url: Slack Incoming Webhook URL
    """
    with open(result_path, encoding="utf-8") as f:
        data = json.load(f)

    report = data.get("report")
    if not report:
        raise ValueError(f"'report' 키가 없습니다: {result_path}")

    send_report(report, webhook_url)
