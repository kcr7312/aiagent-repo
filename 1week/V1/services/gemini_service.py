from typing import Any


import os
from openai import OpenAI
from dotenv import load_dotenv
from schemas.inquiry import InquiryAnalysis # 정의한 스키마 불러오기
from prompts import INQUIRY_SYSTEM_PROMPT

load_dotenv()

class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        # 2026년 기준 최신 Flash 모델 사용 (추론 능력과 속도의 균형)
        self.model_name = "gemini-3-flash-preview" 
        self.system_prompt = INQUIRY_SYSTEM_PROMPT
        self.reasoning_effort = "low"

        # 생성(샘플링) 옵션 기본값
        # - temperature: 높을수록 다양/창의적, 낮을수록 결정적
        # - top_p: nucleus sampling
        # - max_tokens: 출력 토큰 상한 (response_format json_schema 사용 시 너무 낮으면 스키마를 못 맞출 수 있음)
        # - presence_penalty: 새로운 토픽/단어를 더 도입하도록 유도(반복 억제에 도움)
        # - frequency_penalty: 같은 단어/구문 반복을 더 강하게 억제
        # - seed: 동일 입력에서 재현성을 높이기 위한 시드(모델/플랫폼에 따라 완전 고정은 아닐 수 있음)
        self.generation_defaults = {
            "temperature": 0.2,
            "top_p": 0.95,
            "max_tokens": 512,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "seed": None,
        }
        self.response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "inquiry_analysis",
                "schema": InquiryAnalysis.model_json_schema()
            }
        }
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY가 .env 파일에 없습니다.")
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def get_config(self) -> dict:
        """현재 서비스에서 사용하는 모델 및 호출 옵션 정보를 반환합니다."""
        return {
            "model": self.model_name,
            "base_url": self.base_url,
            "generation_defaults": self.generation_defaults,
            "system_prompt": self.system_prompt,
            "response_format": self.response_format,
            "reasoning_effort": self.reasoning_effort,
        }

    def analyze_inquiry(
        self,
        customer_text: str,
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        seed: int | None = None,
    ) -> InquiryAnalysis:
        """고객 문의를 분석하여 구조화된 데이터를 반환합니다."""
        
        try:
            generation_opts = dict[str, Any](self.generation_defaults)
            if temperature is not None:
                generation_opts["temperature"] = temperature
            if top_p is not None:
                generation_opts["top_p"] = top_p
            if max_tokens is not None:
                generation_opts["max_tokens"] = max_tokens
            if presence_penalty is not None:
                generation_opts["presence_penalty"] = presence_penalty
            if frequency_penalty is not None:
                generation_opts["frequency_penalty"] = frequency_penalty
            if seed is not None:
                generation_opts["seed"] = seed

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": self.system_prompt
                    },
                    {"role": "user", "content": customer_text}
                ],
                temperature=generation_opts["temperature"],
                top_p=generation_opts["top_p"],
                max_tokens=generation_opts["max_tokens"],
                presence_penalty=generation_opts["presence_penalty"],
                # frequency_penalty=generation_opts["frequency_penalty"],
                # seed=generation_opts["seed"],
                # [핵심 옵션 1] 구조화된 응답 강제 (Response Format)
                # Pydantic 모델의 스키마를 JSON 형태로 전달합니다.
                response_format=self.response_format,
                # [핵심 옵션 2] 추론 노력 설정
                # 단순 분류 작업이므로 'low' 또는 'minimal'이 효율적입니다.
                extra_body={
                    "reasoning_effort": self.reasoning_effort
                }
            )

            # AI의 응답(JSON 문자열)을 Pydantic 객체로 변환
            json_result = response.choices[0].message.content
            return InquiryAnalysis.model_validate_json(json_result)

        except Exception as e:
            print(f"❌ 분석 중 오류 발생: {e}")
            raise