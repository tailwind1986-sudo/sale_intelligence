# Sales Intelligence Worklog

> 서버 반영 전 로컬 작업 기록.  
> 원칙: 1~7번 기능이 모두 로컬에서 완료되기 전까지 서버 push/pull 배포는 하지 않는다.

---

## 2026-06-24

### Streamlit 제거 1단계. FastAPI 빠른 대시보드

- 상태: 완료
- 변경 파일: `mobile_api.py`, `mobile_calendar/app.js`, `workspace_app/index.html`, `workspace_app/styles.css`, `workspace_app/app.js`
- 구현 내용:
  - `/mobile/workspace` 경로에 Streamlit이 아닌 정적 HTML/JS 기반 빠른 대시보드 추가
  - `/mobile/api/dashboard` API 추가
  - 오늘 일정, 7일 내 일정, 마감 액션, 확인할 약속, 최근 미팅을 JSON으로 제공
  - 기존 모바일 로그인 토큰(`sales_mobile_token`)을 그대로 사용
  - 모바일 캘린더 `더보기` 탭에 `빠른 대시보드` 이동 버튼 추가
- 보존 사항:
  - 기존 Streamlit 대시보드와 모바일 캘린더 기능 유지
  - 기존 DB 스키마 변경 없음
- 검증:
  - `python -m py_compile mobile_api.py` 통과
  - `node --check mobile_calendar\app.js` 통과
  - `node --check workspace_app\app.js` 통과
  - 로컬 기본 Python 환경에는 FastAPI 패키지가 없어 TestClient 검증은 생략
- 서버 반영:
  - 아직 하지 않음

### Streamlit 제거 2단계. 액션아이템/약속사항 관리

- 상태: 완료
- 변경 파일: `mobile_api.py`, `workspace_app/index.html`, `workspace_app/app.js`, `workspace_app/styles.css`
- 구현 내용:
  - `/mobile/api/actions` 액션아이템 목록/추가/수정/삭제 API 추가
  - `/mobile/api/promises` 약속사항 목록/추가/수정/삭제 API 추가
  - 상태, 고객사, 담당자 필터를 API에 반영
  - workspace에 `액션/약속` 탭 추가
  - 액션아이템 상태 변경, 수정, 삭제, 신규 추가 화면 구현
  - 약속사항 상태 변경, 수정, 삭제, 신규 추가 화면 구현
  - 기한 초과 항목을 시각적으로 강조
- 빠진 기능 검증:
  - 기존 Streamlit 액션아이템 탭의 상태 필터, 고객사 필터, 담당자 검색, 상태 변경, 기한/내용 수정, 삭제, 수동 추가 흐름 대응
  - 기존 Streamlit 약속사항 탭의 상태 필터, 고객사 필터, 상태 변경, 삭제, 수동 추가 흐름 대응
- 보존 사항:
  - 기존 Streamlit 액션아이템 관리 화면 유지
  - 기존 DB 스키마 변경 없음
- 검증:
  - `python -m py_compile mobile_api.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
  - `node --check workspace_app\app.js` 통과
- 서버 반영:
  - 아직 하지 않음

### Streamlit 제거 3단계. 고객사 관리

- 상태: 완료
- 변경 파일: `mobile_api.py`, `workspace_app/index.html`, `workspace_app/app.js`, `workspace_app/styles.css`
- 구현 내용:
  - `/mobile/api/workspace/companies` 고객사 목록/검색/필터 API 추가
  - 고객사 상세, 등록, 수정, 삭제 API 추가
  - 담당자 등록, 수정, 삭제 API 추가
  - 고객 취향/중요정보 등록, 수정, 삭제 API 추가
  - workspace에 `고객사` 탭 추가
  - 고객사 목록/상세 2단 구조, 최근 미팅, 담당자, 고객 정보 표시
- 빠진 기능 검증:
  - 기존 Streamlit 고객사 목록의 고객사명/담당자 검색, 사업구분/영업단계/리스크 필터 대응
  - 기존 고객사 등록/수정 주요 필드 대응
  - 기존 담당자 관리의 추가/삭제 및 주요 필드 대응, 수정 기능은 신규 추가
  - 기존 고객 취향·중요정보 추가/삭제 및 주요 필드 대응, 수정 기능은 신규 추가
- 보존 사항:
  - 기존 Streamlit 고객사 관리 화면 유지
  - 기존 DB 스키마 변경 없음
- 검증:
  - `python -m py_compile mobile_api.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
  - `node --check workspace_app\app.js` 통과
