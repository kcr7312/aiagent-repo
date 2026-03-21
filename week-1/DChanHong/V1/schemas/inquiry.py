from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

# 1. 고정된 선택지들을 Enum으로 정의
class IntentEnum(str, Enum):
    order_change = "order_change"
    shipping_issue = "shipping_issue"
    payment_issue = "payment_issue"
    refund_exchange = "refund_exchange"
    other = "other"

class UrgencyEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class RouteEnum(str, Enum):
    order_ops = "order_ops"
    shipping_ops = "shipping_ops"
    billing_ops = "billing_ops"
    returns_ops = "returns_ops"
    human_support = "human_support"

# 2. 메인 스키마 정의

class InquiryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: IntentEnum = Field(
        ...,
        description=(
            "고객 문의의 핵심 의도를 하나만 선택한다. "
            "주문 수정, 취소, 주소 변경, 옵션 변경은 order_change. "
            "출고, 배송 지연, 배송 누락, 배송 완료 오표시는 shipping_issue. "
            "결제 실패, 중복 결제, 청구 이상은 payment_issue. "
            "반품, 환불, 교환, 불량 접수는 refund_exchange. "
            "위 항목 중 하나로 명확히 단정하기 어렵거나 맥락이 부족하면 other."
        ),
    )
    urgency: UrgencyEnum = Field(
        ...,
        description=(
            "문의 처리 시급도를 선택한다. "
            "일반 문의이고 즉시 장애가 아니면 low. "
            "처리가 필요하지만 긴급 장애 또는 금전 리스크가 크지 않으면 medium. "
            "결제 이상, 분실/오배송, 배송 완료 오표시, 고객 불만 고조, "
            "수동 확인이 시급한 상황이면 high."
        ),
    )
    needs_clarification: bool = Field(
        ...,
        description=(
            "현재 텍스트만으로 intent 또는 처리 방향을 확정할 수 없으면 true. "
            "현재 정보만으로 1차 분류와 담당 부서 지정이 가능하면 false."
        ),
    )
    route_to: RouteEnum = Field(
        ...,
        description=(
            "선택한 intent와 일관된 담당 부서를 지정한다. "
            "order_change는 order_ops, shipping_issue는 shipping_ops, "
            "payment_issue는 billing_ops, refund_exchange는 returns_ops가 기본이다. "
            "맥락 부족, 다부서 이슈, 에스컬레이션 필요 시 human_support."
        ),
    )

# 예시 데이터 검증 테스트
test_data = {
    "intent": "shipping_issue",
    "urgency": "high",
    "needs_clarification": False,
    "route_to": "shipping_ops"
}

analysis = InquiryAnalysis(**test_data)
print(analysis.model_dump_json(indent=2))