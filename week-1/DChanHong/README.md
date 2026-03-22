# 1주차 과제: 고객 문의 분류 LLM 호출 실험

## 1. 사용한 모델, SDK, 실행 환경

| 항목 | V1 | V2 (최종 채택) |
|------|-----|----------------|
| 모델 | `gemini-3-flash-preview` | `gemini-3.1-flash-lite-preview` |
| SDK | OpenAI Python SDK (`openai`) | 동일 |
| API Endpoint | Gemini OpenAI-compatible (`v1beta/openai/`) | 동일 |
| 실행 환경 | Python 3 + venv | 동일 |
| 주요 라이브러리 | `openai`, `pydantic`, `python-dotenv` | 동일 |

## 2. 실제 요청 구조

### `system` 메시지

V1과 V2 모두 시스템 프롬프트에 분류 기준(`intent`, `urgency`, `needs_clarification`, `route_to`)과 판단 규칙을 명시했습니다.
V2에서는 프롬프트 하단에 few-shot 예시 3건을 추가해 분류 패턴을 더 명확히 유도했습니다.

```
당신은 전자상거래 고객문의 분류 담당자입니다.
사용자가 입력한 고객 문의를 읽고, 반드시 아래 기준에 따라 분류하여 ...

분류 기준:
1. intent  - order_change / shipping_issue / payment_issue / refund_exchange / other
2. urgency - low / medium / high
3. needs_clarification - true / false
4. route_to - order_ops / shipping_ops / billing_ops / returns_ops / human_support

판단 규칙:
- 문의의 핵심 이슈를 기준으로 intent를 하나만 선택하세요.
- ...

[V2 추가] 예시:
### 예시 1
입력: "배송지를 변경하고 싶어요. 아직 출고 전인가요?"
응답: {"intent": "order_change", "urgency": "medium", ...}
### 예시 2 ...
### 예시 3 ...
```

### `user` 메시지

`customer.json`에서 읽은 고객 문의 텍스트를 그대로 전달합니다.

```
주문한 러닝화가 아직 도착하지 않았어요. 배송이 어디까지 왔는지 확인하고 싶습니다.
```

### `model` / `temperature` / `max_tokens`

| 파라미터 | V1 | V2 (최종) |
|----------|-----|-----------|
| `model` | `gemini-3-flash-preview` | `gemini-3.1-flash-lite-preview` |
| `temperature` | `0.2` | `0.2` |
| `top_p` | `0.95` | `0.95` |
| `max_tokens` | `2000` | `300` (override) |
| `reasoning_effort` | `low` | `low` |

- `temperature=0.2`: 분류 과제에서 결과 흔들림을 줄이기 위해 낮게 설정. Gemini 3 모델은 1.0 권장이나, 실험 결과 0.7에서 개선 없이 오히려 필드 정확도가 하락해 0.2를 유지했다.
- `max_tokens=300`: flash-lite 모델은 150에서 JSON이 잘리는 문제가 발생. 300으로 올려 안정적인 파싱을 확보했다.

### 응답 형식 강제

Pydantic 스키마 기반 `response_format`을 사용해 JSON 출력을 구조적으로 강제했습니다.

```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "inquiry_analysis",
        "schema": InquiryAnalysis.model_json_schema()
    }
}
```

## 3. 실제 응답 구조

### JSON 본문 예시

```json
{
  "intent": "shipping_issue",
  "urgency": "medium",
  "needs_clarification": false,
  "route_to": "shipping_ops"
}
```

### usage/token 정보

```json
{
  "prompt_tokens": 791,
  "completion_tokens": 33,
  "total_tokens": 824,
  "elapsed_ms": 1912.65
}
```

| 지표 | V1 (`gemini-3-flash`) | V2 (`flash-lite`, few-shot) |
|------|-----------------------|-----------------------------|
| 총 prompt tokens | 9,443 | 9,443 |
| 평균 prompt tokens | 786.92 | 786.92 |
| 평균 completion tokens | 32.5 | 40.75 |
| 평균 total tokens | 819.42 | 941.58 |

## 4. V1 → V2에서 바꾼 점


### 제미나이 프롬프트 모범사례를 읽어보며 , 시도해볼 프롬프트 개선사항 정리 후 실험

### 채택된 변경

