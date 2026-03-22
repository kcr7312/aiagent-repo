"""
1주차 과제: 고객 문의 티켓 12건을 LLM으로 구조화 추출
- Anthropic Claude API (SDK) 사용
- Prompt v1 / v2 비교 실험
"""

import json
import os
import time
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator
from anthropic import Anthropic

load_dotenv()

# ── 설정 ──────────────────────────────────────────────
MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 0.0
MAX_TOKENS = 256
DATASET_PATH = "dataset.jsonl"

client = Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용

# ── Pydantic 스키마 ───────────────────────────────────
VALID_INTENTS = {"order_change", "shipping_issue", "payment_issue", "refund_exchange", "other"}
VALID_URGENCY = {"low", "medium", "high"}
VALID_ROUTES = {"order_ops", "shipping_ops", "billing_ops", "returns_ops", "human_support"}


class TicketClassification(BaseModel):
    intent: str
    urgency: str
    needs_clarification: bool
    route_to: str

    @field_validator("intent")
    @classmethod
    def check_intent(cls, v):
        if v not in VALID_INTENTS:
            raise ValueError(f"intent must be one of {VALID_INTENTS}")
        return v

    @field_validator("urgency")
    @classmethod
    def check_urgency(cls, v):
        if v not in VALID_URGENCY:
            raise ValueError(f"urgency must be one of {VALID_URGENCY}")
        return v

    @field_validator("route_to")
    @classmethod
    def check_route(cls, v):
        if v not in VALID_ROUTES:
            raise ValueError(f"route_to must be one of {VALID_ROUTES}")
        return v


# ── 프롬프트 v1: 기본 ────────────────────────────────
SYSTEM_V1 = """You are a customer support ticket classifier.
Given a customer message, classify it into the following JSON schema:

{
  "intent": "order_change | shipping_issue | payment_issue | refund_exchange | other",
  "urgency": "low | medium | high",
  "needs_clarification": true or false,
  "route_to": "order_ops | shipping_ops | billing_ops | returns_ops | human_support"
}

Respond with ONLY the JSON object, no other text."""

# ── 프롬프트 v2: 상세 가이드라인 + 예시 ──────────────
SYSTEM_V2 = """You are an expert customer support ticket classifier for a Korean e-commerce platform.

Your task: classify each customer inquiry into a structured JSON output.

## Field Definitions

### intent (고객 의도)
- "order_change": 주문 수정, 취소, 주소 변경, 옵션 변경
- "shipping_issue": 출고/배송 지연, 배송 누락, 배송 완료 오표시
- "payment_issue": 결제 실패, 중복 결제, 청구 이상
- "refund_exchange": 반품, 환불, 교환, 불량 접수
- "other": 위 카테고리로 단정하기 어렵거나 맥락이 부족한 경우

### urgency (긴급도)
- "low": 일반 문의, 즉시 장애 아님
- "medium": 처리가 필요하지만 긴급 장애/금전 리스크 아님
- "high": 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인 시급

### needs_clarification (추가 확인 필요 여부)
- true: 현재 텍스트만으로 intent 또는 처리 방향을 단정하기 어려움
- false: 현재 정보만으로 1차 분류 가능

### route_to (라우팅 부서)
- "order_ops": 주문/수정 담당
- "shipping_ops": 배송 담당
- "billing_ops": 결제/청구 담당
- "returns_ops": 환불/교환 담당
- "human_support": 맥락 부족, 다부서 이슈, 에스컬레이션 필요

## Classification Rules
1. If the customer message is vague or references a previous unspecified request, set intent to "other" and needs_clarification to true.
2. If the issue spans multiple departments or cannot be clearly routed, set route_to to "human_support".
3. Financial issues (duplicate charges, failed payments with deductions) are always "high" urgency.
4. Delivery marked complete but not received is "high" urgency.

## Example
Input: "주문한 신발이 아직 안 왔어요. 배송 조회가 안 됩니다."
Output:
{"intent": "shipping_issue", "urgency": "medium", "needs_clarification": false, "route_to": "shipping_ops"}

Respond with ONLY the JSON object. No explanation, no markdown fences."""


def load_dataset(path: str) -> list[dict]:
    tickets = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tickets.append(json.loads(line))
    return tickets


def call_llm(system_prompt: str, user_message: str) -> dict:
    """LLM 호출 후 raw response 반환"""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return {
        "text": response.content[0].text,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "model": response.model,
    }


def parse_and_validate(raw_text: str) -> tuple[TicketClassification | None, str | None]:
    """JSON 파싱 + Pydantic 검증"""
    try:
        # 마크다운 코드블록 제거
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        result = TicketClassification(**data)
        return result, None
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    except Exception as e:
        return None, f"Validation error: {e}"


def compare(predicted: TicketClassification, expected: dict) -> dict:
    """필드별 비교"""
    return {
        "intent_match": predicted.intent == expected["intent"],
        "urgency_match": predicted.urgency == expected["urgency"],
        "clarification_match": predicted.needs_clarification == expected["needs_clarification"],
        "route_match": predicted.route_to == expected["route_to"],
        "exact_match": (
            predicted.intent == expected["intent"]
            and predicted.urgency == expected["urgency"]
            and predicted.needs_clarification == expected["needs_clarification"]
            and predicted.route_to == expected["route_to"]
        ),
    }


