#  1주차 과제: LLM 호출을 테스트하고 이해하기

---

## 1. 사용한 모델, SDK, 실행 환경
- Model: gemini-3.1-flash-lite-preview
- SDK: Python용 Google GenAI SDK
- Library:
    - GenAI
    - Python: 3.11 (가상환경 이용)
    - Pydantic
- 실행 환경:
    - Windows (VScode)
    - 윈도우 환경 변수에 API KEY 저장

## 2. 실제 요청 구조 설명

### 2.1 system message

prompt_v2.txt

당신은 10년 차 베테랑 고객 센터 CS 매니저입니다. 주어진 고객 문의를 분석하여 알맞은 카테고리로 분류하세요. 아래의 분류 기준과 예외 규칙을 엄격하게 적용해야 합니다.

[분류 기준]
1. intent (문의 유형)
   - order_change: 주문 수정, 취소, 주소 변경, 옵션 변경
   - shipping_issue: 출고 확인, 배송 지연, 배송 누락, 배송 완료 오표시
   - payment_issue: 결제 실패, 중복 결제, 청구 이상
   - refund_exchange: 반품, 환불, 교환, 불량 접수
   - other: 시스템상 기본 제공되지 않는 요청(예: 선물 포장), 또는 맥락이 부족하여 위 4가지로 단정하기 어려운 경우

2. urgency (긴급도)
   - low: 일반 문의, 즉시 장애 아님 (예: 절차 문의, 정책 질문)
   - medium: 처리가 필요하지만 긴급 장애/금전 리스크는 아님 (예: 배송지 변경, 교환/환불 접수, 일반적인 배송 조회)
   - high: 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인이 시급함 (예: 결제 오류, 중복 결제, 배송 완료 오표시, 장기 미처리 건)

3. needs_clarification (추가 확인 필요 여부)
   - true: 현재 텍스트만으로 intent 또는 처리 방향을 단정하기 어려움
   - false:현재 정보만으로 1차 분류 가능

4. route_to (담당 부서)
   - order_ops: 주문/수정 담당
   - shipping_ops: 배송 담당
   - billing_ops: 결제/청구 담당
   - returns_ops: 환불/교환 담당
   - human_support: 다부서 이슈, 에스컬레이션 필요, intent가 'other'이거나 needs_clarification이 'true'인 복합적인 경우

[주의 및 예외 규칙 (Edge Cases)]
- "선물 포장" 같은 시스템 외적인 요구는 옵션 변경(order_change)이 아니라 기타(other) 및 human_support로 분류
- 고객이 "교환할지 환불할지 고민 중"처럼 명확한 액션을 정하지 않았다면 needs_clarification을 true로 설정하되, 문의의 성격이 명확하다면(예: 반품/교환) human_support가 아닌 해당 담당 부서(returns_ops 등)로 배정하세요
- 배송지 변경"이나 "단순 환불 요청"은 일상적인 CS 업무이므로 urgency를 medium으로 분류하세요
- 고객이 단순히 "결제 문제인지 모르겠다"며 원인을 묻는 일반적인 앱 오류 상황은, 실제 결제 실패나 중복 결제가 확인되지 않은 이상 urgency를 medium으로 분류하세요

### 2.2 user 메시지
- `dataset.jsonl` 파일의 `customer_message` 파라미터 참조
- `main.py`의 `inquiry`

### 2.3 model
- gemini-3.1-flash-lite-preview
- Google AI Studio의 비율 제한에서 확인 결과, 무료 티어에서 RPM/TPM/RPD 조건을 충족하는 모델을 선택했습니다.

### 2.4 temperature
- `temperature`:0.1
    - JSON 형식 출력은 Pydantic을 활용하여 고정했기 때문에, 기본 Gemini API 권장 설정인 0.1을 설정했습니다.

