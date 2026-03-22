# 1주차 과제 (정연승): LLM 호출을 테스트하고 이해하기

## 1. 사용한 모델, SDK, 실행 환경
* **모델(Model)**: `gpt-4o`
* **SDK**: `openai` Python SDK (v1.51.2)
* **실행 환경**: Local Python 3.10 / macOS

---

## 2. 실제 요청 구조 설명
* **system 메시지**: 티켓 분류 전문가 페르소나를 부여하고, 각 필드(`intent`, `urgency`, `needs_clarification`, `route_to`)에 대한 구체적인 정의를 제공함. v2에서는 헷갈리기 쉬운 경계 사례에 대해 논리적 근거가 포함된 **Few-shot(예시)** 지침을 추가하여 모델의 판단 기준을 정교화함.
* **user 메시지**: `고객 메시지: {customer_message}` 형식으로 `dataset.jsonl`의 원본 메시지를 그대로 전달함.
* **model**: `gpt-4o`
* **temperature**: `0` (응답의 일관성 및 재현성을 확보하기 위해 최솟값으로 설정)
* **max_tokens**: `500`

---

## 3. 실제 응답 구조 설명
OpenAI의 **Structured Outputs (`beta.chat.completions.parse`)** 기능을 사용하여 Pydantic 모델로 정의된 규격에 맞는 JSON 응답을 수신함.

### JSON 본문 예시 (ticket-09)
```json
{
  "intent": "other",
  "urgency": "high",
  "needs_clarification": true,
  "route_to": "human_support"
}
```

### usage/token 정보 (1건 평균)
* **Prompt Tokens**: 약 720 tokens (v2 Few-shot 지침 포함 시)
* **Completion Tokens**: 약 35 tokens
* **Total Tokens**: 약 755 tokens

---

## 4. v1 -> v2에서 바꾼 점
* **설명(Rule) 기반에서 예시(Few-shot) 기반으로 전환**: 단순한 텍스트 규칙 추가 시 모델이 특정 단어에 과적합(Overfitting)되어 다른 문제를 틀리는 '두더지 잡기' 현상을 확인하고, 논리적 해석이 포함된 **Few-shot 4건**을 추가하여 모델의 판단 영점을 조절함.
* **판단 가이드라인 구체화**: 
    * `urgency`: "이전 요청 미처리로 인한 고객 불만 고조" 상황을 명시적으로 `high`로 분류하도록 지시함.
    * `needs_clarification`: 고객이 두 가지 옵션(교환/환불) 사이에서 결정하지 못한 '의사결정 보류' 상태를 `true`로 판단하도록 보완함.
    * `intent`: '선물 포장'과 같은 특수 요청을 `other`로 분류하도록 명시함.

---

## 5. 결과 비교

| 항목 | v1 결과 | v2 결과 |
| :--- | :---: | :---: |
| **JSON 파싱 성공률** | 100% | 100% |
| **Exact Match 개수** | 10 / 12 | **12 / 12** |

### 대표 실패 3건과 원인 분석 (v1 및 중간 과정 기준)
1.  **ticket-09 (v1 실패)**: "지난주 요청 미처리"라는 고객의 감정적 긴급도를 간과하고 `urgency: medium`으로 판단함. **원인**: 긴급도 판단 기준에 대한 구체적인 지침 부족.
2.  **ticket-12 (v1 실패)**: 교환과 환불 사이의 고민을 단순 절차 문의로 보아 `needs_clarification: false`로 출력함. **원인**: 상담원 개입이 필요한 '의사결정 보류' 상태에 대한 정의 부족.
3.  **ticket-11 (v2 중간 과정 실패)**: '선물 포장 가능 여부'를 일반적인 `order_change`로 오분류함. **원인**: 정규 옵션 변경이 아닌 특수 요청에 대한 `other` 분류 영점 조절 필요.