def run_experiment(system_prompt: str, tickets: list[dict], label: str) -> dict:
    """한 프롬프트 버전에 대한 전체 실험 실행"""
    results = []
    total_input_tokens = 0
    total_output_tokens = 0

    for ticket in tickets:
        ticket_id = ticket["id"]
        message = ticket["customer_message"]
        expected = ticket["expected_output"]

        raw = call_llm(system_prompt, message)
        total_input_tokens += raw["usage"]["input_tokens"]
        total_output_tokens += raw["usage"]["output_tokens"]

        parsed, error = parse_and_validate(raw["text"])

        result = {
            "id": ticket_id,
            "raw_response": raw["text"],
            "usage": raw["usage"],
            "parse_success": parsed is not None,
            "error": error,
        }

        if parsed:
            result["predicted"] = parsed.model_dump()
            result["expected"] = expected
            result["comparison"] = compare(parsed, expected)
        else:
            result["predicted"] = None
            result["expected"] = expected
            result["comparison"] = None

        results.append(result)
        print(f"  [{label}] {ticket_id}: {'✓' if parsed and result['comparison']['exact_match'] else '✗'} {raw['text'][:60]}")

    # 집계
    parse_success = sum(1 for r in results if r["parse_success"])
    exact_matches = sum(1 for r in results if r["comparison"] and r["comparison"]["exact_match"])
    field_matches = {"intent": 0, "urgency": 0, "clarification": 0, "route": 0}
    for r in results:
        if r["comparison"]:
            if r["comparison"]["intent_match"]:
                field_matches["intent"] += 1
            if r["comparison"]["urgency_match"]:
                field_matches["urgency"] += 1
            if r["comparison"]["clarification_match"]:
                field_matches["clarification"] += 1
            if r["comparison"]["route_match"]:
                field_matches["route"] += 1

    summary = {
        "label": label,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "total_tickets": len(tickets),
        "parse_success": parse_success,
        "parse_rate": f"{parse_success}/{len(tickets)} ({parse_success/len(tickets)*100:.0f}%)",
        "exact_matches": exact_matches,
        "exact_match_rate": f"{exact_matches}/{len(tickets)} ({exact_matches/len(tickets)*100:.0f}%)",
        "field_matches": field_matches,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "results": results,
    }
    return summary


def find_mismatches(summary: dict) -> list[dict]:
    """불일치 건 추출"""
    mismatches = []
    for r in summary["results"]:
        if r["comparison"] and not r["comparison"]["exact_match"]:
            mismatches.append({
                "id": r["id"],
                "predicted": r["predicted"],
                "expected": r["expected"],
                "comparison": r["comparison"],
            })
        elif not r["parse_success"]:
            mismatches.append({
                "id": r["id"],
                "error": r["error"],
                "expected": r["expected"],
            })
    return mismatches


def main():
    print("=" * 60)
    print("1주차 과제: 고객 문의 티켓 구조화 추출")
    print(f"Model: {MODEL} | Temperature: {TEMPERATURE} | Max Tokens: {MAX_TOKENS}")
    print("=" * 60)

    tickets = load_dataset(DATASET_PATH)
    print(f"\n로드된 티켓 수: {len(tickets)}\n")

    # ── v1 실험 ──
    print("─" * 40)
    print("Prompt V1 실행 중...")
    print("─" * 40)
    v1_summary = run_experiment(SYSTEM_V1, tickets, "v1")

    time.sleep(1)  # rate limit 방지

    # ── v2 실험 ──
    print("\n" + "─" * 40)
    print("Prompt V2 실행 중...")
    print("─" * 40)
    v2_summary = run_experiment(SYSTEM_V2, tickets, "v2")

    # ── 결과 저장 ──
    output = {
        "v1": v1_summary,
        "v2": v2_summary,
    }

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ── 요약 출력 ──
    print("\n" + "=" * 60)
    print("결과 요약")
    print("=" * 60)
    for label, s in [("V1", v1_summary), ("V2", v2_summary)]:
        print(f"\n[{label}]")
        print(f"  파싱 성공률: {s['parse_rate']}")
        print(f"  Exact Match: {s['exact_match_rate']}")
        print(f"  필드별 일치: intent={s['field_matches']['intent']}/12, "
              f"urgency={s['field_matches']['urgency']}/12, "
              f"clarification={s['field_matches']['clarification']}/12, "
              f"route={s['field_matches']['route']}/12")
        print(f"  토큰 사용: input={s['total_input_tokens']}, output={s['total_output_tokens']}")

    # 불일치 건 출력
    for label, s in [("V1", v1_summary), ("V2", v2_summary)]:
        mismatches = find_mismatches(s)
        if mismatches:
            print(f"\n[{label}] 불일치 건 ({len(mismatches)}건):")
            for m in mismatches:
                print(f"  {m['id']}:")
                if "error" in m:
                    print(f"    에러: {m['error']}")
                else:
                    print(f"    예측: {m['predicted']}")
                    print(f"    정답: {m['expected']}")
                    print(f"    비교: {m['comparison']}")

    print(f"\n결과 파일 저장: results.json")


if __name__ == "__main__":
    main()