- 서버 반영:
  - 아직 하지 않음

### Streamlit 제거 4단계. AI 일정 후보 승인함

- 상태: 완료
- 변경 파일: `mobile_api.py`, `workspace_app/index.html`, `workspace_app/app.js`, `workspace_app/styles.css`
- 구현 내용:
  - `/mobile/api/schedule-candidates` 후보 목록 API 추가
  - 후보 상태 필터 `대기/저장됨/무시됨/전체` 제공
  - 후보별 제목, 시작일, 종료일, 프로젝트, 담당자, 장소, 비고 수정 후 일정표 저장
  - 저장 시 기존 `Schedule` 테이블에 등록되어 캘린더와 텔레그램 알림 대상에 포함
  - 후보 무시 처리 API 추가
  - workspace에 `일정 후보` 탭 추가
- 빠진 기능 검증:
  - 기존 Streamlit AI 일정 후보 승인함의 대기 후보 조회, 저장, 무시 흐름 대응
  - 기존 미팅 요약 결과 화면의 일정 후보 저장 원칙과 동일하게 자동 등록이 아닌 사용자 승인 후 저장
- 보존 사항:
  - 기존 Streamlit AI 일정 후보 승인함 유지
  - 기존 DB 스키마 변경 없음
- 검증:
  - `python -m py_compile mobile_api.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
  - `node --check workspace_app\app.js` 통과
- 서버 반영:
  - 아직 하지 않음

### 1. 오늘/이번 주 실행 대시보드

- 상태: 완료
- 변경 파일: `app.py`
- 구현 내용:
  - 기존 대시보드 상단에 `오늘/이번 주 실행 보드` 섹션 추가
  - 오늘 일정, 7일 내 일정, 마감/지연 액션, 미확인 약속 KPI 표시
  - 오늘 일정과 이번 주 일정을 별도 목록으로 표시
  - 7일 내 마감 또는 이미 지연된 액션아이템 표시
  - 미완료/미확인 약속사항 표시
  - 최근 회의록 분석의 `risks_and_checks`, `pending_items` 기반 AI 확인 필요사항 표시
- 보존 사항:
  - 기존 KPI 카드, 최근 미팅, 기한 임박 액션아이템, 업체별 진행현황 요약은 삭제하지 않고 유지
- 검증:
  - `python -m py_compile app.py` 통과
- 서버 반영:
  - 아직 하지 않음

### 긴급 수정. AI 일정 후보 페이지 SyntaxError

- 상태: 완료
- 변경 파일: `app.py`
- 원인:
  - AI 일정 후보 페이지의 f-string 표현식 내부에 유니코드 이스케이프 문자열이 포함되어 서버 Python에서 `f-string expression part cannot include a backslash` 오류 발생
- 수정 내용:
  - `candidate.get("confidence") or "확인 필요"` 값을 f-string 밖의 `confidence` 변수로 분리
- 검증:
  - `python -m py_compile app.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
- 서버 반영:
  - 아직 하지 않음

### 7. 검색 강화

- 상태: 완료
- 변경 파일: `app.py`
- 구현 내용:
  - 통합 검색에서 고객사명/메모 외 산업, 주소, 웹사이트까지 검색
  - 담당자명/직책 외 전화, 이메일, 메모까지 검색
  - 미팅 원문 외 참석자, 메모, 파일명까지 검색
  - 약속사항의 내용, 약속 주체, 메모, 상태 검색
  - 액션아이템의 내용, 담당자, 메모, 상태 검색
  - 일정 제목/설명 검색 및 `일정` 결과 섹션 추가
- 보존 사항:
  - 기존 고객사, 담당자, 미팅 원문, AI 분석 결과, 약속사항, 액션아이템 검색 결과 섹션 유지
- 검증:
  - `python -m py_compile app.py` 통과
- 서버 반영:
  - 아직 하지 않음

### 6. 모바일 빠른 입력

