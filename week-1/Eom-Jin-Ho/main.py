import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from typing import Literal

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class TicketClassification(BaseModel):
    intent: Literal[
        "order_change",
        "shipping_issue",
        "payment_issue",
        "refund_exchange",
        "other"
    ]
    urgency: Literal["low", "medium", "high"]
    needs_clarification: bool
    route_to: Literal[
        "order_ops",
        "shipping_ops",
        "billing_ops",
        "returns_ops",
        "human_support"
    ]





system_prompt_v1 = """
너는 고객 문의 티켓을 분류하는 AI다.

반드시 아래 규칙을 모두 지켜라.

1. 반드시 JSON 객체 하나만 출력한다.
2. JSON 바깥의 설명, 문장, 코드블록, 마크다운을 절대 출력하지 않는다.
3. 모든 필드는 반드시 아래 허용값 중 하나만 사용한다.

intent:
- order_change : 주문 수정, 취소, 주소 변경, 옵션 변경
- shipping_issue : 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- payment_issue : 결제 실패, 중복 결제, 청구 이상
- refund_exchange : 반품, 환불, 교환, 불량 접수
- other : 위로 단정하기 어렵거나 맥락이 부족한 경우

urgency:
- low : 일반 문의, 즉시 장애 아님
- medium : 처리가 필요하지만 긴급 장애/금전 리스크는 아님
- high : 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인이 시급함

needs_clarification:
- true : 현재 텍스트만으로 intent 또는 처리 방향을 단정하기 어려움
- false : 현재 정보만으로 1차 분류 가능

route_to:
- order_ops : 주문/수정 담당
- shipping_ops : 배송 담당
- billing_ops : 결제/청구 담당
- returns_ops : 환불/교환 담당
- human_support : 맥락 부족, 다부서 이슈, 에스컬레이션 필요
"""


system_prompt_v2 = """
너는 고객 문의 티켓을 분류하는 AI다.

반드시 아래 규칙을 모두 지켜라.

1. 반드시 JSON 객체 하나만 출력한다.
2. JSON 바깥의 설명, 문장, 코드블록, 마크다운을 절대 출력하지 않는다.
3. 모든 필드는 반드시 아래 허용값 중 하나만 사용한다.

intent:
- order_change : 주문 수정, 취소, 주소 변경, 옵션 변경
- shipping_issue : 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- payment_issue : 결제 실패, 중복 결제, 청구 이상
- refund_exchange : 반품, 환불, 교환, 불량 접수
- other : 위로 단정하기 어렵거나 맥락이 부족한 경우

urgency:
- low : 일반 문의, 즉시 장애 아님
- medium : 처리가 필요하지만 긴급 장애/금전 리스크는 아님, 환불/교환 요청 및 절차 문의, 일반 문의라도 일정 조건이나 빠른 처리 요구가 붙은 건
- high : 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인이 시급한 건, 이미 이전에 요청했지만 아직 처리되지 않은 건, 반복 문의 또는 지연이 누적된 건

needs_clarification:
- true : 현재 텍스트만으로 intent 또는 처리 방향을 단정하기 어려운 경우, 교환할지 환불할지 아직 결정하지 못한 경우, 고객이 원하는 처리 방향이 완전히 정해지지 않은 경우, 주문/결제/배송/환불 중 어느 범주로 봐야 할지 애매한 부가 요청이나 조건 문의인 경우
- false : 현재 정보만으로 1차 분류 가능

추가 규칙:
- 환불/교환의 가능 여부, 절차, 조건을 묻는 문의는 refund_exchange로 분류하고 needs_clarification은 false로 본다.
- 단, 교환할지 환불할지 아직 결정하지 못한 경우는 refund_exchange로 분류하되 needs_clarification은 true로 본다.
- 포장 가능 여부, 선물 포장, 기타 부가 서비스 요청처럼 기본 분류에 바로 들어가지 않는 문의는 other로 분류하고 needs_clarification을 true로 본다.
- 이미 이전에 요청했지만 아직 처리되지 않았다고 말하는 경우는 urgency를 high로 본다.

route_to:
- order_ops : 주문/수정 담당
- shipping_ops : 배송 담당
- billing_ops : 결제/청구 담당
- returns_ops : 환불/교환 담당
- human_support : 맥락 부족, 다부서 이슈, 에스컬레이션 필요
"""

def get_model_price(model_name):
    price_table = {
        "gpt-5.4-mini": (0.25, 2.00),
        "gpt-5.4-nano": (0.05, 0.40),
        "gpt-5-nano": (0.05, 0.40)
    }
    
    return price_table[model_name]

def run_test(system_prompt, version_name, model_name):
    print(f"\n================ {version_name} / {model_name} 시작 ================\n")

    # 카운트 변수
    total = 0
    json_success = 0
    validation_success = 0
    exact_match = 0
    total_input = 0
    total_output = 0
    total_token =0

    with open("../data/dataset.jsonl", "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            item = json.loads(line)
            customer_message = item["customer_message"]
            expected = item["expected_output"]

            total += 1  # 전체 개수 증가

            print(f"\n[{version_name}] {i}번 데이터")
            print(customer_message)

            response = client.responses.create(
                model=model_name,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"고객 문의: {customer_message}"}
                ],
                temperature=0,
                max_output_tokens=100,
                
            )

            usage = response.usage
            total_input += usage.input_tokens
            total_output += usage.output_tokens
            total_token += usage.total_tokens
            print("모델 응답:", response.output_text)
            print("토큰:", response.usage)
            

            try:
                parsed = json.loads(response.output_text)
                json_success += 1
                print("JSON 파싱 성공")

                validated = TicketClassification(**parsed)
                validation_success += 1
                print("검증 성공")
                
                result_dict = validated.model_dump()

                if result_dict == expected:
                    exact_match += 1
                    print("정답 맞음 (exact match)")
                else:
                    print("정답 틀림 (exact match 실패)")
                    print("예상값:", expected)
                    print("예측값", result_dict)
                    
                    for key in expected:
                        if expected[key] != result_dict[key]:
                             print(f" - {key} 다름 | expected={expected[key]} / predicted={result_dict[key]}")
                   

            except json.JSONDecodeError:
                print("JSON 파싱 실패")

            except ValidationError:
                print("검증 실패")
    
    input_price_per_1m, output_price_per_1m = get_model_price(model_name)
    input_cost = (total_input / 1_000_000) * input_price_per_1m
    output_cost = (total_output / 1_000_000) * output_price_per_1m
    total_cost = input_cost + output_cost
    

    # 결과 출력
    print(f"\n===== {version_name} / {model_name} 결과 =====")
    print("전체:", total)
    print("JSON 성공:", json_success)
    print("검증 성공:", validation_success)
    print("Exact Match:", exact_match)
    print("총 input 토큰:", total_input)
    print("총 output 토큰", total_output)
    print("총 토큰", total_token)
    print("총 input 비용(USD):", round(input_cost, 6))
    print("총 output 비용(USD):", round(output_cost, 6))
    print("총 비용(USD):", round(total_cost, 6))
    
    
    



#run_test(system_prompt_v1, "v1")
run_test(system_prompt_v2, "v2", "gpt-5.4-nano")
run_test(system_prompt_v2, "v2", "gpt-5.4-mini")
