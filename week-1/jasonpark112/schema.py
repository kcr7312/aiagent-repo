# Literal -> 특정 값만 허용하도록 제한하는 타입 (ex. "low" | "medium" | "high") -> 이 값 중 하나만 써라
from typing import Literal
# BaseModel 데이터 검증용 클래스, JSON 문자열을 -> Python 객체로 바꾸면서 형식 검사 + 값 검사까지 해줌
from pydantic import BaseModel

#  이 형태의 json만 정상이다 라고 정의 하는 것
class TicketOutput(BaseModel):
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


    # 모델이 반환해야 하는 JSON 구조를 코드로 정의하는 파일. 예를 들면, intent, urgency 값이 허용된 것인지 검증할 때 씀