| 변경 | 내용 | 효과 |
|------|------|------|
| Few-shot 예시 추가 | 배송지 변경, 중복 결제, 단순 인사 3건 추가 | `urgency` 판단 개선 (ticket-08, ticket-12 보정) |
| 모델 변경 | `gemini-3-flash-preview` → `gemini-3.1-flash-lite-preview` | exact match +1 개선, 비용 효율 향상 |
| `max_tokens` 조정 | `2000` → `300` | flash-lite 모델에서 안정적 파싱 확보하면서 불필요한 여유분 제거 |

### 시도했으나 채택하지 않은 변경

| 실험 | 결과 | 미채택 사유 |
|------|------|-------------|
| 프롬프트 축소 (Compact) | exact match 8/12 (66.7%) | 토큰은 줄었으나 `urgency` 정확도 크게 하락 |
| XML 태그 구조화 | exact match 9/12 (75.0%) | few-shot과 동일한 결과에 토큰만 증가 |
| 컨텍스트 먼저 배치 | exact match 9/12 (75.0%) | 필드 정확도 89.6%로 하락, `ticket-11` 오분류 |
| Temperature 0.7 | exact match 9/12 (75.0%) | 필드 정확도 89.6%로 하락, 이점 없음 |

## 5. 결과 비교

### JSON 파싱 성공률

| 버전 | 파싱 성공 | 성공률 |
|------|-----------|--------|
| V1 | 12/12 | **100%** |
| V2 | 12/12 | **100%** |

Pydantic `json_schema` 기반 `response_format`을 사용했기 때문에 V1/V2 모두 파싱 실패 없이 100% 성공했다. 단, V2에서 flash-lite 모델을 `max_tokens=150`으로 실행했을 때는 JSON이 중간에서 끊겨 파싱에 실패했으며, `max_tokens=300`으로 올려 해결했습니다.

### exact match 개수

| 버전 | exact match | 비율 | 필드 정확도 |
|------|-------------|------|-------------|
| V1 (baseline) | **9/12** | 75.0% | 45/48 (93.8%) |
| V2 (최종) | **10/12** | 83.3% | 45/48 (93.8%) |

### 필드별 정확도 비교

| 필드 | V1 | V2 (최종) |
|------|----|-----------|
| `intent` | 12/12 (100%) | 12/12 (100%) |
| `urgency` | 10/12 (83.3%) | 10/12 (83.3%) |
| `needs_clarification` | 11/12 (91.7%) | 11/12 (91.7%) |
| `route_to` | 12/12 (100%) | 12/12 (100%) |

### 대표 실패 건과 원인

#### 1. `ticket-09` — urgency 과소 판단

- 기대값: `urgency=high`
- 예측값: `urgency=medium`
- 원인: 장기 미처리 및 고객 불만 고조 상황을 `high`로 올리지 못했다. 명시적인 "결제 이상", "분실" 등의 키워드가 없으면 모델이 긴급도를 보수적으로 낮추는 경향이 있다.

#### 2. `ticket-12` — urgency 과소 판단 + needs_clarification 미탐지

- 기대값: `urgency=medium`, `needs_clarification=true`
- 예측값: `urgency=low`, `needs_clarification=false`
- 원인: 교환/환불 사이에서 고민 중인 절차 상담형 문의를 확정적 요청으로 과판단했다. "정보 문의/절차 상담"과 "즉시 처리 요청"을 구분하는 기준이 프롬프트에 더 필요하다.

#### 비용/시간 최적화 분석

V2에서 2건의 오답이 남아 있지만, 추가 개선보다는 비용 효율 최적화 관점에서 다음을 확인했습니다.
- 데이터 정확도 측명에서는 유의미하게 개선되자는 않았습니다.
- 모델 변경으로 `gemini-3-flash-preview` → `gemini-3.1-flash-lite-preview`로 전환 시 정확도를 유지하면서 더 저렴한 모델을 사용할 수 있습니다.
- `max_tokens`를 `2000`에서 `300`으로 줄여 불필요한 여유분을 제거했다. 실제 completion 토큰은 평균 40 이하이므로 300이면 충분합니다..
- `temperature=0.2`가 현재 분류 과제에서 가장 안정적이며, 더 높이면 오히려 정확도가 떨어졌습니다.

---
