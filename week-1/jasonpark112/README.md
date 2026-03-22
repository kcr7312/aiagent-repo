# LLM Ticket Classification Experiment

## 1. 사용한 모델, SDK, 실행 환경

- **SDK**: `google-genai` Python SDK
- **Language**: Python 3.12.13
- **실행 환경**: local macOS terminal (venv)


## 2. 실제 요청 구조 설명

#### v1 
```
System 메시지

당신은 전자상거래 고객 문의 티켓 분류기입니다.

반드시 JSON 객체 하나만 출력하세요.
설명, 마크다운, 코드블록, 서문, 후문을 출력하지 마세요.

출력 필드:
- intent: order_change | shipping_issue | payment_issue | refund_exchange | other
- urgency: low | medium | high
- needs_clarification: true | false
- route_to: order_ops | shipping_ops | billing_ops | returns_ops | human_support

분류 기준:
- order_change: 주문 수정, 취소, 주소 변경, 옵션 변경
- shipping_issue: 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- payment_issue: 결제 실패, 중복 결제, 청구 이상
- refund_exchange: 반품, 환불, 교환, 불량 접수
- other: 위로 단정하기 어렵거나 맥락이 부족한 경우
```
- **Model**: `gemini-3-flash-preview`
- **temperature** : `0`
- **max_output_token** : `300`


#### v2 
```
System 메시지

당신은 전자상거래 고객 문의 티켓 분류기입니다.

반드시 JSON 객체 하나만 출력하세요.
설명, 마크다운, 코드블록, 서문, 후문을 출력하지 마세요.

출력 필드:
- intent: order_change | shipping_issue | payment_issue | refund_exchange | other
- urgency: low | medium | high
- needs_clarification: true | false
- route_to: order_ops | shipping_ops | billing_ops | returns_ops | human_support

분류 기준:
- order_change: 주문 수정, 취소, 주소 변경, 옵션 변경
- shipping_issue: 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- payment_issue: 결제 실패, 중복 결제, 청구 이상
- refund_exchange: 반품, 환불, 교환, 불량 접수, 환불/교환 절차 문의
- other: 위로 단정하기 어렵거나 맥락이 부족한 경우

추가 규칙:
- order_change의 urgency는 보통 medium
- payment_issue의 urgency는 보통 high
- 일반 배송 문의는 medium, 배송 완료 오표시는 high
- refund_exchange는 보통 medium
- other는 보통 medium, 장기 미처리 불만은 high
- 환불할지 교환할지 아직 정하지 못했으면 needs_clarification=true
- 주문 문제인지 결제 문제인지 불명확하면 needs_clarification=true

route_to:
- order_change -> order_ops
- shipping_issue -> shipping_ops
- payment_issue -> billing_ops
- refund_exchange -> returns_ops
- other -> human_support

```

- **Model**: `gemini-3-flash-preview`
- **temperature** : `0`
- **max_output_token** : `300`

## 3. 실제 응답 구조 

result_v1.json 참고
result_v2.json 참고


## 4. v1 -> v2 바뀐점

### 개요
v1 프롬프트는 일부 판단 기준이 명확하지 않아 모델이 항목을 추론에 의존해야 했다.  
v2에서는 ambiguity를 줄이기 위해 규칙을 추가하고, 일부 필드는 추론이 아니라 고정 매핑 방식으로 바꾸었다.

### 1. urgency 규칙 추가

#### v1
- urgency 판단 기준이 없음
- 따라서 모델이 문맥만 보고 urgency를 임의로 결정해야 함

#### v2
- intent별 urgency 기준을 일부 명시함
- `order_change` → `medium`
- `payment_issue` → `high`

#### 기대 효과
- urgency 값의 일관성 향상
- 동일한 유형의 문의에 대해 더 안정적인 출력 가능

### 2. route_to를 추론에서 매핑으로 변경

#### v1
- 모델이 intent를 보고 적절한 `route_to`를 추론해야 했음
- 즉, intent와 route_to의 관계가 프롬프트에 간접적으로만 드러남

#### v2
- intent와 route_to 관계를 더 명확하게 매핑 형태로 제시함
- `order_change` → `order_ops`
- `payment_issue` → `billing_ops`

#### 기대 효과
- 불필요한 추론 부담 감소
- route_to 오분류 가능성 감소
- structured output 안정성 향상

### 3. needs_clarification 기준 명시

