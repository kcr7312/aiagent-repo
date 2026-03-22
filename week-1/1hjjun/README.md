# 1주차 과제: LLM 호출을 테스트하고 이해하기

## 사용한 모델, SDK, 실행 환경

- 모델: gemini-2.5-flash
- SDK: google-genai (Python)
- 실행 환경: macOS / VS Code / Python 3.10.10 (가상환경 .venv 사용)

## 실제 요청 구조 설명

system 메시지: SystemMessageV2

```
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
```

user 메시지:

"주문한 러닝화가 아직 도착하지 않았어요. 배송이 어디까지 왔는지 확인하고 싶습니다."

실제 요청 구조:

```python
def classify_ticket(customer_text):
    # 최신 SDK 호출 방식
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config={
            "system_instruction": SYSTEM_PROMPT_V2,
            "temperature": 0.1,
            "response_mime_type": "application/json",
            "max_output_tokens": 500
        },
        contents=customer_text
    )
    return response.text
```

## 실제 응답 구조 설명

JSON 본문 예시:

```json
{
  "id": "ticket-12",
  "input": "사이즈가 안 맞아서 교환할지 환불할지 고민 중인데 어떤 절차로 진행하면 될까요?",
  "expected": {
    "intent": "refund_exchange",
    "urgency": "medium",
    "needs_clarification": true,
    "route_to": "returns_ops"
  },
  "predicted": {
    "intent": "refund_exchange",
    "urgency": "medium",
    "needs_clarification": true,
    "route_to": "returns_ops"
  },
  "is_match": true
}
```

usage/token 정보:

- Prompt Token: 약 250 ~ 300 tokens (System Prompt 포함)
- Candidates Token: 약 40 ~ 60 tokens
- Total Token: 약 350 tokens 내외 (티켓 1건당)

## v1 -> v2에서 바꾼 점

SystemMessageV1

```
당신은 고객 지원 티켓 분류 전문가입니다.
입력받은 고객 문의를 분석하여 반드시 아래의 JSON 형식으로만 답변하세요.
다른 설명은 절대 하지 마세요.

{
  "intent": "order_change | shipping_issue | payment_issue | refund_exchange | other",
  "urgency": "low | medium | high",
  "needs_clarification": true/false,
  "route_to": "order_ops | shipping_ops | billing_ops | returns_ops | human_support"
}
```

SystemMessageV2

```
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
```

1. 구조적 강제: v1에서 가끔 누락되던 route_to 필드를 필수 출력 JSON 구조 섹션을 통해 명확히 강제함.
2. 판단 기준 구체화: AI가 자의적으로 false라고 판단하던 needs_clarification 항목에 대해 '고민 중인 상황'과 '부차적 요청이 포함된 상황'은 반드시 true로 하라는 예외 조항을 추가함.
3. 긴급도 기준 보강: '지난주 요청 미처리'와 같은 고객의 감정적/시간적 맥락을 high로 분류하도록 세부 가이드 추가.
4. "가능한 지 알고 싶다" 는 문의는 결정한 것으로 판단한다는 문구 추가.

## 결과 비교

JSON 파싱 성공률: 100% (12/12) - response_mime_type: "application/json" 설정으로 파싱 에러 방지.
exact match 개수: 12개 (v1: 8개 -> v2: 12개)

대표 실패 사례:

<img width="1280" height="242" alt="image" src="https://github.com/user-attachments/assets/43cc23ba-458b-45ec-9c2e-897c1fd0ba4a" />

- ticket 11 : 부차적인 요청인 "선물 포장 요청" 이 메인 요청인 배송 문의가 명확하면 크게 상관하지 않는 판단을 내리고 있었다.
- ticket 12 : 교환 또는 환불을 문의하고 있어 returns 로의 판단이 맞을 수 있지만, 교환이나 환불을 결정하지 못했을 때는 명확성이 부족하다고 판단을 하겠금 바꿔주어야 했다.

<img width="600" height="300" alt="image" src="https://github.com/user-attachments/assets/2deefdb3-b9ae-47e5-960a-90b9daa6f6d4" />

- 사람은 저 문의사항을 보고 환불이 가능하다면 바로 환불처리를 하겠거니 하고 판단을 내릴 것인데, AI 는 아직 환불 진행 여부를 결정한 것은 아니라고 판단하고 있었다. 그래서 "가능한지 알고싶다" 는 것도 결정한 것 으로 확인한다는 문구를 추가해 주었다.

## 참고사항

[블로그 정리](https://play-devsecops.tistory.com/74)

