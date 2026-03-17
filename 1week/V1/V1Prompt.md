# V1 Prompt / Setting 정리

## 목적

V1은 고객 문의를 구조화된 JSON으로 분류하는 첫 번째 기준 버전이다.  
이 버전으로 결과 데이터를 생성하고, 결과 분석 후 V2 개선 방향을 정한다.

## V1 실험 목표

- 고객 문의를 `intent`, `urgency`, `needs_clarification`, `route_to`로 분류한다.
- Gemini OpenAI 호환 API를 사용해 구조화된 JSON 응답을 받는다.
- 실행 시 사용한 프롬프트와 호출 옵션을 함께 저장해 이후 결과 비교가 가능하도록 한다.

## 모델 설정

- `base_url`: `https://generativelanguage.googleapis.com/v1beta/openai/`
- `model_name`: `gemini-3-flash-preview`
- 선택 이유:
  - 빠른 응답 속도
  - 구조화 출력 실험에 적합
  - 초기 분류 실험용으로 비용 및 반복 실행 부담이 상대적으로 적음

## 생성 옵션 기본값

```python
{
    "temperature": 0.2,
    "top_p": 0.95,
    "max_tokens": 512,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "seed": None,
}
```

### 옵션 해석

- `temperature=0.2`
  - 분류 결과의 흔들림을 줄이고 보수적으로 응답하도록 설정
- `top_p=0.95`
  - 후보 다양성은 일부 허용하되 과도한 변동은 줄이는 설정
- `max_tokens=512`
  - JSON 응답이 잘리지 않도록 충분한 길이 확보
- `presence_penalty=0.0`
  - 분류 태스크에서는 영향이 작아 기본값 유지
- `frequency_penalty=0.0`
  - 반복 억제보다 분류 안정성이 중요하므로 기본값 유지
- `seed=None`
  - 현재는 완전 고정 실험 전 단계로 두고, 필요 시 V2에서 재현성 비교용으로 고정값 사용 검토

## 추론 옵션

- `reasoning_effort`: `low`
- 선택 이유:
  - 현재 태스크는 긴 생성보다 짧은 분류가 중심
  - 속도와 비용을 함께 고려한 기본 설정

## 시스템 프롬프트

현재 V1 시스템 프롬프트는 다음 기준을 명시한다.

- `intent`
  - `order_change`: 주문 수정, 취소, 주소 변경, 옵션 변경
  - `shipping_issue`: 출고, 배송 지연, 배송 누락, 배송 완료 오표시
  - `payment_issue`: 결제 실패, 중복 결제, 청구 이상
  - `refund_exchange`: 반품, 환불, 교환, 불량 접수
  - `other`: 위 카테고리로 단정하기 어렵거나 맥락이 부족한 경우
- `urgency`
  - `low`: 일반 문의, 즉시 장애 아님
  - `medium`: 처리가 필요하지만 긴급 장애 또는 금전 리스크는 아님
  - `high`: 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인이 시급함
- `needs_clarification`
  - `true`: 현재 텍스트만으로 intent 또는 처리 방향을 단정하기 어려움
  - `false`: 현재 정보만으로 1차 분류 가능
- `route_to`
  - `order_ops`: 주문/수정 담당
  - `shipping_ops`: 배송 담당
  - `billing_ops`: 결제/청구 담당
  - `returns_ops`: 환불/교환 담당
  - `human_support`: 맥락 부족, 다부서 이슈, 에스컬레이션 필요

### 판단 규칙

- 문의의 핵심 이슈를 기준으로 `intent`를 하나만 선택한다.
- 문의가 모호하거나 복합적이면 `intent=other`, `needs_clarification=true`를 우선 고려한다.
- `route_to`는 `intent`와 `needs_clarification` 판단과 일관되게 선택한다.
- 응답은 반드시 JSON 스키마 허용값만 사용한다.

## 스키마 제약

V1은 Pydantic 기반 JSON Schema를 사용해 출력 형식을 강하게 제한한다.

- 출력 필드:
  - `intent`
  - `urgency`
  - `needs_clarification`
  - `route_to`
- Enum으로 허용값 제한
- `ConfigDict(extra="forbid")` 적용
  - 정의되지 않은 추가 필드는 허용하지 않음

### 스키마의 역할

- 모델이 자유 서술하지 않고 정해진 필드만 반환하도록 제한
- 결과 저장 및 비교를 쉽게 만듦
- 단, 분류 기준 자체는 스키마보다 시스템 프롬프트의 영향을 더 크게 받음

## 결과 저장 방식

실행 시 결과는 `json/result/{날짜-시간}/` 아래에 저장한다.

- `model-config.json`
  - 모델명
  - base URL
  - generation 기본값
  - system prompt
  - response format
  - reasoning effort
- `analysis-results.json`
  - 각 고객 문의별 분석 결과

## V1 결과 분석 포인트

V1 결과를 본 뒤 아래 항목을 중심으로 평가한다.

- `intent` 분류 정확도
- `urgency` 판단 일관성
- `needs_clarification`이 애매한 문장에서 적절히 작동하는지
- `route_to`가 `intent`와 일관되게 매핑되는지
- JSON 형식이 안정적으로 유지되는지
- 애매한 문의에서 `other` 처리가 적절한지

## V2에서 검토할 개선 후보
- `최적 모델` 비교 (비용 고려)
- `seed` 고정으로 재현성 비교
- `temperature`를 더 낮춘 버전 비교
- 애매한 케이스용 프롬프트 규칙 추가
- few-shot 예시 포함 여부 비교
- 모델 변경 시 정확도/속도/JSON 준수율 비교
