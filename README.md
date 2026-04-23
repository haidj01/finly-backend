# Finly Backend

AI 기반 주식 투자 어시스턴트 **Finly**의 백엔드 서버입니다.  
FastAPI로 구축되었으며, Claude AI와 Alpaca 증권 API를 연동합니다.

---

## 기술 스택

- **Python 3.11+**
- **FastAPI** — REST API 프레임워크
- **Uvicorn** — ASGI 서버
- **httpx** — 비동기 HTTP 클라이언트
- **Claude API** (Anthropic) — AI 채팅, 매매 신호 분석, 티커 검색
- **Alpaca Markets API** — 계좌 조회, 포지션, 주문 실행

---

## 프로젝트 구조

```
finly-backend/
├── main.py               # FastAPI 앱 진입점, CORS 설정
├── requirements.txt      # Python 의존성
├── .env.example          # 환경 변수 예시
└── routes/
    ├── __init__.py
    ├── claude.py         # /api/claude    — AI 채팅, 매매 신호, 티커 검색
    ├── alpaca.py         # /api/alpaca    — 계좌, 포지션, 가격, 주문
    ├── news.py           # /api/news      — 뉴스 수집 및 감성 분석
    └── trending.py       # /api/trending  — 시장 급등락 종목
```

---

## 시작하기

### 1. 의존성 설치

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env.example`을 복사하여 `.env`를 생성하고 값을 입력합니다.

```bash
cp .env.example .env
```

| 변수명 | 설명 |
|---|---|
| `CLAUDE_API_KEY` | Anthropic API 키 (`sk-ant-...`) |
| `ALPACA_API_KEY` | Alpaca Paper Trading API Key ID |
| `ALPACA_API_SECRET` | Alpaca Paper Trading API Secret |
| `FRONTEND_ORIGIN` | 허용할 프론트엔드 Origin (기본값: `http://localhost:3000`) |

### 3. 서버 실행

```bash
uvicorn main:app --reload
```

서버가 `http://localhost:8000`에서 실행됩니다.

---

## API 엔드포인트

### Health Check

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | 서버 상태 확인 |

---

### Claude AI (`/api/claude`)

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/claude/chat` | AI 채팅 (웹 검색 도구 포함) |
| POST | `/api/claude/signals` | 종목 매매 신호 분석 (웹 검색 기반, 최대 10개) |
| POST | `/api/claude/search-ticker` | 검색어로 미국 상장 주식 티커 조회 (최대 5개) |

**`POST /api/claude/chat` 요청 예시:**
```json
{
  "system": "당신은 투자 전문 어시스턴트입니다.",
  "messages": [
    { "role": "user", "content": "애플 주가 전망을 알려줘." }
  ]
}
```

**`POST /api/claude/signals` 요청 예시:**
```json
{
  "symbols": ["AAPL", "TSLA", "NVDA"]
}
```

응답 예시:
```json
[
  { "type": "buy", "sym": "NVDA", "reason": "AI 수요 급증으로 실적 호조", "conf": "신뢰도 82%" }
]
```

**`POST /api/claude/search-ticker` 요청 예시:**
```json
{
  "query": "전기차"
}
```

---

### Alpaca Markets (`/api/alpaca`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/alpaca/account` | 계좌 정보 조회 |
| GET | `/api/alpaca/positions` | 보유 포지션 목록 |
| GET | `/api/alpaca/prices?symbols=AAPL,TSLA` | 종목별 최신 체결가 조회 |
| GET | `/api/alpaca/asset/{sym}` | 개별 종목 정보 조회 |
| GET | `/api/alpaca/orders?status=all&limit=20` | 주문 내역 조회 |
| POST | `/api/alpaca/orders` | 시장가 주문 실행 |

**`POST /api/alpaca/orders` 요청 예시:**
```json
{
  "symbol": "AAPL",
  "qty": 1,
  "side": "buy"
}
```

> **주의:** 현재 Alpaca Paper Trading 환경을 사용합니다. 실제 자금이 사용되지 않습니다.

---

### 뉴스 (`/api/news`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/news?symbols=AAPL,TSLA&limit=10` | 종목별 뉴스 수집 및 감성 분석 |

