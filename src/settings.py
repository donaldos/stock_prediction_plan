"""
환경 변수 로더.
프로젝트 루트의 .env 파일을 읽어 API 키 등을 제공한다.
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트의 .env 로드
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def get_dart_api_key() -> str:
    key = os.getenv("DART_API_KEY", "")
    if not key:
        raise EnvironmentError("DART_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def get_upstage_api_key() -> str:
    key = os.getenv("UPSTAGE_API_KEY", "")
    if not key:
        raise EnvironmentError("UPSTAGE_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def get_openai_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise EnvironmentError("OPENAI_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def get_anthropic_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def get_google_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY", "")
    if not key:
        raise EnvironmentError("GOOGLE_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def get_pinecone_api_key() -> str:
    key = os.getenv("PINECONE_API_KEY", "")
    if not key:
        raise EnvironmentError("PINECONE_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return key


def get_slack_webhook_url() -> str:
    url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not url:
        raise EnvironmentError("SLACK_WEBHOOK_URL 이 설정되지 않았습니다. .env 파일을 확인하세요.")
    return url
