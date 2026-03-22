import json
from google import genai
from google.genai import types
from schema import TicketOutput

# Gemini API 호출용 객체 환경변수에 API key가 설정되어야 한다.
client = genai.Client()
# 어떤 모델을 사용할지
MODEL_NAME = "gemini-2.5-flash"
# 출력 랜덤성 정도 0은 가장 최소화 특히 이번 실습에서는 창의성보다 일관성이 중요하니까 0이 좋음
TEMPERATURE = 0
# 모델이 생성할 최대 출력 길이 제한, 단위는 토큰 1토큰은 대략 0.75 단어 (영어 기준)
MAX_OUTPUT_TOKENS = 256

# 시스템 프롬프트 모델에게 역할을 주는 핵심 규칙 "패르소나와 메타인지, MoE(Mixture of Experts) -> 문제를 카테고리별로 나눠서 판단하는 구조"
SYSTEM_PROMPT_V1 = """
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
- refund_exchange: 반품, 환불, 교환, 불량 접수
- other: 위로 단정하기 어렵거나 맥락이 부족한 경우
""".strip()
# strip -> 문자열 앞뒤 공백/줄바꿈 제거


# 고객 문의 문장 하나를 받아서 모델에게 분류시키고 검증된 딕셔너리 결과를 반환하는 함수이다.
def classify_ticket(customer_message: str) -> dict:
    response = client.models.generate_content(
        # 모델 종류
        model=MODEL_NAME,
        # 모델에게 전달할 사용자 입력, 즉 실제 입력은 customer_message 한 줄이다.
        contents=[
            types.Content(
                role="user",
                parts=[types.Part(text=customer_message)],
            )
        ],
        # 아까 만든 시스템 프롬프트를 적용 즉 모델은 그 규칙을 따르면서 답해야 함
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT_V1,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            #  응답 형식을 JSON으로 강하게 유도
            response_mime_type="application/json",
            # 모델이 출력할 JSON 구조를 TiketOutput 스키마에 맞추도록 제한
            response_schema=TicketOutput,
        ),
    )
    # 여기서 모델 응답을 실제 Python 딕셔너리로 바꾼다. 딕셔녀리 -> 키 : 값 형태로 데이터를 저장하는 자료형
    raw = (response.text or "").strip()
    # Pydantic 검증 단계, 즉 raw JSON 문자열이 정말 TicketOutput 형식에 맞는지 검사
    validated = TicketOutput.model_validate_json(raw)
    # 검증된 Pydantic 객체를 일반 Python dict로 변환해서 반환 model_dump는 Pydantic의 함수이다.
    return validated.model_dump()


# 전체 데이터셋을 읽어서 결과를 쌓고 저장하는 메인 로직
def main():
    #  전체 데이터셋을 읽어서 결과를 쌓고 저장하는 메인 로직이다. results는 각 샘플 평가 결과를 담는 리스트
    results = []

    # 데이터셋 파일 읽기이고 dataset.jsonl은 json lines 형식 파일로 보통 한 줄에 json 객체 하나씩 들어 있음
    with open("dataset.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # 파일 데이터가 원래 json이더라도 python에서 읽게 되면 문자열이 되기 때문에 json.loads를 해줘야 한다.
            row = json.loads(line)
            # 정답 레이블 expected_output을 꺼낸다.
            expected = row["expected_output"]

            # 예측 수행
            try:
                # 고객 메시지를 모델에 넣어서 예측 결과를 받아옴
                predicted = classify_ticket(row["customer_message"])

                # 정답 비교
                intent_match = predicted["intent"] == expected["intent"]
                urgency_match = predicted["urgency"] == expected["urgency"]
                clarification_match = predicted["needs_clarification"] == expected["needs_clarification"]
                route_match = predicted["route_to"] == expected["route_to"]
                exact_match = intent_match and urgency_match and clarification_match and route_match

                # 정상적으로 분류와 파싱이 끝나면 결과를 results 리스트에 추가
                results.append({
                    "id": row["id"],
                    "customer_message": row["customer_message"],
                    "expected_output": expected,
                    "predicted_output": predicted,
                    # parse_suceess : True 는 모델 출력이 JSON 스키마 검증까지 통과했다는 뜻
                    "parse_success": True,
                    "intent_match": intent_match,
                    "urgency_match": urgency_match,
                    "clarification_match": clarification_match,
                    "route_match": route_match,
                    "exact_match": exact_match,
                })

            # 모델 호출이나 json 파싱, 스키마 검증 중 에러가 나면 여기로 (ex. 모델 응답이 비어 있음, json 문법이 깨짐, 허용되지 않은 값 출력, API 오류 발생)
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

    # 결과 저장, 최종 결과 전체를 json 파일로 저장
    with open("results_v1.json", "w", encoding="utf-8") as f:
        # ensure_ascii -> 한글이 \uXXXX 형태로 깨지지 않게 저장
        # indent=2 -> 들여쓰기 해서 사람이 읽기 쉽게 저장
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("results_v1.json 저장 완료")


if __name__ == "__main__":
    main()