import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from typing import Literal

# 1. 환경 설정 및 API 키 로드
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 2. 데이터 스키마 정의 (Pydantic)
class TicketAnalysis(BaseModel):
    intent: Literal["order_change", "shipping_issue", "payment_issue", "refund_exchange", "other"]
    urgency: Literal["low", "medium", "high"]
    needs_clarification: bool
    route_to: Literal["order_ops", "shipping_ops", "billing_ops", "returns_ops", "human_support"]

# 3. LLM 호출 함수 (v1: 기초 프롬프트)
def analyze_ticket_v1(customer_message: str):
    system_prompt = """당신은 고객 지원 티켓 분류 전문가입니다. 
    고객의 메시지를 분석하여 반드시 지정된 JSON 형식으로만 응답하세요."""
    
    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"고객 메시지: {customer_message}"}
            ],
            response_format=TicketAnalysis, 
            temperature=0, 
            max_tokens=500
        )
        return response.choices[0].message.parsed.model_dump(), response.usage
    except Exception as e:
        print(f"v1 Error: {e}")
        return None, None

# 4. LLM 호출 함수 (v2: 분석된 실패 원인을 바탕으로 지침 강화)
def analyze_ticket_v2(customer_message: str):
    # 명확한 가이드라인과 헷갈리기 쉬운 엣지 케이스(Few-shot)를 조합한 최종 프롬프트
    system_prompt = """당신은 고객 지원 티켓 분류 전문가입니다.
    고객의 메시지를 분석하여 반드시 지정된 JSON 형식으로만 응답하세요.

    [분류 가이드라인]
    1. Intent
       - order_change: 주문 수정, 취소, 주소 변경, 옵션 변경
       - shipping_issue: 출고, 배송 지연, 배송 누락, 배송 완료 오표시
       - payment_issue: 결제 실패, 중복 결제, 청구 이상
       - refund_exchange: 반품, 환불, 교환, 불량 접수
       - other: 위로 단정하기 어렵거나 맥락이 부족한 경우 (예: 선물 포장 등 특수 요청)

    2. Urgency
       - low: 일반 문의, 즉시 장애 아님
       - medium: 처리가 필요하지만 긴급 장애/금전 리스크는 아님
       - high: 결제 이상, 분실/오배송, 고객 불만 고조(이전 요청 미처리), 수동 확인이 시급함

    3. Needs Clarification
       - false: 현재 텍스트만으로 1차 분류(Intent)가 명확히 가능한 경우. (예: 환불 규정에 대한 단순 질문 등)
       - true: 텍스트만으로 처리 방향을 단정하기 어려움. (예: 교환/환불 중 고민, 특수 요청 확인 등)

    4. Route To
       - order_ops, shipping_ops, billing_ops, returns_ops, human_support 중 하나로 배정.

    [헷갈리기 쉬운 상황에 대한 기준 (Few-shot)]
    - 메시지: "포장은 안 뜯었는데 환불이 가능한지 먼저 알고 싶습니다."
      해석: 환불에 대한 질문이므로 의도가 명확함(needs_clarification: false).
      출력: {"intent": "refund_exchange", "urgency": "medium", "needs_clarification": false, "route_to": "returns_ops"}
      
    - 메시지: "선물용으로 포장 가능한가요?"
      해석: 정규 옵션 변경이 아닌 특수 문의이므로 other로 분류함.
      출력: {"intent": "other", "urgency": "medium", "needs_clarification": true, "route_to": "human_support"}
      
    - 메시지: "사이즈가 안 맞아서 교환할지 환불할지 고민 중..."
      출력: {"intent": "refund_exchange", "urgency": "medium", "needs_clarification": true, "route_to": "returns_ops"}
      
    - 메시지: "지난주에 요청드린 건이 아직도 처리되지 않은 것 같아요."
      출력: {"intent": "other", "urgency": "high", "needs_clarification": true, "route_to": "human_support"}
    """
    
    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"고객 메시지: {customer_message}"}
            ],
            response_format=TicketAnalysis, 
            temperature=0, 
            max_tokens=500
        )
        return response.choices[0].message.parsed.model_dump(), response.usage
    except Exception as e:
        print(f"v2 Error: {e}")
        return None, None

# 5. 데이터셋 로드 및 비교 실험 실행
def run_experiment():
    v1_exact_matches = 0
    v2_exact_matches = 0
    
    try:
        with open('dataset.jsonl', 'r', encoding='utf-8') as f:
            tickets = [json.loads(line) for line in f]
    except FileNotFoundError:
        print("Error: dataset.jsonl 파일을 찾을 수 없습니다.")
        return

    print(f"--- 1주차 과제: v1 vs v2 성능 비교 (총 {len(tickets)}건) ---\n")

    for ticket in tickets:
        msg = ticket['customer_message']
        expected = ticket['expected_output']
        
        # v1, v2 각각 호출
        actual_v1, _ = analyze_ticket_v1(msg)
        actual_v2, _ = analyze_ticket_v2(msg)
        
        is_match_v1 = (actual_v1 == expected)
        is_match_v2 = (actual_v2 == expected)
        
        if is_match_v1: v1_exact_matches += 1
        if is_match_v2: v2_exact_matches += 1

        # 터미널 출력 로직
        print(f"[{ticket['id']}] 고객 메시지: {msg}")
        
        # v1 결과 출력
        if is_match_v1:
            print("  ▶ [v1] Match: True ✅")
        else:
            print("  ▶ [v1] Match: False ❌")
            print(f"     🎯 정답: {expected}")
            print(f"     🤖 응답: {actual_v1}")
            
        # v2 결과 출력
        if is_match_v2:
            print("  ▶ [v2] Match: True ✅")
        else:
            print("  ▶ [v2] Match: False ❌")
            print(f"     🎯 정답: {expected}")
            print(f"     🤖 응답: {actual_v2}")
            
        print("-" * 50)

    # 최종 결과 요약 출력
    print("\n" + "="*40)
    print("      최종 실험 결과 요약 (Exact Match)")
    print("="*40)
    print(f"전체 건수: {len(tickets)}")
    print(f" ▷ v1 성적: {v1_exact_matches}/{len(tickets)} ({v1_exact_matches/len(tickets)*100:.1f}%)")
    print(f" ▷ v2 성적: {v2_exact_matches}/{len(tickets)} ({v2_exact_matches/len(tickets)*100:.1f}%)")
    print("="*40)

if __name__ == "__main__":
    run_experiment()