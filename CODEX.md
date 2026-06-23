# Sales Intelligence — 프로젝트 CODEX

> 최종 업데이트: 2026-06-24  
> 작성 목적: 프로젝트 현황 공유 및 Oracle Cloud 서버 세팅 기록

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Sales Intelligence |
| 목적 | 영업 미팅 기록 관리, AI 분석, 고객사 관리, 일정 관리 통합 시스템 |
| 언어/프레임워크 | Python 3.x + Streamlit |
| DB | Supabase PostgreSQL (운영) / SQLite (로컬 개발) |
| AI | OpenAI GPT-4o |
| 알림 | Telegram Bot API |
| 배포 | Oracle Cloud VM + Streamlit Cloud (병행) |
| GitHub | https://github.com/tailwind1986-sudo/sale_intelligence |
| Streamlit Cloud URL | https://sales-intelli.streamlit.app |
| Oracle 서버 URL | http://161.33.148.67:8501 |

---

## 2. 구현된 기능 목록

### 2-1. 대시보드 (🏠)
- 최근 미팅 7건 요약 표시
- 주요 KPI 카드 (고객사 수, 미팅 수, 액션아이템 수 등)

### 2-2. 고객사 관리 (🏢)
- 고객사 등록/수정/삭제
- 영업 단계, 중요도, 리스크 레벨 관리
- 담당자(Contact) 관리 (생일, 직책, 연락처 등)
- 고객 취향·중요정보 관리 (생일/취향/가족/주요이슈)
- `st.radio()` + `session_state`로 탭 전환 (수정 버튼 programmatic 전환 지원)

### 2-3. 미팅 기록 업로드 (📤)
- 텍스트 직접 입력 또는 파일 업로드 (.txt, .docx)
- 고객사 연결, 미팅 유형, 날짜, 참석자 입력
- 업로드 후 GPT-4o AI 분석 자동 실행
- 잘못 올린 미팅 삭제 기능

### 2-4. 미팅 요약 결과 (📋)
- GPT-4o 분석 결과 표시:
  - 한줄 요약, 상세 요약
  - 핵심 논의사항, 고객 니즈, 불만사항
  - 가격 언급, 경쟁사 언급
  - 약속사항, 후속조치, 리스크 요인
  - 신뢰도/리스크 점수
  - 다음 미팅 질문 추천, 영업 기회

### 2-5. 고객사별 타임라인 (📅)
- 고객사 선택 → 미팅 이력 타임라인 표시

### 2-6. 액션아이템 관리 (✅)
- 상태별 필터 (예정/진행중/완료/지연)
- 고객사별 필터
- 완료 처리, 삭제

### 2-7. 리스크 분석 (⚠️)
- 고객사별 리스크 점수 시각화
- 위험 고객사 우선 표시

### 2-8. 통합 검색 (🔍)
- 미팅 내용, 고객사명, 담당자 통합 검색

### 2-9. 일정 관리 (🗓️) — TimeTree 스타일
- **3단계 드릴다운 UX:**
  1. 월간 캘린더 뷰 (streamlit-calendar / FullCalendar.js)
  2. 날짜 클릭 → 해당 날짜 일정 목록 (시간순)
  3. 일정 클릭 → 상세 카드 (수정/삭제)
- 년/월 드롭다운 네비게이터
- 종일 이벤트 지원 (FullCalendar exclusive end +1일 처리)
- 드래그 범위 선택으로 기간 일정 추가
- 고객사 연결
- **Telegram 알림 연동:**
  - 알림 ON/OFF, 알림 시간 설정 (10분 전 ~ 1주일 전)
  - 60초마다 자동 체크, 발송 후 중복 방지
  - 텔레그램 설정 탭 (연동 상태 확인, 테스트 메시지 전송)

---

## 3. 기술 스택 및 핵심 구현

### 3-1. 패키지 (requirements.txt)
```
streamlit>=1.35.0
sqlalchemy>=2.0.0
pandas>=2.0.0
python-dotenv>=1.0.0
openai>=1.52.0
openpyxl>=3.1.0
pg8000>=1.30.0
streamlit-calendar>=0.6.0
requests>=2.28.0
```