- 상태: 완료
- 변경 파일: `mobile_calendar/index.html`, `mobile_calendar/app.js`, `mobile_calendar/styles.css`
- 구현 내용:
  - 모바일 캘린더 하단 일자 시트에 빠른 일정 입력 폼 추가
  - 제목만 입력하면 선택 날짜의 종일 일정으로 등록
  - `오후 3시 고객 미팅`, `15:00 고객 미팅`처럼 시작 시간을 앞에 쓰면 1시간 일정으로 등록
  - 현재 고객사 필터가 선택되어 있으면 해당 고객사 일정으로 저장
  - 빠른 입력 일정은 기본 텔레그램 알림 ON, 시간 일정은 1시간 전, 종일 일정은 1일 전으로 설정
  - 모바일 정적 파일 캐시 버전 `tt10`으로 갱신
- 보존 사항:
  - 기존 `+` 버튼 상세 일정 등록/수정 흐름 유지
  - 기존 모바일 API 변경 없음
- 검증:
  - `python -m py_compile mobile_api.py` 통과
  - `node --check mobile_calendar\app.js` 통과
- 서버 반영:
  - 아직 하지 않음

### 5. 회의록 재분석 옵션 분리

- 상태: 완료
- 변경 파일: `app.py`
- 구현 내용:
  - 미팅 요약 결과 화면에 `AI 재분석 옵션` expander 추가
  - `전체 재분석`: 기존 등록 액션아이템/약속/일정은 보존하고 `MeetingAnalysis` 분석 결과만 갱신
  - `일정 후보만 재추출`: `schedule_candidates`만 갱신
  - 일정 후보 재추출 시 기존 후보의 `saved`, `ignored` 상태를 날짜+제목 기준으로 최대한 유지
- 보존 사항:
  - 신규 회의록 업로드 시 기존 `_save_analysis()` 경로 유지
  - 사용자가 이미 등록/수정한 액션아이템, 약속사항, 일정 데이터는 재분석으로 삭제하지 않음
- 검증:
  - `python -m py_compile app.py services\ai_analyzer.py` 통과
- 서버 반영:
  - 아직 하지 않음

### 4. 텔레그램 아침 브리핑

- 상태: 완료
- 변경 파일: `services/telegram_service.py`
- 구현 내용:
  - 기존 오늘 일정 요약을 `아침 브리핑` 형태로 확장
  - 오늘 일정, 7일 내 마감 액션아이템, 7일 내 확인할 약속사항을 함께 전송
  - 일정이 없어도 액션/약속이 있으면 브리핑 전송
  - 텔레그램 HTML 메시지 깨짐 방지를 위해 고객사명/제목/내용 escape 처리
- 보존 사항:
  - 기존 `reminder_worker.py digest` 실행 경로와 `sales-digest.timer` 구조 유지
  - 개별 일정 알림 `check_and_send_reminders()` 로직은 변경하지 않음
- 검증:
  - `python -m py_compile services\telegram_service.py reminder_worker.py` 통과
  - `send_daily_digest` import 확인
- 서버 반영:
  - 아직 하지 않음

### 3. 고객사별 현재 상황 자동 요약

- 상태: 완료
- 변경 파일: `app.py`
- 구현 내용:
  - 회의록 분석, 미완료 액션아이템, 미완료 약속사항을 합쳐 업체별 현재상황 스냅샷 생성
  - 대시보드의 업체별 진행현황을 `최근회의`, `현재상황`, `다음액션`, `확인/리스크` 컬럼으로 분리
  - 업체별 상세 진행 메모 expander 추가
  - 고객사별 타임라인 상단에 선택 업체의 현재상황 요약 표시
- 보존 사항:
  - 기존 고객사/미팅/액션/약속 데이터 구조 변경 없음
  - 기존 `company_progress_summary()`는 유지
- 검증:
  - `python -m py_compile app.py` 통과
- 서버 반영:
  - 아직 하지 않음

### 2. AI 일정 후보 승인함

- 상태: 완료
- 변경 파일: `app.py`
- 구현 내용:
  - 회의록 분석 결과의 `schedule_candidates`를 한 곳에서 검토하는 `AI 일정 후보` 페이지 추가
  - 후보별 제목, 시작일, 종료일, 관련 프로젝트, 담당자, 장소, 비고를 수정한 뒤 `일정표에 저장` 가능
  - 저장 시 기존 `Schedule` 테이블에 등록되어 캘린더와 알림 대상에 포함
  - `무시` 처리 시 해당 후보를 다시 검토 목록에 띄우지 않도록 `ignored` 플래그 저장
  - 저장 완료 후보는 `saved` 플래그와 기존 일정 중복 검사로 대기 목록에서 제외
