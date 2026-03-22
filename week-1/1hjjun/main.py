import os
from google import genai
import json
import time
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수에서 키 가져오기
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)


# 2. 시스템 프롬프트 (v2)
SYSTEM_PROMPT_V2 = """
너는 이커머스 고객 지원 전문 AI야. 
다음 지침에 따라 고객 문의를 JSON으로 구조화해.

1. intent 분류: 
    - 배송/포장 문제는 shipping_issue
    - 결제 오류/중복은 payment_issue
    - 주문/주소 변경은 order_change
    - 단순 변심/사이즈 교환/환불은 refund_exchange
    - 그 외 모호하거나 에스컬레이션이 필요한 건 other

2. urgency 판단:
    - high: 금전적 손실, 오배송 확인, 반복된 미처리 문의(고객 불만 고조). (지난주 문제가 해결되지 않음)
    - medium: 일반적인 서비스 요청, 단순 배송 확인.

3. needs_clarification 판단:
    -상담원이 intent에 맞는 route_to로 이어줄 수 있다면 false로 설정하십시오.
    -하지만 다음 중 하나라도 해당하면 반드시 true로 설정하십시오.
    -결정 미정: 고객이 두 가지 이상의 옵션(예: 교환 혹은 환불) 사이에서 고민 중이거나 결정을 내리지 못한 경우.("가능한지 알고 싶다"는 결정한 것으로 판단) 
    -복합/부차적 요청: 메인 요청이 있더라도 선물 포장, 배송일 지정 등 시스템이 즉시 확답하기 어려운 부차적인 요구사항이 포함된 경우.
    

4. route_to:
    - intent에 맞춰 담당 부서를 지정해. 
    - shipping_issue -> shipping_ops
    - billing_issue -> billing_ops
    - refund_exchange -> returns_ops
    - order_change -> order_ops
    - 판단이 어려우면 반드시 human_support로 보내.


반드시 JSON 형식으로만 응답해.
"""

def load_data(file_path):
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def classify_ticket(customer_text):
    # 최신 SDK 호출 방식
    response = client.models.generate_content(
        model="gemini-2.5-flash", # 현재 사용 가능한 모델명으로 확인
        config={
            "system_instruction": SYSTEM_PROMPT_V2,
            "temperature": 0.1,
            "response_mime_type": "application/json",
            "max_output_tokens": 500
        },
        contents=customer_text
    )
    return response.text

def main():
    # 1. 데이터 불러오기
    dataset = load_data('dataset.jsonl')
    print(f"총 {len(dataset)}건의 데이터를 불러왔습니다.\n")

    results = []
    exact_match_count = 0

    # 2. 루프를 돌며 처리
    for i, item in enumerate(dataset):
        customer_msg = item['customer_message']
        expected = item['expected_output']
        
        print(f"[{i+1}/12] 처리 중... (ID: {item['id']})")
        
        try:
            # AI 호출
            raw_response = classify_ticket(customer_msg)
            predicted = json.loads(raw_response) # 문자열을 JSON 객체로 변환
            
            # print(f"AI 응답 결과:")
            # print(json.dumps(predicted, indent=2, ensure_ascii=False)) # 들여쓰기 포함 출력

            # 결과 비교 (Exact Match 확인)
            is_match = (predicted == expected)
            if is_match:
                exact_match_count += 1
            
            # 결과 저장용 데이터 생성
            results.append({
                "id": item['id'],
                "input": customer_msg,
                "expected": expected,
                "predicted": predicted,
                "is_match": is_match
            })
            
            print(f"   - 결과: {'✅ 일치' if is_match else '❌ 불일치'}")
            
        except Exception as e:
            print(f"   - 에러 발생: {e}")
            results.append({"id": item['id'], "error": str(e)})
        
        # API 할당량 보호를 위해 짧은 휴식 (필요 시)
        #time.sleep(1)

    # 3. 최종 결과 저장
    with open('results_v1.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n" + "="*30)
    print(f"전체 처리 완료!")
    print(f"정답 일치(Exact Match): {exact_match_count} / {len(dataset)}")
    print(f"결과가 'results_v1.json'에 저장되었습니다.")
    print("="*30)

if __name__ == "__main__":
    main()