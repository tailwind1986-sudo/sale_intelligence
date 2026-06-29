from __future__ import annotations

import json
import os
import re
from pathlib import Path

from openai import OpenAI

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[1]

load_dotenv(APP_DIR / ".env")
load_dotenv()


def _read_secret_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_api_key() -> str:
    value = os.getenv("OPENAI_API_KEY", "")
    if value:
        return value
    for path in (
        APP_DIR / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ):
        data = _read_secret_file(path)
        if data.get("OPENAI_API_KEY"):
            return str(data["OPENAI_API_KEY"])
    return ""


_PROMPT_TEMPLATE = """당신은 TLD/CSO 영업 회의록을 업무 보고서, 실행 관리 문서, 고객 관계 관리 메모, 일정 관리 문서로 재구성하는 전문가입니다.

사용자가 제공하는 회의록 원문을 단순 요약하지 말고, 회의에 참석하지 않은 사람도 상황을 이해하고 바로 후속 조치를 할 수 있도록 정리하세요.

요약 원칙:
- 불필요한 잡담, 말버릇, 반복 표현은 제거합니다.
- 중요한 맥락, 배경, 쟁점, 결정사항은 생략하지 않습니다.
- 너무 짧게 요약하지 말고 업무 문서처럼 재구성합니다.
- 담당자, 일정, 숫자, 금액, 회사명, 제품명, 프로젝트명은 최대한 보존합니다.
- 결정된 내용과 아직 검토 중인 내용을 구분합니다.
- 리스크와 확인 필요사항을 별도로 분리합니다.
- 원문에 없는 내용을 추측하지 않습니다.
- 불명확한 내용은 "확인 필요"라고 표시합니다.
- 모든 텍스트는 한국어로 작성합니다.

full_report 작성 원칙 (가장 중요):
- 회의록에 프로젝트나 주제가 여러 개 있으면 반드시 프로젝트별/주제별로 분리하여 서술합니다.
- 각 프로젝트 내에서 [논의 내용 → 결정사항 → 우려사항/쟁점 → Action] 흐름으로 서술합니다.
- 이해관계자(예: A사, B사, 담당자명)의 입장과 의견을 명시적으로 구분하여 서술합니다.
- 기술적 세부사항(수치, 방식, 조건 등)을 생략 없이 보존합니다.
- 분량 제한 없이 회의 내용을 충분히 담아야 합니다. 중요한 내용이 많으면 길어도 됩니다.
- 마크다운 형식(## 제목, - 항목, **강조**)을 적극 활용합니다.

중요 일정 추출 규칙:
- TLD 관련 회의에서는 일정, 담당자, 후속 조치가 가장 중요합니다.
- 날짜, 마감일, 방문 일정, 설치 일정, 납품 일정, 검토 일정, 보고 일정이 언급되면 반드시 schedule_candidates에 추출합니다.
- 공공조달, 혁신조달, 나라장터, 공고, 접수, 신청, 마감, 설명회, 평가, 발표, 납품, 계약, 제안서 제출과 관련된 날짜는 반드시 schedule_candidates에 추출합니다.
- 날짜가 명확하지 않으면 date는 null로 두고 note에 "확인 필요"를 포함합니다.
- 상대 날짜(다음 주, 다음 달 등)는 원문 기준 날짜를 알 수 없으면 추측하지 말고 null 처리합니다.

영업 기회 신호 추출 규칙:
- 아래 유형 중 해당하는 것만 추출합니다: 대표참석, 견적요청, 예산확보, 데모요청, 계약논의, 추가주문, 긍정반응
- 대표참석: 고객사 대표·임원·최종의사결정자가 직접 참석하거나 언급된 경우
- 견적요청: 가격·견적·제안서 제출을 고객이 먼저 요청한 경우
- 예산확보: 예산이 확보됐거나 투자 승인이 났다는 언급
- 데모요청: 시연·PoC·샘플 테스트를 고객이 요청한 경우
- 계약논의: 계약 조건·납기·계약서 관련 구체적 논의가 시작된 경우
- 추가주문: 기존 거래에서 추가 발주·확대 가능성이 언급된 경우
- 긍정반응: 강한 관심·적극적 진행 의지·빠른 일정 제안 등 명확한 긍정 신호
- strength: HIGH = 명시적·확정적, MED = 가능성·의향, LOW = 암시·간접 언급
- content: 해당 신호를 뒷받침하는 원문 핵심 문장 (짧게 발췌)
- 신호가 없으면 빈 배열 []을 반환합니다.

이슈 태그 추출 규칙:
- 아래 카테고리 중 해당하는 것만 추출합니다: 가격, 납기, 인증, 기술, 경쟁사, 예산, 관계, 기타
- 가격: 단가·비용·견적·할인·예산 부족 관련 이슈
- 납기: 일정 지연·납품 기한·기간 관련 이슈
- 인증: 인증·허가·규격·표준 관련 이슈
- 기술: 기술 문제·품질·성능·사양 관련 이슈
- 경쟁사: 경쟁사 제품·가격 비교·대안 검토 언급
- 예산: 예산 미확보·예산 삭감·투자 보류 관련
- 관계: 담당자 교체·의사결정 지연·내부 이견 관련
- 이슈가 없으면 빈 배열 []을 반환합니다.
- content는 원문에서 해당 이슈를 나타내는 핵심 문장을 짧게 발췌합니다.

회의 분위기 분석 규칙:
- overall은 "긍정적" / "중립" / "부정적" / "혼재" 중 하나로 판단합니다.
- score는 0~100 범위로 표현합니다 (100에 가까울수록 긍정적).
- 긍정 신호: 대표/의사결정자 직접 참석, 견적 요청, 추가 미팅 제안, 예산 확인 완료, 빠른 진행 의지.
- 부정 신호: 가격 거부, 납기 우려, 비교 검토 언급, 결정 미루기, 담당자 교체, 침묵/소극적 반응.
- concern에는 가장 주의해야 할 부정 신호나 리스크를 한 문장으로 서술합니다 (없으면 null).

고객 관계 정보 추출 규칙:
- CSO 영업 관련 회의에서는 고객 성향, 개인 선호, 관계 관리 정보를 별도로 추출합니다.
- 선호 제품/제안 방식, 관심사, 싫어하는 방식, 의사결정 성향, 생일, 기념일, 가족/취미/개인적 대화 소재를 relationship_notes에 정리합니다.
- 민감도는 낮음/중간/높음 중 하나로 표시합니다.
- 건강, 정치, 종교, 재정상태 등 민감 정보는 원문에 명확히 있을 때만 기록하고 sensitivity를 높음으로 표시합니다.

회의록 원문:
{transcript}

아래 JSON 형식으로만 반환하세요. 코드블록을 쓰지 마세요.
반드시 full_report를 가장 먼저 작성하세요. full_report는 절대 비워두지 마세요.

{{
  "full_report": "## 프로젝트명\n### 주제\n- 논의내용\n\n형식으로 프로젝트별 상세 보고서 작성. 마크다운 사용. 분량 제한 없음. 이해관계자 입장 구분, 기술 세부사항, 결정사항, 쟁점, Action 포함.",
  "one_line_summary": "회의의 핵심 방향과 다음 액션을 한 문장으로 정리",
  "detailed_summary": "회의 전체 흐름을 간결하게 요약 (3~5문장, 핵심만)",
  "meeting_overview": {{
    "topic": "회의 주제 또는 확인 필요",
    "attendees": "주요 참석자 또는 확인 필요",
    "purpose": "회의 목적 또는 확인 필요"
  }},
  "topic_discussions": [
    {{
      "project": "프로젝트명 또는 주제 그룹 (예: DALTON 설치, 일본 역사광고 사업)",
      "topic": "세부 주제명",
      "current_status": "현재 상황",
      "discussion": "논의 내용을 충분히 서술. 기술적 세부사항, 수치, 방식, 조건 포함. 이해관계자별 입장이 다르면 '(A사) ..., (B사) ...' 형식으로 구분.",
      "issue": "쟁점 또는 미결 사항",
      "needs_review": "검토 필요사항"
    }}
  ],
  "key_discussions": ["주요 논의사항 요약1", "주요 논의사항 요약2"],
  "decisions": ["확정된 결정사항1"],
  "customer_needs": ["고객 니즈1", "고객 니즈2"],
  "complaints": ["불만 또는 우려사항1"],
  "price_mentions": ["가격 관련 언급1"],
  "competitor_mentions": ["경쟁사 또는 경쟁제품 언급1"],
  "promises": [
    {{"content": "약속 내용", "promised_by": "약속 주체", "due_date": "YYYY-MM-DD 또는 null"}}
  ],
  "follow_ups": ["후속조치1", "후속조치2"],
  "action_items_structured": [
    {{"task": "할 일", "assignee": "담당자 또는 확인 필요", "due_date": "YYYY-MM-DD 또는 null", "note": "비고"}}
  ],
  "pending_items": ["미결 사항1"],
  "risk_factors": ["리스크 요인1"],
  "risks_and_checks": ["리스크 또는 확인 필요사항1"],
  "next_meeting_questions": ["다음 미팅에서 확인할 질문1"],
  "sales_opportunities": ["영업 기회1"],
  "sales_signals": [
    {{"signal_type": "견적요청", "strength": "HIGH", "content": "원문 근거 문장"}}
  ],
  "relationship_notes": [
    {{
      "person_or_company": "인물/회사",
      "category": "선호도/성향/관심사/개인 정보/기타",
      "content": "원문에 나온 내용",
      "use_point": "영업 활용 포인트",
      "sensitivity": "낮음/중간/높음"
    }}
  ],
  "schedule_candidates": [
    {{
      "date": "YYYY-MM-DD 또는 null",
      "end_date": "YYYY-MM-DD 또는 null",
      "title": "일정 제목",
      "project": "관련 프로젝트 또는 확인 필요",
      "assignee": "담당자 또는 확인 필요",
      "location": "장소 또는 확인 필요",
      "note": "비고와 원문 근거",
      "confidence": "높음/중간/낮음"
    }}
  ],
  "issue_tags": [
    {{"tag": "가격", "content": "원문 발췌 또는 근거 문장"}}
  ],
  "meeting_mood": {{
    "overall": "긍정적",
    "score": 70,
    "signals": ["긍정 신호1", "긍정 신호2"],
    "concern": "우려 또는 부정 신호 요약 (없으면 null)"
  }},
  "trust_score": 75,
  "risk_score": 30
}}

점수 기준:
- trust_score: 0-100, 고객 신뢰도/진행 안정성이 높을수록 높은 점수
- risk_score: 0-100, 거래 위험도가 높을수록 높은 점수
- 해당 내용이 없으면 빈 배열 [] 또는 null을 반환하세요.
"""