### 3-2. DB 연결 (database/db.py)
- **SQLite** (로컬): `DATABASE_URL` 환경변수 없을 때 자동 사용
- **Supabase PostgreSQL** (운영): `DATABASE_URL` 환경변수로 연결
- **pg8000** 드라이버 사용 (Python 3.14 호환, pure Python)
- URL 파서: `rfind('@')` 방식 (Python 3.14 urlparse가 `[`,`]` 포함 비밀번호에서 크래시)
- `SA_URL.create()` 로 안전한 SQLAlchemy URL 구성
- `pool_pre_ping=True`, `pool_recycle=300` (Supabase 연결 안정성)
- `@st.cache_resource` 로 DB 세션 캐싱 (성능 최적화)

### 3-3. AI 분석 (OpenAI GPT-4o)
- `response_format={"type": "json_object"}` 로 구조화된 JSON 응답
- `openai>=1.52.0` 필수 (이전 버전 httpx 호환 오류 있음)

### 3-4. Telegram 알림 (services/telegram_service.py)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 환경변수로 설정
- `check_and_send_reminders()`: 미전송 알림 체크 → 발송 → `remind_sent=True` 처리
- `@st.cache_data(ttl=60)` 로 60초마다만 체크 (과도한 API 호출 방지)

### 3-5. DB 모델 (database/models.py)
| 모델 | 설명 |
|------|------|
| Company | 고객사 |
| Contact | 담당자 |
| CustomerInfo | 고객 취향/중요정보 |
| MeetingRecord | 미팅 기록 |
| MeetingAnalysis | AI 분석 결과 |
| Promise | 약속사항 |
| ActionItem | 액션아이템 |
| Schedule | 일정 (Telegram 알림 포함) |

### 3-6. 주요 버그 수정 이력
| 버그 | 원인 | 해결 |
|------|------|------|
| DB 연결 오류 `host '3]@aws-...'` | 비밀번호에 `[MY-PASSWORD]` 리터럴 포함 | Supabase 비밀번호 재설정 |
| Python 3.14 urlparse ValueError | `[`, `]` 를 IPv6으로 파싱 | `rfind('@')` 수동 파서 |
| OpenAI proxies 오류 | openai 1.35.0 + 신버전 httpx 충돌 | `openai>=1.52.0` 업그레이드 |
| 미팅 삭제 InvalidRequestError | 세션 detach된 객체 삭제 시도 | `db.get(MeetingRecord, id)` 재조회 후 삭제 |
| 고객사 수정 버튼 무반응 | `st.tabs()` programmatic 전환 불가 | `st.radio()` + `session_state` 전환 방식으로 교체 |
| 캘린더 종일 이벤트 날짜 오류 | FullCalendar end exclusive 처리 | `end_dt + timedelta(days=1)` |

---

## 4. Oracle Cloud 서버 세팅

### 4-1. 서버 사양
| 항목 | 내용 |
|------|------|
| 클라우드 | Oracle Cloud Free Tier |
| 리전 | Japan East (Tokyo) — ap-tokyo-1 |
| 인스턴스명 | instance-20260623-2301 |
| Shape | VM.Standard.E5.Flex |
| OCPU | 1 |
| Memory | 12GB |
| OS | Canonical Ubuntu 22.04 LTS |
| Public IP | 161.33.148.67 |
| Username | ubuntu |
| SSH 키 | ssh-key-2026-06-23.key |

> **참고:** VM.Standard.A1.Flex (ARM) 은 도쿄 AD-1 용량 부족으로 생성 실패. E5.Flex로 대체.

### 4-2. 서버 접속 방법 (Windows)
```powershell
# SSH 키 권한 설정 (최초 1회)
icacls "D:\Project\Server Setup_oracle\ssh-key-2026-06-23.key" /inheritance:r /grant:r "${env:USERNAME}:(R)"
icacls "D:\Project\Server Setup_oracle\ssh-key-2026-06-23.key" /remove "NT AUTHORITY\Authenticated Users"
icacls "D:\Project\Server Setup_oracle\ssh-key-2026-06-23.key" /remove "BUILTIN\Users"

# SSH 접속
ssh -i "D:\Project\Server Setup_oracle\ssh-key-2026-06-23.key" ubuntu@161.33.148.67
```

