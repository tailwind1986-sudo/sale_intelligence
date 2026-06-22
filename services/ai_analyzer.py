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


_PROMPT_TEMPLATE = """당신은 영업 미팅 분석 전문가입니다. 아래 미팅 전사 텍스트를 분석하여 JSON 형식으로 결과를 반환해주세요.

미팅 전사 텍스트:
{transcript}

다음 JSON 형식으로 정확히 반환해주세요 (코드블록 없이 순수 JSON만):
{{
  "one_line_summary": "미팅을 한 줄로 요약",
  "detailed_summary": "상세 요약 (3-5문장, 핵심 흐름 포함)",
  "key_discussions": ["주요 논의사항1", "주요 논의사항2"],
  "customer_needs": ["고객 니즈1", "고객 니즈2"],
  "complaints": ["불만 또는 우려사항1"],
  "price_mentions": ["가격 관련 언급1"],
  "competitor_mentions": ["경쟁사 또는 경쟁제품 언급1"],
  "promises": [
    {{"content": "약속 내용", "promised_by": "약속한 주체", "due_date": "YYYY-MM-DD 또는 null"}}
  ],
  "follow_ups": ["후속조치1", "후속조치2"],
  "pending_items": ["미결 사항1"],
  "risk_factors": ["리스크 요인1"],
  "next_meeting_questions": ["다음 미팅에서 확인할 질문1"],
  "sales_opportunities": ["영업 기회1"],
  "trust_score": 75,
  "risk_score": 30
}}

주의사항:
- trust_score: 0-100 (고객 신뢰도·긍정도, 높을수록 좋음)
- risk_score: 0-100 (거래 위험도, 높을수록 위험)
- 해당 내용이 없으면 빈 배열 [] 반환
- promises의 due_date가 명시되지 않으면 null 설정
- 모든 텍스트는 한국어로 작성"""


def analyze_meeting_transcript(transcript: str) -> dict:
    """OpenAI API로 미팅 전사 텍스트를 분석하고 구조화된 결과를 반환한다."""
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. Streamlit Secrets 또는 .env 파일을 확인해주세요.")

    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 영업 미팅 분석 전문가입니다. 요청한 JSON 형식으로만 응답합니다."},
            {"role": "user", "content": _PROMPT_TEMPLATE.format(transcript=transcript)},
        ],
        temperature=0.3,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()

    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if m:
            raw = m.group(1)

    return json.loads(raw)
