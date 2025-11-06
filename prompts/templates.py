"""
프롬프트 템플릿 유틸리티

역할
- SYSTEM 프롬프트(rulebook.md) 로딩/캐시
- 일자별 채점 루브릭/입력 가이드/예시 제공
- user_payload_judge: 모델에 전달할 사용자 페이로드 문자열을 구성

확장 가이드
- 루브릭/가이드는 README 변경 시 본 파일을 업데이트하여 정합성 유지
- 필요 시 logs 요약을 추가로 포함해 컨텍스트 강화 가능(현 버전은 경량 유지)
"""

from functools import lru_cache
from pathlib import Path

# 한국어 설명
# - 이 모듈은 일차별 루브릭(RUBRIC_BY_DAY), 입력 가이드(GUIDELINE_BY_DAY), 예시(EXAMPLE_BY_DAY)를 제공하고
#   룰북(rulebook.md) SYSTEM 텍스트를 읽어오는 헬퍼(system_prompt)를 포함합니다.
# - UI(app.py, pages/*)와 엔진(engine*.py)이 동일한 기준/가이드를 공유하도록 하는 연결 고리입니다.


# --- Day-specific rubrics and input helpers -------------------------------

# 일자별 채점 루브릭(README Criterion 반영)
RUBRIC_BY_DAY = {
    1: (
        "[Day 1 Rubric]\n"
        "- Creativity (0..5): 차별화된 AI/LLM 아이디어·가치 제안.\n"
        "- Feasibility (0..5): 구현 난이도, 개인정보/LLM moderation 리스크 대응.\n"
        "- delta = creativity + feasibility (cap +10); score = prev + delta."
    ),
    2: (
        "[Day 2 Rubric]\n"
        "- Root Cause Thinking: 오류 원인 파악.\n"
        "- Risk & Safety: 롤백/비상복구/알림/고객·내부 커뮤니케이션.\n"
        "- Actionability: 오류 원인에 대한 적절한 조치.\n"
        "- Poor answers: -5..-20; solid answers: small positive (up to +5) or 0."
    ),
    3: (
        "[Day 3 Rubric]\n"
        "- Plan Fit (-10..0): 현재 목표/피드백 반영의 적합성."
    ),
    4: (
        "[Day 4 Rubric]\n"
        "- Measurement: 모델 성능 징후 명시.\n"
        "- Plan/Action: 징후에 대한 적절한 해결 방안 명시.\n"
        "- Poor answers: -5..-20; otherwise small positive or 0."
    ),
    5: (
        "[Day 5 Rubric]\n"
        "- Action Quality (-10..+0): 현재 목표/피드백 반영의 적합성."
    ),
    6: (
        "[Day 6 Rubric]\n"
        "- Clarity: 개요/목적/핵심지표/성과를 간결·일관되게.\n"
        "- Market Fit: 타겟층 정합.\n"
        "- Outcome Framing: 로드맵·리스크 계획.\n"
        "- Weak/불명확 시 감점, 명확/현실적이면 소폭 가점 또는 0."
    ),
}


# 일자별 사용자 입력 가이드(한 문단 구성 요소)
GUIDELINE_BY_DAY = {
    1: (
        "AI를 활용한 스타트업의 아이디어를 제시해주세요.\n"
        "제품 개요와 차별점(창의성), 타깃 고객/문제, 구현 접근(기술/알고리즘), "
        "리스크(개인정보/LLM moderation) 대응을 자연스럽게 포함하세요."
    ),
    2: (
        "현재 발생한 오류에 대한 해결방법을 제시해주세요.\n"
        "원인 1~2개와 근거, 해결 방법을 포함하세요."
    ),
    3: (
        "현재 제공된 사용자의 피드백에 대한 적절한 조치를 취하세요.\n"
        "현재 목표와의 적합성 및 해당 피드백의 유용성을 판단하여 조치하세요."
    ),
    4: (
        "모델 성능과 관련한 이슈에 대해 적절한 조치를 취하세요.\n"
        "핵심 지표와 주어진 성능 이슈에 대한 적절한 방법을 선택하세요."
    ),
    5: (
        "베타 테스트의 후기에 대한 적절한 조치를 취하세요.\n"
        "현재 목표와의 적합성 및 해당 피드백의 유용성을 판단하여 조치하세요."
    ),
    6: (
        "투자자에게 프로젝트를 어필하세요\n"
        "개요/목적/핵심지표/성과, 시장 적합성, 로드맵/리스크 계획을 포함하세요."
    ),
}


