# CLAUDE Handoff Notes

> 작성일: 2026-06-24  
> 목적: Claude Code가 작업한 뒤 Codex가 이어받아 수정/배포한 변경사항과, 다시 Claude가 이어받을 때 주의해야 할 내용을 기록한다.

---

## 1. 현재 기준

- 현재 브랜치: `main`
- 현재 로컬 HEAD: `662b343`
- 현재 작업트리: 문서 작성 직전 기준 clean
- 주요 런타임 DB: SQLite
  - 로컬/서버 공통 구조는 `database/db.py`의 `data/sales_intelligence.db`
  - Oracle 서버 DB 경로는 `/home/ubuntu/app/data/sales_intelligence.db`
- Supabase/PostgreSQL 연결은 현재 사용하지 않는 방향으로 정리되어 있음

---

## 2. Claude 최신 변경 사항

최근 Claude Code가 추가/수정한 커밋:

- `9c0dc3f` 회의 이력 컨텍스트 주입, 주간 요약 개선, 수동 트리거 추가
- `feaaaf7` 회의록 결과 페이지에 주간 요약 버튼 추가
- `9f1dea2` 주간 요약 포맷 개선
- `76d56a8` 회의록 결과를 3개 탭 구조로 리팩터링
- `662b343` 위 3개 탭 리팩터링을 revert

주의:
- `76d56a8`의 3탭 구조는 `662b343`에서 되돌려졌으므로, 같은 구조를 다시 적용하기 전에는 사용자 확인이 필요하다.
- 주간 요약 관련 변경은 `services/telegram_service.py`, `reminder_worker.py`, 회의록 결과 페이지 주변과 연동되어 있으므로 수정 시 중복 버튼/중복 요약 로직을 조심한다.

---

## 3. Codex가 반영한 주요 변경 사항

### 3-1. 로그인 유지 개선

관련 커밋:

- `137a237` 브라우저 세션 간 Streamlit 로그인 유지
- `4356e61` 자동 로그인 중 화면이 흐려지는 문제 수정

내용:

- `extra-streamlit-components` 쿠키와 localStorage 토큰을 이용해 로그인 지속성을 개선했다.
- 모바일/Safari에서 자동 로그인 중 `body.style.opacity = 0.35`가 남아 화면 전체가 회색으로 보이는 문제가 있어 해당 opacity 처리를 제거했다.

주의:

- 로그인 유지 로직은 `require_login()`, `_mobile_auth_token()`, `_local_storage_autologin_script()` 주변에 있다.
- 자동 로그인 관련 JS를 수정할 때 화면 전체 opacity, overlay, pointer-events를 건드리지 않는 것이 좋다.

### 3-2. 회의록 요약 분석 스키마 확장

관련 커밋:

- `11880aa` 회의록 분석 보고서 확장

내용:

- OpenAI 프롬프트를 단순 요약에서 업무 보고서/실행 관리/고객 관계/일정 관리 문서 역할로 확장했다.
- 새 분석 필드:
  - `meeting_overview`
  - `topic_discussions`
  - `decisions`
  - `action_items_structured`
  - `risks_and_checks`
  - `relationship_notes`
  - `schedule_candidates`
- `database/models.py`의 `MeetingAnalysis`에 위 JSON 컬럼들을 추가했다.
- 기존 SQLite DB에도 누락 컬럼을 자동 추가하도록 `database/db.py`에 `_ensure_meeting_analysis_columns()`를 추가했다.

주의:

- 기존 분석 결과에는 새 필드가 비어 있을 수 있다. 새 일정 후보/고객 관계 정보가 필요하면 AI 분석 재실행이 필요하다.
- SQLite는 `Base.metadata.create_all()`만으로 기존 테이블에 컬럼을 추가하지 못하므로, 새 컬럼 추가 시 마이그레이션 보강이 필요하다.

### 3-3. 회의록 결과 UI 확장

관련 커밋:

- `11880aa` 회의록 분석 보고서 확장

내용:

- 회의록 결과 화면에 새 렌더러 `_render_enhanced_meeting_result()`를 추가했다.
- 탭 구성:
  - `보고서`
  - `후속조치`
  - `일정`
  - `고객관계`
  - `카톡보고`
  - `원문`
- AI가 추출한 일정 후보는 자동 저장하지 않고 사용자가 확인 후 저장한다.
- 일정 후보에서 `일정표에 저장`을 누르면 `Schedule`에 저장되고 알림 대상이 된다.
- 고객 관계 정보는 `고객 정보로 저장` 버튼으로 `CustomerInfo`에 저장한다.

주의:

- 사용자가 명확히 원한 방향은 "AI가 자동으로 캘린더에 넣는 것"이 아니라 "AI가 후보를 뽑고 사용자가 확인 후 일정표에 저장"이다.
- 일정 저장 함수는 `_add_schedule_candidate()`이며 기본값은 종일 일정, 알림 1일 전이다.

### 3-4. 카톡/문자 보고용 요약 개선

관련 커밋:

- `a9beaac` 카톡 보고용 요약 단순화
- `1d5a22e` 카톡 보고에 일정 흐름 반영

내용:

- 초기에는 `업체 / 일자 / 주요논의`만 남기도록 단순화했다.
- 이후 사용자의 피드백에 따라 혁신조달 같은 일정 흐름이 빠지지 않도록 다시 확장했다.
- 현재 카톡 보고 방향:

```text
[미팅보고] 업체명 / 일자

주요논의
- 주제: 핵심 내용; 일정 A → 일정 B → 일정 C 일정 검토

확인필요
- 일정/공고/등록/리스크 확인 항목
```

참고:

- 관련 함수는 `compact_meeting_report()`, `_build_kakao_discussions()`, `_build_kakao_checks()`.
- `schedule_candidates`, `pending_items`, `risks_and_checks`, `risk_factors`, `decisions`를 함께 참고한다.

### 3-5. 액션아이템/약속사항 버튼 명확화

관련 커밋:

- `e67e8ab` 삭제/일정 저장 버튼 명확화

내용:

- 액션아이템/약속사항 목록의 `🗑️` 단독 버튼을 `삭제` 텍스트 버튼으로 변경했다.
- 바로 삭제되지 않고 `삭제 확인` / `취소` 2단계로 처리한다.
- 회의록 일정 후보의 `캘린더에 추가` 버튼을 `일정표에 저장`으로 변경했다.
- 저장 성공 토스트도 "일정표에 저장했습니다. 알림 대상에 포함됩니다."로 변경했다.

### 3-6. 모바일 캘린더 하단 탭 활성화

관련 커밋:

- `c47caab` 모바일 캘린더 하단 탭 작동 수정

내용:

- 기존 모바일 캘린더 하단 `캘린더 / 목록 / 알림 / 더보기` 버튼은 HTML에만 있고 disabled 상태였으며 JS 이벤트가 없었다.
- 버튼 활성화 및 탭 전환 로직을 추가했다.
- 각 탭 역할:
  - `캘린더`: 선택일 일정/미팅
  - `목록`: 해당 월 전체 일정/미팅
  - `알림`: 알림이 켜진 일정
  - `더보기`: 새로고침, 오늘로 이동, 로그아웃
- 정적 파일 캐시 버전:
  - CSS/JS query: `tt9`
  - service worker cache: `sales-mobile-v11`

주의:

- 모바일 홈화면 앱은 service worker 캐시가 강하게 남을 수 있으므로, 정적 파일 변경 시 `index.html`, `sw.js`, service worker register URL의 버전을 함께 올려야 한다.

### 3-7. Streamlit 설정 보정

관련 커밋:

- `9acf851` Streamlit config section 보정

내용:

- 서버의 `.streamlit/config.toml`에 `[server]` 섹션이 중복되어 TOML 파싱 오류가 로그에 남았다.
- `maxMessageSize = 200`을 기존 `[server]` 섹션 아래로 합쳐 레포에 반영했다.

---

## 4. 서버 반영 이력

Codex가 수행한 서버 반영:

- 여러 차례 `git push origin main`
- Oracle 서버 `/home/ubuntu/app`에서 `git pull origin main`
- `sales-intelligence` 재시작
- 모바일 정적 파일 변경 시 `sales-mobile` 재시작

최근 Codex 서버 반영 기준:

- `c47caab`까지 서버 pull/restart 완료
- 이후 Claude가 `662b343`까지 추가 작업한 상태로 보이며, 해당 최신 HEAD가 서버에 반영되었는지는 별도 확인 필요

서버 확인 명령:

```bash
cd /home/ubuntu/app
git rev-parse --short HEAD
git status --short
sudo systemctl is-active sales-intelligence sales-mobile
```

주의:

- 서버 작업트리에 `deploy/oracle/backup.sh` 로컬 수정이 남아 있었던 적이 있다. 원인 불명 변경이므로 함부로 되돌리지 말 것.
- 서버 반영 요청이 명확하지 않으면 로컬 커밋까지만 진행하는 것이 비용/안정성 측면에서 낫다.

---

## 5. 다음 작업 시 주의할 점

- 회의록 결과 페이지는 최근 Claude가 3탭 구조를 적용했다가 revert했다. 같은 UI 리팩터링 재시도 전 사용자 의도를 확인할 것.
- 모바일 캘린더는 별도 FastAPI/static 앱(`mobile_api.py`, `mobile_calendar/*`)과 Streamlit 내 캘린더가 공존한다.
- 사용자는 모바일 사용 비중이 높으므로 모바일 화면/하단 탭/캐시 갱신을 우선 확인할 것.
- 일정 후보는 자동 등록이 아니라 사용자가 확인 후 `일정표에 저장`해야 한다.
- 알림은 `Schedule.remind_enabled`, `remind_minutes`, `remind_sent`에 의존한다.
- 기존 분석 결과에는 새 AI 필드가 없을 수 있으므로, 기능 테스트 시 새 회의록 분석 또는 AI 재분석이 필요하다.
- 한글이 깨져 보이는 파일이 일부 있다. 실제 UTF-8 내용과 PowerShell 콘솔 표시가 다를 수 있으므로, 한글 문자열 교체 시 `python` 또는 editor 기준으로 확인할 것.