- 보존 사항:
  - 미팅 요약 결과 화면의 기존 일정 탭과 저장 기능 유지
  - AI가 추출한 일정은 자동등록하지 않고 사용자가 확인 후 저장하는 흐름 유지
- 검증:
  - `python -m py_compile app.py` 통과
- 서버 반영:
  - 아직 하지 않음
### Streamlit 제거 5단계. 미팅 요약 결과 조회

- 상태: 완료
- 변경 파일: `mobile_api.py`, `workspace_app/index.html`, `workspace_app/app.js`
- 구현 내용:
  - `/mobile/api/meetings` 미팅 요약 목록 API 추가
  - `/mobile/api/meetings/{meeting_id}` 미팅 요약 상세 API 추가
  - workspace에 `미팅요약` 탭 추가
  - 회의 개요, 전체 요약, 핵심 논의, 결정사항, 후속 조치, 리스크, 카톡/문자 보고, 고객 관계 정보, 원문 확인 영역 추가
  - 고객 관계 정보 저장 API 추가
  - 미팅 기록 삭제 API 추가
- 빠진 기능 검증:
  - 기존 Streamlit 미팅 요약 결과의 결과 조회, 카톡/문자 보고 복사, 고객 관계 정보 저장, 원문 확인, 삭제 흐름 대응
  - AI 실행/재분석/업로드는 6단계에서 별도 이관
- 보존 사항:
  - 기존 Streamlit 미팅 요약 결과 화면 유지
  - 기존 DB 스키마 변경 없음
- 검증:
  - `python -m py_compile mobile_api.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
  - `node --check workspace_app\app.js` 통과
- 서버 반영:
  - 아직 하지 않음

### Streamlit 제거 6단계. 미팅 업로드 / AI 분석

- 상태: 완료
- 변경 파일: `mobile_api.py`, `services/ai_analyzer.py`, `workspace_app/index.html`, `workspace_app/app.js`, `workspace_app/styles.css`, `requirements.txt`
- 구현 내용:
  - `/mobile/api/meetings/upload` API 추가
  - TXT 파일 업로드 또는 직접 입력으로 `MeetingRecord` 저장
  - 저장 후 선택적으로 OpenAI 회의록 분석 실행
  - 신규 분석 결과를 `MeetingAnalysis`, `Promise`, `ActionItem`에 기존 구조대로 저장
  - `/mobile/api/meetings/{meeting_id}/analyze` 재분석 API 추가
  - 전체 재분석과 일정 후보만 재추출 모드 지원
  - workspace에 `미팅 업로드` 탭과 업로드/분석 폼 추가
  - 미팅 요약 상세 화면에 `AI 분석`, `전체 재분석`, `일정 재추출` 버튼 추가
  - `services.ai_analyzer`의 직접 Streamlit import 제거
  - 파일 업로드 Form 처리를 위해 `python-multipart` 의존성 추가
- 빠진 기능 검증:
  - 기존 Streamlit 업로드의 고객사, 미팅일자, 유형, 참석자, 메모, 원문 저장, AI 자동 분석 흐름 대응
  - 기존 재분석의 전체 재분석 / 일정 후보 재추출 흐름 대응
  - 재분석 시 사용자가 이미 수정했을 수 있는 액션/약속은 자동 삭제하거나 재생성하지 않음
- 보존 사항:
  - 기존 Streamlit 업로드/요약 화면 유지
  - 기존 DB 스키마 변경 없음
  - `.env`와 `.streamlit/secrets.toml` 기반 OpenAI 키 로딩 유지
- 검증:
  - `python -m py_compile mobile_api.py services\ai_analyzer.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
  - `node --check workspace_app\app.js` 통과
  - 로컬 기본 Python에는 FastAPI가 없어 `import mobile_api` 런타임 검증은 8단계 후 의존성 설치/로컬 실행 때 확인 예정
- 서버 반영:
  - 아직 하지 않음

### Streamlit 제거 7단계. 통합 검색

