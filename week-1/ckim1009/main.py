import os
import json
from google import genai
from pydantic import BaseModel, ValidationError
from typing import Literal
import time
import os
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

class OutputSchema(BaseModel):
    # 1. 필드명과 데이터 타입 검증
    intent: Literal["order_change", "shipping_issue", "payment_issue", "refund_exchange", "other"]
    # 2. 허용된 값(Literal)인지 검증: "delivery" 같은 오타가 들어오면 에러 발생
    urgency: Literal["low", "medium", "high"]
    # 3. Boolean 타입인지 검증: "True"(문자열)가 아닌 실제 True/False인지 확인
    needs_clarification: bool
    route_to: Literal["order_ops", "shipping_ops", "billing_ops", "returns_ops", "human_support"]

system_prompt_v1 = '''
### 당신은 고객 지원 전문 분류 모델입니다.
### 당신의 목적은 주어진 고객 문의사항을 분석해 json 파일만 출력하는 것입니다.
### 당신이 출력해야할 json 파일의 구조는 다음과 같습니다. {{"intent": , "urgency": , "needs_clarification": , "route_to": }}

### "intent"
- "order_change": 주문 수정, 취소, 주소 변경, 옵션 변경
- "shipping_issue": 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- "payment_issue": 결제 실패, 중복 결제, 청구 이상
- "refund_exchange": 반품, 환불, 교환, 불량 접수
- "other": 위 4가지 intent로 단정하기 어렵거나 맥락이 부족한 경우

### "urgency"
- "low": 일반 문의, 즉각적인 대응이 필요한 장애가 아닌 경우
- "medium": 처리가 필요하지만 긴급하지 않은 장애/금전 리스크
- "high": 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인이 시급함

### "needs_clarification"
- True: 현재 텍스트만으로 처리 방향을 단정하기 어려움
- False : 현재 정보만으로 분류 가능

### "route_to"
- "order_ops": 주문/수정 담당
- "shipping_ops": 배송 담당
- "billing_ops": 결제/청구 담당
- "returns_ops": 환불/교환 담당
- "human_support": 맥락 부족, 다부서 이슈, 에스컬레이션 필요

### 고객문의사항:
'''

system_prompt_v2 = '''
### 당신은 고객 지원 전문 분류 모델입니다.
### 당신의 목적은 주어진 고객 문의사항을 분석해 json 파일만 출력하는 것입니다.
### 당신이 출력해야할 json 파일의 구조는 다음과 같습니다. {{"intent": , "urgency": , "needs_clarification": , "route_to": }}
### 아래는 각각의 구성요소에 대한 지침입니다.

### "intent"
- "order_change": 주문 수정, 취소, 주소 변경, 옵션 변경
- "shipping_issue": 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- "payment_issue": 결제 실패, 중복 결제, 청구 이상
- "refund_exchange": 반품, 환불, 교환, 불량 접수
- "other": 위 4가지 intent로 단정하기 어렵거나 맥락이 부족한 경우

### "urgency"
- "low": 일반 문의, 즉시 장애 아님
- "medium": 처리가 필요하지만 긴급 장애/금전 리스크는 아님
- "high": 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인이 시급함

### "needs_clarification"
- True: 현재 텍스트만으로 intent 또는 처리 방향을 단정하기 어려움
- False : 현재 정보만으로 1차 분류 가능

### "route_to"
- "order_ops": 주문/수정 담당
- "shipping_ops": 배송 담당
- "billing_ops": 결제/청구 담당
- "returns_ops": 환불/교환 담당
- "human_support": 맥락 부족, 다부서 이슈, 에스컬레이션 필요

### 고객문의사항:
'''



system_prompt = system_prompt_v2

def load_data(file_path):
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def ask_llm(customer_message):
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        config={
            'system_instruction':system_prompt,
            'temperature':0,
            "max_output_tokens": 500,
            "response_mime_type": "application/json",
        },
        contents = customer_message
    )
    return response.text


def main():
    parsing_success_count=0
    validation_count=0
    exact_match_count=0
    
    # Load data
    data = load_data('dataset.jsonl')

    total = len(data)
    
    for i, item in enumerate(data):

        id = item['id']
        customer_message = item["customer_message"]
        expected_output = item["expected_output"]


        try:
            # llm 호출
            raw_output = ask_llm(customer_message)
            
            # JSON 파싱
            parsed_dict = json.loads(raw_output)
            parsing_success_count += 1

            # 스키마 검증
            validated_output = OutputSchema(**parsed_dict).model_dump()
            validation_count +=1
            
            # Exact Match 확인
            is_correct = (validated_output == expected_output)
            if is_correct:
                print(f'{id}: 정답과 일치✅')
                exact_match_count += 1
            else:
                print(f'{id}: 정답과 불일치❌')

                # 차이가 나는 항목을 찾아 출력
                diffs = []
                for key in expected_output.keys():
                    expected_val = expected_output.get(key)
                    actual_val = validated_output.get(key)
                    
                    if expected_val != actual_val:
                        diffs.append(f"    - [{key}] 정답: {expected_val} | 출력결과: {actual_val}")
                
                # 불일치한 상세 내용 출력
                for diff in diffs:
                    print(diff)
            
            

        except json.JSONDecodeError:
            print(f"[{id}] 에러: JSON 파싱 실패")
        except ValidationError as e:
            print(f"[{id}] 에러: 스키마 불일치\n{e}")
        except Exception as e:
            print(f"[{id}] 에러: {e}")

        # 최종 결과 저장 (json.dump 사용)
        with open('prompt_v2_output.jsonl', "a", encoding="utf-8") as f:
            f.write(json.dumps(parsed_dict, ensure_ascii=False) + '\n')
        time.sleep(30)
    
        

    print(f'Parsing 성공 횟수: {parsing_success_count}/{total}')
    print(f'Schema 규칙 준수: {validation_count}/{total}')
    print(f'일치 정확도: {exact_match_count}/{total}')

    
    
    

if __name__ == "__main__":
    main()