# 일자별 사용자 입력 예시(한 문단)
EXAMPLE_BY_DAY = {
    1: (
        "감정 기반 도서 추천 서비스로, 하루 기분을 분석해 개인에게 맞춘 책을 제안합니다. "
        "기존 서비스 대비 ‘설명 가능한 추천(근거 문구 노출)’을 차별점으로 삼고, 20~30대 직장인을 주요 타깃으로 합니다. "
        "LLM moderation은 금칙어 사전 필터·후검수 룰을 조합해 운영 리스크를 줄이겠습니다."
    ),
    2: (
        "비용 급등 원인은 과도한 컨텍스트 길이와 캐시 미스 증가로 추정됩니다(로그에서 평균 prompt 토큰 2배 증가, 캐시 히트율 20%p 하락). "
        "단기적으로 프롬프트 템플릿 압축과 라우팅(경량 모델 우선) 실험을 진행하고, 중기에는 사용량 경계값을 기반으로 오토스케일·사전 승인 흐름을 도입합니다. "
    ),
    3: (
        "이번 스프린트 목표(설명 가능한 추천, 빠른 첫 가치 경험)와 정합하므로 온보딩 문구/툴팁 정리와 추천 근거 하이라이트를 즉시 적용하겠습니다."
    ),
    4: (
        "모델에 과적합 징후가 포착되었기 때문에 L2-normalization 등의 정규화 기법을 사용하겠습니다."
        "모델의 일반화를 위해 Bottle-neck 기법 중 하나인 1x1 CNN을 사용하겠습니다."
    ),
    5: (
        "해당 피드백에 대해 UI 카피/툴팁/하이라이트 개선과 저장 토글을 이번 스프린트에 적용하겠습니다."
    ),
    6: (
        "우리는 ‘설명 가능한 감정 기반 추천’을 제공하며, 타겟은 20~30대 독서 습관을 가진 직장인입니다. "
        "근거 문구 노출로 신뢰가 향상되었고, 다음 분기에는 경량 모델 라우팅과 온보딩 최적화에 집중합니다. "
        "개인정보는 익명화/권한분리로 관리하며, 리스크는 캐시/알람/롤백 체계를 통해 통제합니다."
    ),
}


@lru_cache(maxsize=1)
def system_prompt() -> str:
    """SYSTEM 룰북(rulebook.md) 로딩(캐시)

    - 성능을 위해 프로세스 생애주기 동안 1회 캐싱
    - 파일 변경 시 프로세스 재시작으로 반영
    """
    path = Path(__file__).parent / "rulebook.md"
    return path.read_text(encoding="utf-8")


def user_payload_event(day: int) -> str:
    """(선택) 모델에 이벤트 카드를 생성 요청할 때 사용할 짧은 프롬프트

    - 현재 버전은 engine.get_event_card()가 결정론적으로 이벤트를 생성하므로 미사용
    - 풍부한 이벤트가 필요하면 본 함수를 호출하도록 확장 가능
    """
    return (
        f"오늘은 {day}일차입니다. 간결한 이벤트 카드(JSON 아님)를 한 문단으로 제시해 주세요. "
        f"주제: 스타트업 운영과 관련된 과제 또는 기회."
    )


def user_payload_judge(day: int, user_text: str, prev_score: int) -> str:
    """채점 요청용 사용자 페이로드 문자열 구성

    - 사용자 한 문단 응답, 이전 점수 포함
    - day별 루브릭 첨부(모델이 정확한 기준으로 채점하도록 유도)
    - 출력 스키마를 명시(룰북의 JSON-only 규칙 재강조)
    """
    rubric = RUBRIC_BY_DAY.get(day, "")
    return (
        "당신은 7일 간의 스타트업 시뮬레이션 심판입니다.\n"
        f"오늘은 {day}일차이며, 이전 점수는 {prev_score}점입니다.\n"
        "아래 사용자의 한 단락 응답을 평가하세요.\n"
        f"심사 루브릭:\n{rubric}\n\n"
        "출력 형식: 반드시 하나의 JSON 객체만을 ```json 코드펜스 내에 출력.\n"
        "키(일 1~6): day, delta, score, reason, llm_summary.\n"
        "키(일 7): day=7, final_score, final_grade, risk_report[], next_recommendations[].\n\n"
        f"[사용자 응답]:\n{user_text}\n"
    )


def input_guidelines(day: int) -> str:
    """UI 표시용: 일자별 한 문단 입력 형식 요약을 반환"""
    return GUIDELINE_BY_DAY.get(day, "하루를 요약하는 한 문단으로 작성하세요.")


def input_example(day: int) -> str:
    """UI 표시용: 일자별 한 문단 입력 예시를 반환"""
    return EXAMPLE_BY_DAY.get(day, "")