def _build_history_context(prev_meetings: list) -> str:
    """이전 미팅 요약 목록을 프롬프트용 텍스트로 변환."""
    if not prev_meetings:
        return ""
    lines = ["[이전 미팅 히스토리 (최근 순, 맥락 참고용 — 아래 원문 분석 시 활용하세요)]"]
    for m in prev_meetings:
        date_str = m.meeting_date.strftime("%Y-%m-%d") if m.meeting_date else "날짜미상"
        a = m.analysis
        if not a:
            continue
        parts = [f"• {date_str}"]
        if a.one_line_summary:
            parts.append(a.one_line_summary)
        if a.decisions:
            items = a.decisions if isinstance(a.decisions, list) else []
            if items:
                parts.append("결정: " + " / ".join(str(i) for i in items[:2]))
        if a.follow_ups:
            items = a.follow_ups if isinstance(a.follow_ups, list) else []
            if items:
                parts.append("후속: " + " / ".join(str(i) for i in items[:2]))
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def analyze_meeting_transcript(transcript: str, prev_meetings: list | None = None) -> dict:
    """OpenAI API로 미팅 전사 텍스트를 분석하고 구조화된 결과를 반환한다.
    prev_meetings: 같은 고객사의 이전 MeetingRecord 리스트 (최근순, analysis preloaded)
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. Streamlit Secrets 또는 .env 파일을 확인해주세요.")

    client = OpenAI(api_key=api_key)

    history_context = _build_history_context(prev_meetings or [])
    prompt = _PROMPT_TEMPLATE.format(transcript=transcript)
    if history_context:
        prompt = history_context + "\n\n" + prompt

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "system",
                "content": "당신은 영업 회의록 분석 전문가입니다. 반드시 유효한 JSON 객체만 응답합니다. JSON의 첫 번째 필드인 full_report를 반드시 충분한 내용으로 작성하세요. full_report를 비우거나 생략하지 마세요.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=16000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()

    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if m:
            raw = m.group(1)

    return json.loads(raw)


def generate_monthly_insight(
    company_name: str,
    year_month: str,
    meeting_summaries: list[dict],
    company_history: dict | None = None,
    prev_insights: list[dict] | None = None,
) -> dict:
    """특정 고객사의 월간 인사이트를 GPT-4.1로 생성."""
    meetings_text = "\n\n".join(
        f"[{m.get('date', '')}] {m.get('summary', '')}"
        for m in meeting_summaries
    ) or "해당 월 미팅 없음"

    history_text = ""
    if company_history:
        history_text = (
            f"신뢰지수 평균: {company_history.get('trust_score_avg', '-')}, "
            f"리스크 평균: {company_history.get('risk_score_avg', '-')}, "
            f"미팅수: {company_history.get('meeting_count', 0)}, "
            f"영업단계: {company_history.get('sales_stage', '-')}"
        )

    prev_text = ""
    if prev_insights:
        prev_text = "\n".join(
            f"- {p.get('year_month')}: {p.get('summary', '')}"
            for p in prev_insights[:3]
        )

    system_prompt = """당신은 B2B 영업 전략 분석 전문가입니다.
