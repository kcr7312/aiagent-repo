#!/usr/bin/env python3

import os
from dotenv import load_dotenv
import json
from openai import OpenAI
from pydantic import BaseModel
from typing import Literal
import time

# .env 파일에서 환경 변수 로드
load_dotenv()

# 1. API 클라이언트 설정
# 환경 변수에 GEMINI_API_KEY가 등록되어 있어야 정상 작동합니다.
client = OpenAI(
    api_key=os.getenv("APT_KEY"), 
    base_url=os.getenv("BASE_URL") # 구글 서버로 라우팅
)

# 2. Pydantic을 이용한 응답 스키마 강제 정의
# 모델이 무조건 이 형식과 타입에 맞춰서만 응답하게 만듭니다.
class TicketClassification(BaseModel):
    intent: Literal["order_change", "shipping_issue", "payment_issue", "refund_exchange", "other"]
    urgency: Literal["low", "medium", "high"]
    needs_clarification: bool
    route_to: Literal["order_ops", "shipping_ops", "billing_ops", "returns_ops", "human_support"]

# 3. 프롬프트 버전 관리
# v1: 아주 기본적인 지시사항만 있는 프롬프트
system_prompt_v1 = """
알아서 잘 분류해
"""

system_prompt_v2 = """
너는 이커머스 고객 센터의 티켓 라우팅 자동화 시스템이야.
사용자의 문의 텍스트를 분석해서 다음의 엄격한 기준에 따라 분류해.

[1. intent 분류 기준]
- order_change: 주문 옵션(색상 등) 변경, 배송지 주소 수정
- shipping_issue: 출고 및 배송 상태 확인, 배송 완료 오표시(수령 전 완료 처리)
- payment_issue: 이중 결제, 결제 실패 후 계좌 출금 등 결제 오류
- refund_exchange: 사이즈 교환, 환불 가능 여부, 교환/환불 절차 문의
- other: 과거 문의 지연(내용 모름), 원인 불명의 앱 오류(결제/주문 불분명), 선물 포장 등 규격 외 문의

[2. urgency 분류 기준]
- high: 고객의 금전 리스크(중복 결제, 실패 후 출금), 분실 위험(배송 완료 오표시), 장기 미처리로 인한 불만(지난주 요청 지연 등)은 반드시 high로 분류.
- medium: 일반적인 배송 조회, 옵션/주소 변경, 단순 교환 및 환불 문의, 단순 앱 오류. (주의: 단순 환불/교환 문의라도 돈이나 상품이 이동하므로 low가 아닌 medium으로 할당할 것)
- low: 즉시 처리가 필요 없는 단순 정보성 질문.

[3. needs_clarification (추가 확인 필요 여부) 판단 기준]
- true: 아래 3가지 경우에만 true로 설정할 것.
  1) 고객이 어떤 요청을 했었는지 텍스트만으로 알 수 없을 때 (예: "지난주 요청 건")
  2) 장애의 원인을 고객도 모를 때 (예: "결제 문제인지 주문 문제인지 모름")
  3) 고객이 목적(intent)은 정했으나 세부 행동을 결정하지 못했을 때 (예: "교환할지 환불할지 고민 중")
- false: "~가능할까요?", "확인해주세요"와 같이 의문문이나 요청형으로 끝나더라도, 고객이 원하는 바(색상 변경, 주소 수정, 배송 확인 등)가 명확하다면 무조건 false.

[4. route_to 담당 부서 매핑]
- intent가 order_change -> order_ops
- intent가 shipping_issue -> shipping_ops
- intent가 payment_issue -> billing_ops
- intent가 refund_exchange -> returns_ops
- intent가 other -> human_support
"""

def run_evaluation(prompt_version, system_instruction):
    dataset = []
    
    # 데이터 로드
    try:
        with open('dataset.jsonl', 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip(): # 빈 줄은 건너뛰기
                    dataset.append(json.loads(line))
    except FileNotFoundError:
        print("dataset.jsonl 파일이 같은 폴더에 없습니다. 확인해주세요!")
        return

    exact_match_count = 0
    parsing_success_count = 0
    
    print(f"\n=== 프롬프트 {prompt_version} 테스트 시작 ===")
    
    # 12건의 데이터를 하나씩 돌면서 모델에게 물어보고 정답과 채점합니다.
    for i, item in enumerate(dataset):
        user_message = item['customer_message']
        expected = item['expected_output']
        
        try:
            # LLM 호출 부분 (모델, 온도, 토큰, 스키마 설정)
            response = client.beta.chat.completions.parse(
                model="gemini-2.5-flash", # gpt-4o 대신 gemini 이름을 넣습니다.
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.0,
                max_tokens=1000,
                response_format=TicketClassification # OpenAI의 Structured Output 기능 사용
            )
            print(f"{i+1}번 티켓 처리 중...") # 진행 상황 표시


            # 텍스트로 온 JSON을 파이썬 딕셔너리로 변환
            model_output = json.loads(response.choices[0].message.content)
            parsing_success_count += 1
                
            # 정답과 완벽히 일치하는지 확인 (Exact Match)
            is_exact_match = True
            for key in expected.keys():
                if model_output.get(key) != expected[key]:
                    is_exact_match = False
                    break
                    
            if is_exact_match:
                exact_match_count += 1
                print(f"{i+1}번 티켓: 정답과 일치!")
                print(f"문의내용: {user_message}")
                print(f"담당부서: {model_output['route_to']}\n\n\n")
            else:
                # 틀린 문제는 원인 분석을 위해 터미널에 출력해 줍니다.
                print(f"[불일치 발생 - {i+1}번 티켓]")
                print(f"문의내용: {user_message}")
                print(f"기대값: {expected}")
                print(f"모델출력: {model_output}\n\n\n")        
        except Exception as e:
            print(f"{i+1}번 티켓 처리 중 에러 발생: {e}")

    print(f"\n=== {prompt_version} 최종 결과 ===")
    print(f"파싱 성공률: {parsing_success_count}/{len(dataset)}")
    print(f"Exact Match: {exact_match_count}/{len(dataset)}")

if __name__ == "__main__":
    # run_evaluation("v1", system_prompt_v1)

    # time.sleep(2) # 잠시 대기 후 다음 테스트 실행
    run_evaluation("v2", system_prompt_v2)