from __future__ import annotations

import json
import os
import re

import streamlit as st
from openai import OpenAI


def _get_api_key() -> str:
    try:
        key = st.secrets.get("OPENAI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY", "")


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

중요 일정 추출 규칙:
- TLD 관련 회의에서는 일정, 담당자, 후속 조치가 가장 중요합니다.
- 날짜, 마감일, 방문 일정, 설치 일정, 납품 일정, 검토 일정, 보고 일정이 언급되면 반드시 schedule_candidates에 추출합니다.
- 공공조달, 혁신조달, 나라장터, 공고, 접수, 신청, 마감, 설명회, 평가, 발표, 납품, 계약, 제안서 제출과 관련된 날짜는 반드시 schedule_candidates에 추출합니다.
- 날짜가 명확하지 않으면 date는 null로 두고 note에 "확인 필요"를 포함합니다.
- 상대 날짜(다음 주, 다음 달 등)는 원문 기준 날짜를 알 수 없으면 추측하지 말고 null 처리합니다.

고객 관계 정보 추출 규칙:
- CSO 영업 관련 회의에서는 고객 성향, 개인 선호, 관계 관리 정보를 별도로 추출합니다.
- 선호 제품/제안 방식, 관심사, 싫어하는 방식, 의사결정 성향, 생일, 기념일, 가족/취미/개인적 대화 소재를 relationship_notes에 정리합니다.
- 민감도는 낮음/중간/높음 중 하나로 표시합니다.
- 건강, 정치, 종교, 재정상태 등 민감 정보는 원문에 명확히 있을 때만 기록하고 sensitivity를 높음으로 표시합니다.

회의록 원문:
{transcript}

아래 JSON 형식으로만 반환하세요. 코드블록을 쓰지 마세요.
{{
  "one_line_summary": "회의의 핵심 방향과 다음 액션을 한 문장으로 정리",
  "detailed_summary": "회의 전체 흐름을 5~8문장 정도로 정리",
  "meeting_overview": {{
    "topic": "회의 주제 또는 확인 필요",
    "attendees": "주요 참석자 또는 확인 필요",
    "purpose": "회의 목적 또는 확인 필요"
  }},
  "topic_discussions": [
    {{
      "topic": "주제명",
      "current_status": "현재 상황",
      "discussion": "논의 내용",
      "issue": "쟁점",
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
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "당신은 영업 회의록 분석 전문가입니다. 반드시 유효한 JSON 객체만 응답합니다.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=6000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()

    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if m:
            raw = m.group(1)

    return json.loads(raw)
