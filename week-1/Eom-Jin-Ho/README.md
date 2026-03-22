# 1주차 과제: LLM 호출을 테스트하고 이해하기

---

## 1. 사용한 모델, SDK, 실행 환경

- Model: `gpt-5.4-mini`
- SDK: `openai` (Python)
- Language: Python 3.13.2
- Library:
  - openai
  - pydantic
  - python-dotenv
- 실행 환경:
  - Windows (VSCode)
  - `.env`를 통한 API Key 관리

---

## 2. 실제 요청 구조 설명

LLM 호출 시 system 메시지와 user 메시지를 분리하여 구성하였다.

- system 메시지: 모델의 역할, 출력 형식(JSON), 분류 기준 정의
- user 메시지: 실제 고객 문의 데이터 전달

이를 통해 모델이 항상 동일한 기준으로 분류하도록 유도하였다.

---

## 3. system 메시지

너는 고객 문의 티켓을 분류하는 AI다.

반드시 아래 규칙을 모두 지켜라.

1. 반드시 JSON 객체 하나만 출력한다.
2. JSON 바깥의 설명, 문장, 코드블록, 마크다운을 절대 출력하지 않는다.
3. 모든 필드는 반드시 아래 허용값 중 하나만 사용한다.

intent:
- order_change : 주문 수정, 취소, 주소 변경, 옵션 변경
- shipping_issue : 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- payment_issue : 결제 실패, 중복 결제, 청구 이상
- refund_exchange : 반품, 환불, 교환, 불량 접수
- other : 위로 단정하기 어렵거나 맥락이 부족한 경우

urgency:
- low : 일반 문의, 즉시 장애 아님
- medium : 처리가 필요하지만 긴급 장애/금전 리스크는 아님, 환불/교환 요청 및 절차 문의, 일반 문의라도 일정 조건이나 빠른 처리 요구가 붙은 건
- high : 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인이 시급한 건, 이미 이전에 요청했지만 아직 처리되지 않은 건, 반복 문의 또는 지연이 누적된 건

needs_clarification:
- true : 현재 텍스트만으로 intent 또는 처리 방향을 단정하기 어려운 경우, 교환할지 환불할지 아직 결정하지 못한 경우, 고객이 원하는 처리 방향이 완전히 정해지지 않은 경우, 주문/결제/배송/환불 중 어느 범주로 봐야 할지 애매한 부가 요청이나 조건 문의인 경우
- false : 현재 정보만으로 1차 분류 가능

추가 규칙:
- 환불/교환의 가능 여부, 절차, 조건을 묻는 문의는 refund_exchange로 분류하고 needs_clarification은 false로 본다.
- 단, 교환할지 환불할지 아직 결정하지 못한 경우는 refund_exchange로 분류하되 needs_clarification은 true로 본다.
- 포장 가능 여부, 선물 포장, 기타 부가 서비스 요청처럼 기본 분류에 바로 들어가지 않는 문의는 other로 분류하고 needs_clarification을 true로 본다.
- 이미 이전에 요청했지만 아직 처리되지 않았다고 말하는 경우는 urgency를 high로 본다.

route_to:
- order_ops
- shipping_ops
- billing_ops
- returns_ops
- human_support

---

## 4. user 메시지

고객 문의: {customer_message}

---

## 5. 모델 파라미터 설정

model = "gpt-5.4-mini"
temperature = 0
max_output_tokens = 100

### 설정 이유

- temperature = 0  
  → 동일 입력에 대해 항상 동일한 결과를 얻기 위해 설정

- max_output_tokens = 100  
  → JSON 형태의 짧은 응답만 필요하므로 불필요한 출력 방지

---

## 6. 실제 응답 구조 설명

모델은 반드시 아래 JSON 구조로 응답하도록 설계하였다.

{
  "intent": "string",
  "urgency": "string",
  "needs_clarification": true/false,
  "route_to": "string"
}

---

## 7. JSON 응답 예시

{
  "intent": "shipping_issue",
  "urgency": "medium",
  "needs_clarification": false,
  "route_to": "shipping_ops"
}

---

## 8. usage / token 정보

- 총 input token : 7464
- 총 output token : 333
- 총 token : 7797
- 전체 12건 기준 평균 input koken  : 622
- 전체 12건 기준 평균 output koken  : 27.75
- 전체 평균 token : 649.75

response.usage 기반 측정 / 모델별로 input, ouput token은 동일

### 비용 계산
OPenAI 공식 가격표 기준  
 gpt-5.4-mini: 입력  $0.25 / 100만 토큰,  출력 $2.00 / 100만 토큰 
 gpt-5.4-nano: 입력  $0.05 / 100만 토큰,  출력 $0.40 / 100만 토큰

#### gpt-5.4-mini
총 input 비용(USD): 0.001866
총 output 비용(USD): 0.000666
총 비용(USD): 0.002532

#### gpt-5.4-nano
총 input 비용(USD): 0.000373
총 output 비용(USD): 0.000133
총 비용(USD): 0.000506

 


---

## 9. v1 → v2에서 바꾼 점

v1은 스키마와 허용값 정의 중심의 기본 프롬프트였다.

v2에서는 다음과 같은 판단 기준을 보강하였다.

- urgency 기준 구체화  
  → 이전 요청 미처리 → high

- needs_clarification 기준 보강  
  → 교환/환불 선택 미정 → true  
  → 부가 서비스 문의 → true

- refund_exchange 관련 규칙 추가  
  → 가능 여부/절차 문의 → false  
  → 선택 미정 → true

즉, v2는 스키마 유지 + 판단 기준 강화 전략으로 설계하였다.

---

## 10. 결과 비교 (JSON 파싱, 검증, exact match 성공률)
v1
- 파싱 : 12/12
- 검증 : 12/12
- exact Match : 8/12

v2
- 파싱 : 12/12
- 검증 : 12/12
- exact Match : 12/12

---



## 11. 대표 실패 사례 및 원인 (v1 기준)

### 실패 1
- 문제: urgency 판단 오류
- 원인: "장기간 미처리" 기준이 명확하지 않음

### 실패 2
- 문제: needs_clarification 판단 오류
- 원인: 부가 서비스 문의에 대한 기준 부족

### 실패 3
- 문제: refund_exchange 처리 오류
- 원인: 가능 여부 문의 vs 선택 미정 구분 부족

---

## 12. 최적화 가능성

### 비용 최적화
- system prompt 길이를 축소해 볼 수 있을것 같다. (반복 문장 제거 등)
- 모델을 gpt-5.4-mini -> gpt-5.4-nano로 변경해도 정답은 맞았다.



---

# 최종 결론

본 과제를 통해 LLM을 활용한 분류 작업에서

- 스키마 정의
- 프롬프트 설계
- 판단 기준 구체화

결과 정확도에 큰 영향을 미친다는 것을 확인하였다.

특히 v2에서는 경계 사례를 명확히 정의함으로써 exact match 성능을 크게 개선할 수 있었다.

---

## 한 줄 요약

👉 LLM 성능은 모델보다 프롬프트 설계가 더 크게 좌우된다
