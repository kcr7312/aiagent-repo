import os
import json
from google import genai
from pydantic import BaseModel
from typing import Literal


api_key = os.getenv("GOOGLE_API_KEY") 
client = genai.Client(api_key=api_key)


# Pydantic 스키마 정의 (출력 구조 강제)
class ClassifyTicket(BaseModel) : 
    intent: Literal["order_change", "shipping_issue", "payment_issue", "refund_exchange", "other"]
    urgency: Literal["low", "medium", "high"]
    needs_clarification: bool
    route_to: Literal["order_ops", "shipping_ops", "billing_ops", "returns_ops", "human_support"]


api_key = os.getenv("GOOGLE_API_KEY") 
client = genai.Client(api_key=api_key)


# prompt.txt 파일 불러오기
def load_text_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"{file_path} 프롬프트 파일 찾기 실패")
        return None

print("- - - 데이터 분류 시작 - - -\n")
total_result = []


# 현재 프롬프트 설정 (프롬프트가 길어서 따로 .txt로 저장)
current_prompt = load_text_file("prompt_v2.txt")

# JSON 파일명에 붙을 버전명 작성
version_name = "v2"


#dataset.json 불러오고, customer_message 분류 실행
with open("dataset.jsonl", "r", encoding="utf-8") as file:
    for line in file:
        if not line.strip(): # 빈 줄 건너뛰기 ㅂㄷㅂㄷㅂㄷ....
            continue

        data = json.loads(line)
        inquiry = data.get("customer_message")
        ticket_id = data.get("id")

        if not inquiry:
            continue

        try: 
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=inquiry,
                config={
                    "system_instruction": current_prompt,
                    "response_mime_type": "application/json",
                    "response_json_schema": ClassifyTicket.model_json_schema(),
                    "temperature": 0.1,
                    "max_output_tokens": 440,
                },
            )

            #JSON으로 파싱하기
            parsing_result = ClassifyTicket.model_validate_json(response.text)

            #결과 보기 좋게 데이터 저장
            entry_result = {
                "ticket_id": ticket_id,
                "original_message": inquiry,
                "analysis": parsing_result.model_dump()
            }
            total_result.append(entry_result)

            # 분류 과정 표시
            print(f"분류 완료: {ticket_id}...")

        except Exception as e:
            print(f"에러 발생 ({ticket_id}): {e} -> 통과하고 다음 진행")
            

#JSON 형식으로 파일 저장
file_name = f"classification_results_{version_name}.json"

with open(file_name, "w", encoding="utf-8") as outfile:
    json.dump(total_result, outfile, ensure_ascii=False, indent=2)

print("- - - - - 완료 - - - - - -")