### 2.5 max_tokens
-`max_output_token`: 450
    - 토큰 수를 계산한 결과 한 라인당 36개의 토큰이 소비되었습니다.
    - `max_output_token`을 400으로 설정한 결과 오류가 발생했습니다.
    - 단순하게 36*12를 해서 432를 넣어주었지만 분류가 진행되지 않고 계속 대기하는 현상이 발생했습니다.
    - 토큰 수를 450으로 설정하여 실행 결과 무리없이 잘 출력이 되어서 일단 450으로 설정하였습니다.....

## 3. 실제 응답 구조 설명
### 3.1 본문 JSON 예시
```
  {
    "ticket_id": "ticket-01",
    "original_message": "주문한 러닝화가 아직 도착하지 않았어요. 배송이 어디까지 왔는지 확인하고 싶습니다.",
    "analysis": {
      "intent": "shipping_issue",
      "urgency": "medium",
      "needs_clarification": false,
      "route_to": "shipping_ops"
    }
  },

```

## 4. v1 -> v2에서 바꾼점

모호한 문의 사항에 대해서 Edge Cases를 추가했습니다.

[주의 및 예외 규칙 (Edge Cases)]
- "선물 포장" 같은 시스템 외적인 요구는 옵션 변경(order_change)이 아니라 기타(other) 및 human_support로 분류
- 고객이 "교환할지 환불할지 고민 중"처럼 명확한 액션을 정하지 않았다면 needs_clarification을 true로 설정하되, 문의의 성격이 명확하다면(예: 반품/교환) human_support가 아닌 해당 담당 부서(returns_ops 등)로 배정하세요
- 배송지 변경"이나 "단순 환불 요청"은 일상적인 CS 업무이므로 urgency를 medium으로 분류하세요
- 고객이 단순히 "결제 문제인지 모르겠다"며 원인을 묻는 일반적인 앱 오류 상황은, 실제 결제 실패나 중복 결제가 확인되지 않은 이상 urgency를 medium으로 분류하세요

## 5. 결과 비교
- JSON 파싱 성공률: 100%
- exact macth 개수
    - v1: 7
    - v2: 12

### 5.1 대표 실패 사레

#### 5.4.1 긴급도(urgency)가 기댓값과 다르게 설정된 경우

-ticket-05
    - 기댓값은 `medium`인데 AI는 `high`로 분류하였습니다.
    - 출고 전 수정 요청을 수동 확인이 시급함이라고 판단한 것으로 추정됩니다.

- ticket-08
    - 기댓값은 `medium`인데 AI는 `low`로 분류하였습니다.
    - 고객 문의사항의 실제 의도인 환불보다는 `먼저 알고 싶다`를 중심으로 두어 정책 문의로 판단한 것 같습니다.

- ticket-12
    - 기댓값은 `medium`인데 AI는 `low`로 분류하였습니다.
    - ticket-08 케이스와 마찬가지로 교환이나 환불보다는 `어떤 절차로 진행하면 될까요?`에 초점을 맞춰 판단한 것으로 추정됩니다.


```
  {
    "ticket_id": "ticket-05",
    "original_message": "배송지를 잘못 적었는데 아직 출고 전이면 수정하고 싶습니다.",
    "analysis": {
      "intent": "order_change",
      "urgency": "high",
      "needs_clarification": false,
      "route_to": "order_ops"
    }
  },
                        ⁝
  {
    "ticket_id": "ticket-08",
    "original_message": "포장은 안 뜯었는데 환불이 가능한지 먼저 알고 싶습니다.",
    "analysis": {
      "intent": "refund_exchange",
      "urgency": "low",
      "needs_clarification": false,
      "route_to": "returns_ops"
    }
  },
                        ⁝
  {
    "ticket_id": "ticket-12",
    "original_message": "사이즈가 안 맞아서 교환할지 환불할지 고민 중인데 어떤 절차로 진행하면 될까요?",
    "analysis": {
      "intent": "refund_exchange",
      "urgency": "low",
      "needs_clarification": false,
      "route_to": "returns_ops"
    }
  }
```