- 상태: 완료
- 변경 파일: `mobile_api.py`, `workspace_app/index.html`, `workspace_app/app.js`, `workspace_app/styles.css`, `WORKLOG.md`
- 구현 내용:
  - `/mobile/api/search` 통합 검색 API 추가
  - 고객사, 담당자, 미팅 원문, AI 요약, 약속사항, 액션아이템, 일정 검색 지원
  - workspace에 `통합 검색` 탭 추가
  - 검색어 입력 시 자동 검색 및 검색 버튼 제출 지원
  - 미팅 검색 결과 클릭 시 미팅 요약 상세로 이동
  - 고객사/담당자 검색 결과 클릭 시 고객사 상세로 이동
- 빠진 기능 검증:
  - 기존 Streamlit 통합 검색의 주요 검색 범위 대응
  - 미팅 AI 분석 결과는 한 줄 요약과 상세 요약 검색 대응
  - JSON 상세 필드 전체 전문 검색은 DB 호환성을 위해 제외하고, 화면에 표시되는 핵심 텍스트 검색 중심으로 구성
- 보존 사항:
  - 기존 Streamlit 통합 검색 화면 유지
  - 기존 DB 스키마 변경 없음
- 검증:
  - `python -m py_compile mobile_api.py services\ai_analyzer.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
  - `node --check workspace_app\app.js` 통과
- 서버 반영:
  - 아직 하지 않음

### Streamlit 제거 8단계. 리스크 분석 / 설정 / 텔레그램

- 상태: 완료
- 변경 파일: `mobile_api.py`, `workspace_app/index.html`, `workspace_app/app.js`, `workspace_app/styles.css`, `WORKLOG.md`
- 구현 내용:
  - `/mobile/api/risk` 리스크 스코어보드 API 추가
  - 고객사별 약속 불이행, 약속 지연, 지연 액션, AI 평균 위험/신뢰, 종합 리스크 점수 계산
  - 고객사별 누적 리스크 요인, 불만/우려사항, 경쟁사 언급, 불이행 약속, 위험/신뢰 추이 조회
  - `/mobile/api/risk/{company_id}` 리스크 등급 저장 API 추가
  - `/mobile/api/telegram/status` 텔레그램 설정 상태 API 추가
  - `/mobile/api/telegram/test`, `/check-reminders`, `/daily-digest`, `/weekly-summary` 버튼형 실행 API 추가
  - workspace에 `리스크/설정` 탭 추가
  - 리스크 카드형 점수표, 상세 리스크, 등급 저장 UI 추가
  - 텔레그램 테스트/알림 체크/오늘 브리핑/주간 요약 발송 UI 추가
- 빠진 기능 검증:
  - 기존 Streamlit 리스크 분석의 점수표, 고객사 상세 리스크, 등급 저장 흐름 대응
  - 기존 텔레그램 설정의 연동 상태, 테스트 메시지, 알림 체크, 주간 요약 수동 발송 흐름 대응
  - 오늘 브리핑 수동 발송은 기존 `send_daily_digest` 서비스 재사용
- 보존 사항:
  - 기존 Streamlit 리스크 분석과 일정관리 텔레그램 설정 화면 유지
  - 기존 Telegram 서비스 로직과 reminder worker 유지
  - 기존 DB 스키마 변경 없음
- 검증:
  - `python -m py_compile mobile_api.py services\ai_analyzer.py services\telegram_service.py reminder_worker.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
  - `node --check workspace_app\app.js` 통과
- 서버 반영:
  - 아직 하지 않음

### 로컬 FastAPI 실행 호환성 보강

- 상태: 완료
- 변경 파일: `mobile_api.py`, `WORKLOG.md`
- 구현 내용:
  - 로컬 직접 실행에서도 서버와 같은 `/mobile/` URL로 접속할 수 있도록 alias 라우트 추가
  - `/mobile/static`, `/mobile/workspace/static`, `/mobile/workspace`, `/mobile/sw.js` 경로 추가
- 보존 사항:
  - 기존 `/`, `/workspace`, `/static`, `/workspace/static` 경로 유지
- 검증:
  - `python -m py_compile mobile_api.py` 통과
  - `ast.parse(..., feature_version=(3,10))` 통과
- 서버 반영:
  - 아직 하지 않음