### 4-3. 서버 초기 세팅 순서
```bash
# 1. 패키지 업데이트
sudo apt update && sudo apt upgrade -y

# 2. Python, git 설치
sudo apt install -y python3-pip python3-venv git

# 3. 앱 클론
git clone https://github.com/tailwind1986-sudo/sale_intelligence.git ~/app

# 4. 가상환경 생성 및 패키지 설치
cd ~/app && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# 5. Streamlit secrets 설정
mkdir -p ~/.streamlit && nano ~/.streamlit/secrets.toml
```

### 4-4. secrets.toml 내용
```toml
DATABASE_URL = "postgresql://postgres.zdwbsxipthnkluqfooxh:PASSWORD@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres"
OPENAI_API_KEY = "sk-proj-..."
TELEGRAM_BOT_TOKEN = "8732241207:..."
TELEGRAM_CHAT_ID = "7274204338"
```

### 4-5. 앱 실행
```bash
# 백그라운드 실행 (터미널 꺼도 유지)
cd ~/app && source venv/bin/activate
nohup streamlit run app.py --server.port 8501 > ~/streamlit.log 2>&1 &
```

### 4-6. 재부팅 자동시작 설정
```bash
# 시작 스크립트 생성
cat > ~/.streamlit_start.sh << 'EOF'
#!/bin/bash
cd ~/app
source venv/bin/activate
nohup streamlit run app.py --server.port 8501 > ~/streamlit.log 2>&1 &
EOF
chmod +x ~/.streamlit_start.sh

# crontab 등록
(crontab -l 2>/dev/null; echo "@reboot ~/.streamlit_start.sh") | crontab -

# 확인
crontab -l
```

### 4-7. Oracle Cloud 방화벽 설정
- Oracle Cloud 콘솔 → Networking → VCN → Subnet → Security Lists
- **Default Security List** → Add Ingress Rule:
  - Source CIDR: `0.0.0.0/0`
  - Protocol: TCP
  - Destination Port: `8501`
- 서버 내부 iptables:
```bash
sudo iptables -I INPUT -p tcp --dport 8501 -j ACCEPT
```

### 4-8. 앱 업데이트 방법
```bash
ssh -i "D:\Project\Server Setup_oracle\ssh-key-2026-06-23.key" ubuntu@161.33.148.67
cd ~/app && git pull
# 앱 재시작
pkill -f streamlit
nohup streamlit run app.py --server.port 8501 > ~/streamlit.log 2>&1 &
```

---

## 5. 환경변수 목록

| 변수명 | 설명 | 설정 위치 |
|--------|------|-----------|
| `DATABASE_URL` | Supabase PostgreSQL 연결 URL | Streamlit Cloud Secrets / `~/.streamlit/secrets.toml` |
| `OPENAI_API_KEY` | OpenAI API 키 | 동일 |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 | 동일 |
| `TELEGRAM_CHAT_ID` | 텔레그램 Chat ID | 동일 |

---

## 6. 파일 구조

```
Sales_Intelligence/
├── app.py                          # 메인 앱 (전체 페이지 포함)
├── requirements.txt
├── database/
│   ├── db.py                       # DB 엔진, 세션, URL 파서
│   └── models.py                   # SQLAlchemy ORM 모델 8개
├── services/
│   └── telegram_service.py         # Telegram 알림 서비스
└── data/
    └── sales_intelligence.db       # SQLite (로컬 개발용)
```

---

## 7. 향후 계획 / 미완료 항목

| 항목 | 상태 | 비고 |
|------|------|------|
| Oracle 서버 재부팅 자동시작 검증 | 미확인 | `sudo reboot` 후 확인 필요 |
| 다른 앱 Oracle 서버 배포 | 예정 | 포트 분리 필요 (8502, 8503 등) |
| 모바일 위젯 | 검토 완료 | Telegram Bot 명령어 확장이 현실적 |
| ARM 인스턴스 (A1.Flex) | 보류 | 도쿄 용량 부족, 새벽에 재시도 가능 |

---

## 8. 다른 앱 추가 배포 시 참고사항

같은 Oracle 서버에 추가 앱 배포 시:
1. 포트 번호 다르게 설정 (예: `--server.port 8502`)
2. Oracle Security List에 해당 포트 Ingress Rule 추가
3. `sudo iptables -I INPUT -p tcp --dport 8502 -j ACCEPT`
4. 별도 가상환경 생성 권장 (`~/app2/venv`)
5. 별도 `secrets.toml` 또는 환경변수 파일 관리
6. crontab에 자동시작 스크립트 추가