- v2 프롬프트에 다음과 같은 문구를 추가하여 조정하였습니다.
    - ticket-05: "배송지 변경"이나 "단순 환불 요청"은 일상적인 CS 업무이므로 urgency를 medium으로 분류하세요
    - ticket-08/12: 고객이 단순히 "결제 문제인지 모르겠다"며 원인을 묻는 일반적인 앱 오류 상황은, 실제 결제 실패나 중복 결제가 확인되지 않은 이상 urgency를 medium으로 분류하세요.

```
  {
    "ticket_id": "ticket-05",
    "original_message": "배송지를 잘못 적었는데 아직 출고 전이면 수정하고 싶습니다.",
    "analysis": {
      "intent": "order_change",
      "urgency": "medium",
      "needs_clarification": false,
      "route_to": "order_ops"
    }
  },
                        ⁝
  {
    "ticket_id": "ticket-08",
    "original_message": "포장은 안 뜯었는데 환불이 가능한지 먼저 알고 싶습니다.",
    "analysis": {
      "intent": "refund_exchange",
      "urgency": "medium",
      "needs_clarification": false,
      "route_to": "returns_ops"
    }
  },
                        ⁝
  {
    "ticket_id": "ticket-12",
    "original_message": "사이즈가 안 맞아서 교환할지 환불할지 고민 중인데 어떤 절차로 진행하면 될까요?",
    "analysis": {
      "intent": "refund_exchange",
      "urgency": "medium",
      "needs_clarification": true,
      "route_to": "returns_ops"
    }
  }
```

#### 5.4.2  ticket 11 - intent와 route_to 분류 실패

기댓값은 `other/human_support`인데 AI는 `order_change/order_ops`로 분류했습니다.
AI는 선물 포장 요청을 옵션 변경으로 판단한 것 같습니다.

```
 {
    "ticket_id": "ticket-11",
    "original_message": "선물용으로 포장 가능한가요? 가능하면 이번 주 안에 받고 싶어요.",
    "analysis": {
      "intent": "order_change",
      "urgency": "medium",
      "needs_clarification": false,
      "route_to": "order_ops"
    }
  }
```

다음과 같은 로직을 v2 프롬프트에 추가하였습니다.
    - "선물 포장" 같은 시스템 외적인 요구는 옵션 변경(order_change)이 아니라 기타(other) 및 human_support로 분류

```
  {
    "ticket_id": "ticket-11",
    "original_message": "선물용으로 포장 가능한가요? 가능하면 이번 주 안에 받고 싶어요.",
    "analysis": {
      "intent": "other",
      "urgency": "medium",
      "needs_clarification": false,
      "route_to": "human_support"
    }
  },
```

#### 5.4.3 ticket 12 - urgency/needs_clarification 분류 실패

기댓값은 `needs_clarification: true`인데 AI는 `false`로 분류했습니다.
고객이 행동을 결정하지 않은 상태를 AI가 포착하지 못한것 같습니다.

```
{
    "ticket_id": "ticket-12",
    "original_message": "사이즈가 안 맞아서 교환할지 환불할지 고민 중인데 어떤 절차로 진행하면 될까요?",
    "analysis": {
      "intent": "refund_exchange",
      "urgency": "low",
      "needs_clarification": false,
      "route_to": "returns_ops"
    }
}
```
다음과 같은 문구를 추가하였습니다. 
- 고객이 "교환할지 환불할지 고민 중"처럼 명확한 액션을 정하지 않았다면 needs_clarification을 true로 설정하되, 문의의 성격이 명확하다면(예: 반품/교환) human_support가 아닌 해당 담당 부서(returns_ops 등)로 배정하세요.

```
  {
    "ticket_id": "ticket-12",
    "original_message": "사이즈가 안 맞아서 교환할지 환불할지 고민 중인데 어떤 절차로 진행하면 될까요?",
    "analysis": {
      "intent": "refund_exchange",
      "urgency": "medium",
      "needs_clarification": true,
      "route_to": "returns_ops"
    }
  }
```