주어진 고객사 미팅 데이터를 바탕으로 월간 인사이트를 JSON으로 생성하세요.

출력 형식:
{
  "summary": "이 달 전반적인 한 줄 총평 (50자 이내)",
  "key_trends": ["트렌드1", "트렌드2", ...],
  "risks": [{"risk": "리스크 내용", "level": "HIGH|MED|LOW"}],
  "opportunities": [{"action": "기회/액션", "priority": "HIGH|MED|LOW"}],
  "recommended_actions": [{"action": "권장 행동", "deadline": "YYYY-MM 또는 단기/중기"}],
  "relationship_score": 0~100,
  "deal_probability": 0~100
}

규칙:
- key_trends: 2~4개, 이 달 두드러진 변화나 패턴
- risks: 0~3개, 놓치면 안 되는 위험 요소
- opportunities: 1~3개, 즉시 활용 가능한 기회
- recommended_actions: 1~3개, 다음 달 전에 해야 할 것
- relationship_score: 신뢰·친밀도 종합 (미팅 없으면 null)
- deal_probability: 수주 가능성 추정 (명확한 근거 없으면 null)
"""

    user_prompt = f"""고객사: {company_name}
분석 대상 월: {year_month}

【이달 미팅 요약】
{meetings_text}

【이달 영업 히스토리 지표】
{history_text or "없음"}

