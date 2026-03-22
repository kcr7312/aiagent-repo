import json
from google import genai
from google.genai import types
from schema import TicketOutput

client = genai.Client()

MODEL_NAME = "gemini-2.5-flash"
TEMPERATURE = 0
MAX_OUTPUT_TOKENS = 256

SYSTEM_PROMPT_V2 = """
당신은 전자상거래 고객 문의 티켓 분류기입니다.

반드시 JSON 객체 하나만 출력하세요.
설명, 마크다운, 코드블록, 서문, 후문을 출력하지 마세요.

출력 필드:
- intent: order_change | shipping_issue | payment_issue | refund_exchange | other
- urgency: low | medium | high
- needs_clarification: true | false
- route_to: order_ops | shipping_ops | billing_ops | returns_ops | human_support

분류 기준:
- order_change: 주문 수정, 취소, 주소 변경, 옵션 변경
- shipping_issue: 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- payment_issue: 결제 실패, 중복 결제, 청구 이상
- refund_exchange: 반품, 환불, 교환, 불량 접수, 환불/교환 절차 문의
- other: 위로 단정하기 어렵거나 맥락이 부족한 경우

추가 규칙:
- order_change의 urgency는 보통 medium
- payment_issue의 urgency는 보통 high
- 일반 배송 문의는 medium, 배송 완료 오표시는 high
- refund_exchange는 보통 medium
- other는 보통 medium, 장기 미처리 불만은 high
- 환불할지 교환할지 아직 정하지 못했으면 needs_clarification=true
- 주문 문제인지 결제 문제인지 불명확하면 needs_clarification=true

route_to:
- order_change -> order_ops
- shipping_issue -> shipping_ops
- payment_issue -> billing_ops
- refund_exchange -> returns_ops
- other -> human_support
""".strip()

def classify_ticket(customer_message: str) -> dict:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Content(
                role="user",
                parts=[types.Part(text=customer_message)],
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT_V2,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=TicketOutput,
        ),
    )

    raw = (response.text or "").strip()
    validated = TicketOutput.model_validate_json(raw)
    return validated.model_dump()


def main():
    results = []

    with open("dataset.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            row = json.loads(line)
            expected = row["expected_output"]

            try:
                predicted = classify_ticket(row["customer_message"])

                intent_match = predicted["intent"] == expected["intent"]
                urgency_match = predicted["urgency"] == expected["urgency"]
                clarification_match = predicted["needs_clarification"] == expected["needs_clarification"]
                route_match = predicted["route_to"] == expected["route_to"]
                exact_match = intent_match and urgency_match and clarification_match and route_match

                results.append({
                    "id": row["id"],
                    "customer_message": row["customer_message"],
                    "expected_output": expected,
                    "predicted_output": predicted,
                    "parse_success": True,
                    "intent_match": intent_match,
                    "urgency_match": urgency_match,
                    "clarification_match": clarification_match,
                    "route_match": route_match,
                    "exact_match": exact_match,
                })

            except Exception as e:
                results.append({
                    "id": row["id"],
                    "customer_message": row["customer_message"],
                    "expected_output": expected,
                    "predicted_output": None,
                    "parse_success": False,
                    "intent_match": False,
                    "urgency_match": False,
                    "clarification_match": False,
                    "route_match": False,
                    "exact_match": False,
                    "error": str(e),
                })

    with open("results_v2.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("results_v2.json 저장 완료")


if __name__ == "__main__":
    main()