#### v1
- 언제 `needs_clarification = true`로 처리해야 하는지 기준이 없음
- 모델이 애매한 상황을 일관되게 처리하기 어려움

#### v2
- clarification이 필요한 대표 상황을 명시함
- 환불인지 교환인지 불명확한 경우 → `true`
- 주문 문제인지 결제 문제인지 불명확한 경우 → `true`

#### 기대 효과
- 애매한 문의를 더 정확하게 감지 가능
- 잘못된 단정 분류를 줄이고 human review로 넘길 근거 강화

### 정리

v2의 핵심은 모델이 자유롭게 추론하던 부분을 줄이고,  
명시적인 규칙과 매핑을 추가해 출력의 일관성과 정확도를 높인 것이다.


## 5. 결과 비교 
[v1]
- 전체 건수: 12
- JSON 파싱 성공률: 8/12 (66.7%)
- exact match 개수: 6/12 (50.0%)
- 대표 실패 3건:
  1) ticket-05
     message: 배송지를 잘못 적었는데 아직 출고 전이면 수정하고 싶습니다.
     expected: {'intent': 'order_change', 'urgency': 'medium', 'needs_clarification': False, 'route_to': 'order_ops'}
     predicted: {'intent': 'order_change', 'urgency': 'high', 'needs_clarification': False, 'route_to': 'order_ops'}
     원인: urgency 필드 불일치
  2) ticket-06
     message: 상품은 아직 받지 못했는데 앱에는 배송 완료로 떠 있습니다. 확인해주세요.
     expected: {'intent': 'shipping_issue', 'urgency': 'high', 'needs_clarification': False, 'route_to': 'shipping_ops'}
     predicted: None
     error: 1 validation error for TicketOutput
  Invalid JSON: EOF while parsing a string at line 1 column 81 [type=json_invalid, input_value='{"intent":"shipping_issu...cation":false,"route_to', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/json_invalid
     원인: JSON 형식 오류 또는 출력 잘림으로 파싱 실패
  3) ticket-09
     message: 지난주에 요청드린 건이 아직도 처리되지 않은 것 같아요. 확인 좀 부탁드립니다.
     expected: {'intent': 'other', 'urgency': 'high', 'needs_clarification': True, 'route_to': 'human_support'}
     predicted: None
     error: 1 validation error for TicketOutput
  Invalid JSON: expected value at line 1 column 1 [type=json_invalid, input_value='Here is the JSON requested:', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/json_invalid
     원인: JSON 형식 오류 또는 출력 잘림으로 파싱 실패

[v2]
- 전체 건수: 12
- JSON 파싱 성공률: 12/12 (100.0%)
- exact match 개수: 9/12 (75.0%)
- 대표 실패 3건:
  1) ticket-08
     message: 포장은 안 뜯었는데 환불이 가능한지 먼저 알고 싶습니다.
     expected: {'intent': 'refund_exchange', 'urgency': 'medium', 'needs_clarification': False, 'route_to': 'returns_ops'}
     predicted: {'intent': 'refund_exchange', 'urgency': 'medium', 'needs_clarification': True, 'route_to': 'returns_ops'}
     원인: needs_clarification 필드 불일치
  2) ticket-09
     message: 지난주에 요청드린 건이 아직도 처리되지 않은 것 같아요. 확인 좀 부탁드립니다.
     expected: {'intent': 'other', 'urgency': 'high', 'needs_clarification': True, 'route_to': 'human_support'}
     predicted: {'intent': 'other', 'urgency': 'high', 'needs_clarification': False, 'route_to': 'human_support'}
     원인: needs_clarification 필드 불일치
  3) ticket-11
     message: 선물용으로 포장 가능한가요? 가능하면 이번 주 안에 받고 싶어요.
     expected: {'intent': 'other', 'urgency': 'medium', 'needs_clarification': True, 'route_to': 'human_support'}
     predicted: {'intent': 'other', 'urgency': 'medium', 'needs_clarification': False, 'route_to': 'human_support'}
     원인: needs_clarification 필드 불일치


[비교 요약]
- 파싱 성공률: v1 66.7% → v2 100.0%
- exact match: v1 6 → v2 9

## 6. 비용 및 시간을 단축하는 법 

v2처럼 판단 규칙을 명확히 해서 모델의 고민을 줄이고, 출력/프롬프트를 최소화하면 토큰과 추론 시간이 같이 줄어든다.