【이전 월 인사이트 (최근 3개월)】
{prev_text or "없음"}

위 정보를 바탕으로 {year_month} 월간 인사이트를 JSON으로 출력하세요."""

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if m:
            raw = m.group(1)
    return json.loads(raw)


def generate_monthly_report_summary(
    year_month: str,
    stats: dict,
    hot_companies: list,
    stagnant_companies: list,
    risk_companies: list,
    top_issues: list,
) -> dict:
    """전사 월간 리포트 GPT 총평 + 다음달 추천 액션 생성.

    Returns:
        {"overall_summary": str, "next_month_actions": [str, ...]}
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
    client = OpenAI(api_key=api_key)

    hot_text = "\n".join(
        f"- {c['name']}: 딜확률 {c.get('deal_probability', '?')}%, 관계점수 {c.get('relationship_score', '?')}점, {c.get('summary', '')[:80]}"
        for c in hot_companies
    )
    stagnant_text = "\n".join(
        f"- {c['name']} ({c['days_since']}일째 미접촉)" for c in stagnant_companies
    )
    risk_text = "\n".join(
        f"- {c['name']}: {c.get('top_risk', '')}" for c in risk_companies
    )
    issue_text = "\n".join(
        f"- {tag} ({cnt}건)" for tag, cnt in top_issues
    )

    user_prompt = f"""【{year_month} 전사 영업 현황】
총 미팅: {stats.get('total_meetings', 0)}건 / 접촉 고객사: {stats.get('active_companies', 0)}개사

【HOT 고객사】
{hot_text or '없음'}

【정체 고객 (30일 이상 미접촉)】
{stagnant_text or '없음'}

【위험 고객】
{risk_text or '없음'}

【반복 이슈】
{issue_text or '없음'}

위 데이터를 바탕으로 이달 영업 총평(2~3문장)과 다음달 반드시 챙겨야 할 추천 액션 3가지를 JSON으로 출력하세요.

출력 형식:
{{
  "overall_summary": "이달 영업 총평 2~3문장",
  "next_month_actions": [
    "추천 액션 1",
    "추천 액션 2",
    "추천 액션 3"
  ]
}}"""

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "당신은 B2B 영업 전략 전문가입니다. 데이터를 바탕으로 간결하고 실용적인 인사이트를 제공합니다."},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=600,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if m:
            raw = m.group(1)
    result = json.loads(raw)
    return {
        "overall_summary": result.get("overall_summary", ""),
        "next_month_actions": result.get("next_month_actions", []),
    }
