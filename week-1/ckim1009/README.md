# 1주차 과제: LLM 호출 테스트

---

## 사용한 모델, SDK, 실행 환경

---

SDK: google-genai (Python)

실행 환경: Window / VS Code / Python 3.10.2

## 프롬프트v1 실험

### 파라미터 설정

`model` = 'gemini-2.5-flash-light'

`temperature` = 0

`max_tokens` = 200

- 실험을 재현가능하게 만들기 위해 여러 번 반복해도 동일한 출력이 나오도록 `temperature`를 0으로 설정. 
- `max_tokens`의 경우 출력 가능한 토큰 MAX값이 고정되어 있으므로 여유롭게 설정


### 프롬프트v1 구성

System prompt
- 역할부여
- 출력 json 구조 명시
- 분류 조건 정의

User prompt
- 고객문의사항 전달

---

**프롬프트v1**

```
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
```


### 프롬프트v1 실험 결과

```
Parsing 성공 횟수: 12/12
Schema 규칙 준수: 12/12
일치 정확도: 7/12

오답케이스
ticket-04: [urgency] 정답: medium | 출력결과: low
ticket-08: [urgency] 정답: medium | 출력결과: low
ticket-09: [urgency] 정답: high | 출력결과: medium
ticket-11: [urgency] 정답: medium | 출력결과: low
ticket-12:
    - [urgency] 정답: medium | 출력결과: low
    - [needs_clarification] 정답: True | 출력결과: False
```

## 프롬프트v2 실험

### 파라미터 설정

`model` = 'gemini-2.5-flash'

`temperature` = 0

`max_tokens` = 500


### 프롬프트v2 구성

System prompt
- 역할부여
- 출력 json 구조 명시
- 분류 조건 정의

User prompt
- 고객문의사항 전달

---

**프롬프트v2**

```
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
```

### 프롬프트v2 실험 결과

```
Parsing 성공 횟수: 12/12
Schema 규칙 준수: 12/12
일치 정확도: 8/12

오답 케이스
ticket-08: [urgency] 정답: medium | 출력결과: low
ticket-09: [urgency] 정답: high | 출력결과: medium
ticket-11: [urgency] 정답: medium | 출력결과: low
ticket-12: [needs_clarification] 정답: true | 출력결과: false
```


## 실험 분석

- 프롬프트의 LLM 출력 결과가 모두 json 형태로 출력됨
- `pydantic` 분석 결과, LLM 출력 결과가 모두 사전 정의된 json 구조에 만족함
- `urgency`와 `needs_clarification`에서 오답 출력하는 케이스 확인, 프롬프트v1에서 `urgency`와 `needs_clarification`의 설명을 수정하여 프롬프트 v2 작성
- 프롬프트v1, 프롬프트v2 실험 시 `model`과 `max_tokens` 변경
- `urgency`와 `needs_clarification`의 분류 조건이 불명확한 것으로 확인됨, 조금 더 구체적인 조건과 few-shot과 같은 예제 설명이 필요한 것으로 판단됨