Alpaca 뉴스와 Google News RSS를 동시에 조회하며, Claude가 헤드라인을 한국어로 번역하고 `bull` / `bear` / `neu` 감성을 분류합니다.

응답 예시:
```json
{
  "alpaca": {
    "ok": true,
    "error": null,
    "items": [
      {
        "sym": "AAPL",
        "hl": "Apple reports record Q2 earnings",
        "hl_ko": "애플, 역대 최고 2분기 실적 발표",
        "url": "https://...",
        "time": "2025-05-15T10:00:00+00:00",
        "sent": "bull",
        "source": "Reuters"
      }
    ]
  },
  "google": { "ok": true, "error": null, "items": [] }
}
```

---

### 트렌딩 종목 (`/api/trending`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/trending` | 시장 급등락 및 거래량 상위 종목 조회 |

Alpaca 스크리너에서 거래량 상위 8개(`actives`), 상승 상위 5개(`gainers`), 하락 상위 5개(`losers`)를 조회하고 Claude 웹 검색으로 각 종목의 주목 이유를 분석합니다.

응답 예시:
```json
{
  "actives": [
    { "sym": "NVDA", "price": 950.10, "change": 25.30, "chg_pct": 2.73, "volume": 45000000, "category": "most_active", "reason": "AI 칩 수요 폭증" }
  ],
  "gainers": [],
  "losers": []
}
```

---

## AWS 배포 (EC2 단일 인스턴스)

### 사전 준비

#### 1. AWS EC2 Key Pair 생성

AWS 콘솔에서 EC2 접속용 Key Pair를 생성합니다.

1. [AWS 콘솔 → EC2 → Network & Security → Key Pairs](https://console.aws.amazon.com/ec2/#KeyPairs) 접속
2. **Create key pair** 클릭
3. 설정:
   - **Name**: `finly-key`
   - **Key pair type**: RSA
   - **Private key file format**: `.pem` (Mac/Linux)
4. **Create key pair** 클릭 → `finly-key.pem` 자동 다운로드
5. PEM 파일 권한 설정:
   ```bash
   mv ~/Downloads/finly-key.pem ~/.ssh/finly-key.pem
   chmod 400 ~/.ssh/finly-key.pem
   ```

#### 2. 환경변수 설정

```bash
export KEY_FILE=~/.ssh/finly-key.pem    # PEM 파일 경로
export EC2_KEY_NAME=finly-key            # AWS Key Pair 이름
export CLAUDE_API_KEY=sk-ant-...
export ALPACA_API_KEY=...
export ALPACA_API_SECRET=...
```

### 전체 배포 (최초 1회)

```bash
cd /path/to/workspace   # finly, finly-backend, finly-agent가 있는 상위 디렉터리
./finly_deploy.sh --ec2-all
```

순서대로 실행됩니다:
1. **bootstrap** — Terraform 상태 저장용 S3 버킷 + DynamoDB 생성
2. **ec2 infra** — EC2 인스턴스, Elastic IP, ECR, SSM 시크릿 생성
3. **ec2 apps** — Docker 이미지 빌드 → ECR push → SSH → `docker-compose up`
4. **frontend** — `npm build` → S3 업로드 → CloudFront 캐시 무효화

### 코드 변경 후 재배포

```bash
# 앱 + 프론트엔드 동시 재배포
./finly_deploy.sh --ec2-redeploy

# 앱만 재배포
./finly_deploy.sh --ec2-apps

# 프론트엔드만 재배포
./finly_deploy.sh --frontend
```

### Terraform 구조

```
finly-backend/terraform/
├── ec2/          ← EC2 단일 인스턴스 (현재 사용)
│   ├── main.tf   EC2, Elastic IP, ECR, Security Group
│   ├── iam.tf    Instance Profile (SSM + ECR 권한)
│   ├── ssm.tf    SSM Parameter Store (API 키 저장)
│   └── userdata.sh  Docker + nginx + 앱 자동 설치
└── (ECS 버전)    향후 확장 시 사용
```

---

## 개발 참고사항

- 자동 API 문서: `http://localhost:8000/docs` (Swagger UI)
- CORS는 `FRONTEND_ORIGIN` 환경 변수로 제어되며, `GET`/`POST` 메서드만 허용합니다.
- Claude 모델: `claude-sonnet-4-20250514`
