# CI/CD 정책 문서

> **프로젝트**: Stock Prediction Pipeline
> **작성일**: 2026-03-09
> **대상**: 개발 참여자 전원

---

## 목차

1. [소스 관리 전략 (GitHub)](#1-소스-관리-전략-github)
2. [환경 독립성 확보 (Docker)](#2-환경-독립성-확보-docker)
3. [CI 파이프라인 (GitHub Actions)](#3-ci-파이프라인-github-actions)
4. [워크플로우 전체 흐름](#4-워크플로우-전체-흐름)

---

## 1. 소스 관리 전략 (GitHub)

### 목적
여러 명의 개발자가 동시에 작업해도 코드 충돌을 최소화하고, 안정적인 메인 브랜치를 유지한다.

### 브랜치 운영 규칙

```
main
 └── feature/기능명       ← 신규 기능 개발
 └── fix/버그명           ← 버그 수정
 └── chore/작업명         ← 설정, 문서, 인프라 변경
```

| 규칙 | 내용 |
|------|------|
| `main` 직접 push 금지 | 반드시 PR(Pull Request)을 통해 병합 |
| PR 병합 조건 | CI 전체 통과 필수 |
| 커밋 단위 | 기능 단위로 원자적(atomic) 커밋 |
| 커밋 메시지 | `feat:`, `fix:`, `chore:`, `docs:` 접두어 사용 |

### 협업 흐름

```
1. main 브랜치에서 feature 브랜치 생성
2. 로컬 개발 완료 후 push
3. GitHub에서 PR 생성
4. CI 자동 실행 (Lint + Docker Build)
5. CI 통과 + 코드 리뷰 승인 → main 병합
```

---

## 2. 환경 독립성 확보 (Docker)

### 목적
"내 맥에서는 되는데 서버에서 안 된다" 문제를 근본 차단한다.
OS, Python 버전, 패키지 의존성을 컨테이너 안에 완전히 고정한다.

### 구성 파일

| 파일 | 역할 |
|------|------|
| `Dockerfile` | 이미지 빌드 정의 (Python 3.11 slim 기반) |
| `docker-compose.yml` | 로컬 개발 실행 환경 정의 |
| `requirements.txt` | Python 패키지 버전 고정 |

### Dockerfile 핵심 설계

```dockerfile
FROM python:3.11-slim          # Python 버전 고정

# 시스템 의존성 설치 (sentence-transformers, pdfplumber 등)
RUN apt-get install -y gcc g++ build-essential ...

# torch CPU-only 설치 (GPU 불필요 → 이미지 경량화)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# 소스/설정만 복사 (비밀키는 환경변수로 주입)
COPY src/ ./src/
COPY config/ ./config/

# 데이터 볼륨 마운트 (컨테이너 재시작 시 데이터 유지)
VOLUME ["/app/collected_datas", "/app/chroma_db", "/app/logs"]
```

### 로컬 개발 실행

```bash
# 전체 파이프라인 실행
docker compose up

# 단계별 개별 실행
docker compose run --rm stock-pipeline python -m src.main --collect
docker compose run --rm stock-pipeline python -m src.main --orchestrate
```

### 비밀키 관리 원칙

```
로컬 개발  → .env 파일 (git에서 제외, .gitignore 등록)
CI/CD     → GitHub Secrets (암호화된 환경변수)
```

> `.env` 파일은 절대로 git에 커밋하지 않는다.

---

## 3. CI 파이프라인 (GitHub Actions)

### 트리거 조건

```
main 브랜치로 push 또는 PR 생성 시 자동 실행
```

### Job 구성

```
┌─────────────────┐    ┌─────────────────┐
│  Lint (ruff)    │    │ Docker Build    │
│                 │    │ Check           │
│ ruff check src/ │    │ docker build .  │
└────────┬────────┘    └────────┬────────┘
         │                      │
         └──────────┬───────────┘
                    ▼
           ┌────────────────┐
           │  Slack Notify  │
           │  (항상 실행)   │
           │ ✅ CI 통과     │
           │ ❌ CI 실패     │
           └────────────────┘
```

### Job 상세

#### Job 1 — Lint (ruff)

```yaml
- 도구: ruff (Python 코드 품질 검사)
- 검사 범위: src/ 전체
- 검사 항목:
    E402  임포트 순서 위반
    F401  미사용 임포트
    F841  미사용 변수
    F821  미정의 이름 참조
```

| 의의 | 내용 |
|------|------|
| 코드 스타일 통일 | 여러 개발자가 작업해도 동일한 코드 품질 유지 |
| 버그 예방 | 실수로 남긴 미사용 변수·임포트 자동 감지 |
| PR 전 자동 검증 | 리뷰어가 스타일 지적하는 시간 절약 |

#### Job 2 — Docker Build Check

```yaml
- 명령: docker build -t stock-pipeline:ci .
- 목적: Dockerfile 및 requirements.txt 유효성 검증
```

| 의의 | 내용 |
|------|------|
| 이미지 빌드 가능 여부 확인 | 의존성 충돌·Dockerfile 오류 조기 감지 |
| 배포 환경 사전 검증 | 실제 실행 환경(컨테이너)에서 동작 보장 |

#### Job 3 — Slack Notify

```yaml
- 조건: Lint + Docker Build 완료 후 항상 실행
- 내용: 성공/실패 여부, 브랜치명, 작성자, 워크플로우 링크
```

성공 예시:
```
✅ CI 통과
브랜치: main | 작성자: donaldos
[워크플로우 보기]
```

실패 예시:
```
❌ CI 실패
Lint: failure | Docker Build: success
[워크플로우 보기]
```

---

## 4. 워크플로우 전체 흐름

```
개발자 A                GitHub                  맥북 (팀원)
   │                      │                         │
   │  git push (feature)  │                         │
   │─────────────────────>│                         │
   │                      │                         │
   │               CI 자동 실행                      │
   │               ┌──────┴──────┐                  │
   │               │ Lint (ruff) │                  │
   │               │ Docker Build│                  │
   │               └──────┬──────┘                  │
   │                      │                         │
   │               Slack 결과 알림 ─────────────────>│
   │<─────────────────────│                         │
   │                      │                         │
   │  [CI 실패] 코드 수정  │                         │
   │  [CI 통과] PR 생성   │                         │
   │─────────────────────>│                         │
   │                      │  코드 리뷰 요청 ─────────>│
   │                      │<──── 승인 ──────────────│
   │                      │                         │
   │               main 브랜치 병합                   │
   │                      │                         │
```

### 매일 자동 실행 (Daily Pipeline)

```
평일 오전 6시 (KST)  →  Docker 빌드  →  파이프라인 실행  →  결과 Slack 알림
```

> 장 마감(15:30 KST) 이후 데이터를 수집하기 위해 매일 오후 6시 실행

---

## 부록: 개발자 체크리스트

### Push 전 로컬 확인

```bash
# 1. Lint 검사 (CI와 동일한 조건)
pip install ruff
ruff check src/

# 2. Docker 빌드 확인
docker build -t stock-pipeline:test .

# 3. 환경변수 확인 (.env 파일 존재 여부)
cat .env
```

### GitHub Secrets 등록 목록

| Secret 이름 | 용도 |
|-------------|------|
| `DART_API_KEY` | DART 공시 API |
| `OPENAI_API_KEY` | OpenAI LLM |
| `ANTHROPIC_API_KEY` | Claude LLM |
| `UPSTAGE_API_KEY` | Upstage 임베딩 |
| `GOOGLE_API_KEY` | Gemini LLM |
| `PINECONE_API_KEY` | Pinecone 벡터DB |
| `SLACK_WEBHOOK_URL` | CI/CD 결과 알림 |
