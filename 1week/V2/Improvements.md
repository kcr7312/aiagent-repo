# V2 Improvements

이 문서는 `V2`에서 시도한 개선점과 각 실험 결과를 누적 기록하기 위한 문서이다.
이후 개선 실험도 같은 형식으로 계속 추가한다.
평가의 최우선 기준은 `dataset.pretty.json`의 `expected_output`과 얼마나 일치하는지이며, `intent=other`, `route_to=human_support` 건수는 보조 관찰 지표로만 해석한다.

## 1. Few-shot Prompting 추가

### 개선 목적

- 프롬프트에 예시 데이터를 넣어 모델이 분류 패턴과 JSON 응답 형식을 더 안정적으로 따르도록 유도한다.
- 특히 `urgency`와 `needs_clarification` 같은 경계 판단이 개선되는지 확인한다.

### 적용 내용

- 수정 파일: `1week/V2/prompts/inquiry_prompt.py`
- 변경 사항: 프롬프트 하단에 few-shot 예시 3건 추가

#### 추가한 예시

- 예시 1: 배송지 변경 문의 -> `order_change`, `medium`, `false`, `order_ops`
- 예시 2: 중복 결제 문의 -> `payment_issue`, `high`, `false`, `billing_ops`
- 예시 3: 단순 인사 -> `other`, `low`, `true`, `human_support`

### 평가 기준

- 정답 데이터: `1week/dataset.pretty.json`
- 실험 결과 데이터: `1week/V2/json/result/20260319-202059-Few-shot/analysis-results.json`
- 비교 기준: `1week/V1/V1PromptResult.md`

### 결과 요약

- 완전 일치(4개 필드 모두 일치): `9/12` = `75.0%`
- 필드 단위 정확도: `45/48` = `93.8%`

#### 필드별 정확도

- `intent`: `12/12` = `100%`
- `urgency`: `11/12` = `91.7%`
- `needs_clarification`: `10/12` = `83.3%`
- `route_to`: `12/12` = `100%`

### 토큰 사용량 분석

- 총 prompt tokens: `9,443`
- 평균 prompt tokens: `786.92`
- 총 completion tokens: `390`
- 평균 completion tokens: `32.5`
- 총 tokens: `9,833`

### 핵심 지표 분석

- 정답 기준 `needs_clarification=true` 필요 건수: `4건`
- 예측 `needs_clarification=true`: `2건`
- 정답 기준 `intent=other` 필요 건수: `3건`
- 예측 `intent=other`: `3건`
- 정답 기준 `route_to=human_support` 필요 건수: `3건`
- 예측 `route_to=human_support`: `3건`

### V1 결과와 비교

- 완전 일치율: `75.0% -> 75.0%`로 동일
- 필드 정확도: `91.7% -> 93.8%`로 `+2.1%p` 개선
- `urgency`: `75.0% -> 91.7%`로 개선
- `needs_clarification`: `91.7% -> 83.3%`로 하락
- `intent`, `route_to`: 모두 `100%` 유지
- 평균 prompt tokens: `612.92 -> 786.92`로 증가
- 총 tokens: `9,438 -> 9,833`으로 증가

### 세부 분석

#### 개선된 항목

- `ticket-08`: `urgency=low` -> `urgency=medium`으로 개선
- `ticket-12`: `urgency=low` -> `urgency=medium`으로 개선

#### 여전히 오답인 항목

- `ticket-09`: 기대값 `urgency=high`, 예측값 `urgency=medium`
- `ticket-12`: 기대값 `needs_clarification=true`, 예측값 `needs_clarification=false`

#### 새롭게 악화된 항목

- `ticket-11`: 기대값 `needs_clarification=true`, 예측값 `needs_clarification=false`

### 해석

- few-shot 예시 추가는 `urgency` 판단 보정에는 효과가 있었다.
- 반면 모델이 애매한 상담형 문의를 더 쉽게 확정적으로 해석하면서 `needs_clarification` 성능은 하락했다.
- `intent=other`, `route_to=human_support` 건수는 정답과 동일했지만, 이것만으로 성능 개선 여부를 판단할 수는 없다.
- 즉, 현재 few-shot은 `urgency`는 개선했지만 `needs_clarification`에서 기대값 일치도가 낮아진 실험이다.

### 결론

- exact match는 유지됐고 필드 정확도는 소폭 개선되었지만, 토큰 사용량이 늘었고 `needs_clarification` 기대값 일치도는 오히려 낮아졌다.

### 다음 개선 방향

- `needs_clarification=true`가 되어야 하는 경계 사례 예시를 추가한다.
- `ticket-11`, `ticket-12`와 유사한 절차 상담형 문의를 예시에 포함한다.
- "정보 문의/절차 상담"과 "즉시 처리 요청"의 구분 기준을 프롬프트 규칙에 더 명확히 적는다.

## 2. 불필요한 프롬프트 축소

### 개선 목적

- `pydantic`의 `json_schema`가 형식과 허용값을 강제하므로, 프롬프트에서 중복되는 설명과 예시를 줄여 prompt token 사용량을 낮춘다.
- 토큰 절감이 실제 정확도와 `expected_output` 일치도에 어떤 영향을 주는지 확인한다.

### 적용 내용

- 수정 파일: `1week/V2/prompts/inquiry_prompt.py`
- 변경 사항:
- 출력 형식 강제 문구와 few-shot 예시 제거
- 중복 설명을 줄이고 핵심 분류 규칙만 남긴 압축 프롬프트로 변경

### 평가 기준

- 정답 데이터: `1week/dataset.pretty.json`
- 실험 결과 데이터: `1week/V2/json/result/20260319-203207-Compact-prompt/analysis-results.json`
- 비교 기준:
- 베이스라인 `1week/V2/V1PromptResult.md`
- 1차 개선 `1week/V2/json/result/20260319-202059-Few-shot`

### 결과 요약

- 완전 일치(4개 필드 모두 일치): `8/12` = `66.7%`
- 필드 단위 정확도: `43/48` = `89.6%`

#### 필드별 정확도

- `intent`: `12/12` = `100%`
- `urgency`: `8/12` = `66.7%`
- `needs_clarification`: `11/12` = `91.7%`
- `route_to`: `12/12` = `100%`

### 토큰 사용량 분석

- 총 prompt tokens: `5,147`
- 평균 prompt tokens: `428.92`
- 총 completion tokens: `358`
- 평균 completion tokens: `29.83`
- 총 tokens: `7,829`

### 핵심 지표 분석

- 정답 기준 `needs_clarification=true` 필요 건수: `4건`
- 예측 `needs_clarification=true`: `5건`
- 정답 기준 `intent=other` 필요 건수: `3건`
- 예측 `intent=other`: `3건`
- 정답 기준 `route_to=human_support` 필요 건수: `3건`
- 예측 `route_to=human_support`: `3건`

### 이전 결과와 비교

- 베이스라인 대비 완전 일치율: `75.0% -> 66.7%`로 하락
- 베이스라인 대비 필드 정확도: `93.8% -> 89.6%`로 하락
- 1차 개선 대비 완전 일치율: `75.0% -> 66.7%`로 하락
- 1차 개선 대비 필드 정확도: `93.8% -> 89.6%`로 하락
- 베이스라인 대비 평균 prompt tokens: `612.92 -> 428.92`로 감소
- 1차 개선 대비 평균 prompt tokens: `786.92 -> 428.92`로 크게 감소
- 베이스라인 대비 총 tokens: `9,438 -> 7,829`로 감소
- 1차 개선 대비 총 tokens: `9,833 -> 7,829`로 감소

### 세부 분석

#### 악화된 항목

- `ticket-08`: 기대값 `urgency=medium`, `needs_clarification=false` / 예측값 `urgency=low`, `needs_clarification=true`
- `ticket-09`: 기대값 `urgency=high` / 예측값 `urgency=medium`
- `ticket-11`: 기대값 `urgency=medium` / 예측값 `urgency=low`
- `ticket-12`: 기대값 `urgency=medium` / 예측값 `urgency=low`

#### 유지된 항목

- `intent=other` 예측 건수는 `3건`으로 그대로였다.
- `route_to=human_support` 예측 건수도 `3건`으로 그대로였다.

### 해석

- 프롬프트 축소는 prompt token 절감에는 확실히 효과가 있었다.
- 그러나 `urgency` 판단이 전반적으로 보수적으로 낮아졌고, `needs_clarification=true`도 필요 이상으로 더 많이 출력되었다.
- `intent=other`, `route_to=human_support` 건수는 정답과 동일했지만, 더 중요한 exact match와 필드 정확도는 모두 하락했다.
- 즉, 이번 실험은 비용 절감은 성공했지만 `expected_output` 일치도는 명확히 악화된 실험이다.

### 결론

- 토큰 절감 효과 자체는 유의미합니다.
- 하지만 정확도와 핵심 운영 지표가 더 나빠졌기 때문에 실험 결과는 실패에 가깝습니다.
- 특히 `expected_output` 기준 exact match와 필드 정확도가 모두 하락했기 때문에 채택하기 어렵습니다.

### 다음 개선 방향

- 프롬프트를 다시 길게 늘리기보다, 경계 사례를 잡는 짧은 규칙만 일부 복원한다.
- `ticket-08` 같은 환불 가능 여부 문의는 `refund_exchange`로 보되 `needs_clarification`을 과도하게 켜지 않도록 기준을 분명히 적는다.
- `ticket-11`은 `other/human_support`로 가더라도 `urgency`를 `low`로 내리지 않도록 보완 규칙을 추가한다.
- `ticket-12` 같은 절차 상담형 문의는 `needs_clarification=true`를 유지하되 `urgency`는 `medium`으로 판단하도록 규칙을 보강한다.

## 3. XML 태그 구조화

### 개선 목적

- same few-shot 내용을 유지한 채 섹션 구분자만 XML 스타일 태그로 명확히 나눈다.
- 모델이 역할, 기준, 규칙, 예시의 경계를 더 잘 이해해서 정확도가 좋아지는지 확인한다.

### 적용 내용

- 수정 파일: `1week/V2/prompts/inquiry_prompt.py`
- 변경 사항:
- `role`, `instruction`, `criteria`, `rules`, `examples`를 XML 태그로 구분
- few-shot 예시 3건은 그대로 유지

### 평가 기준

- 정답 데이터: `1week/dataset.pretty.json`
- 실험 결과 데이터: `1week/V2/json/result/20260319-205143-XML-tags/analysis-results.json`
- 비교 기준:
- 베이스라인 `1week/V2/V1PromptResult.md`
- 1차 개선 `1week/V2/json/result/20260319-202059-Few-shot`

### 결과 요약

- 완전 일치(4개 필드 모두 일치): `9/12` = `75.0%`
- 필드 단위 정확도: `45/48` = `93.8%`

#### 필드별 정확도

- `intent`: `12/12` = `100%`
- `urgency`: `11/12` = `91.7%`
- `needs_clarification`: `10/12` = `83.3%`
- `route_to`: `12/12` = `100%`

### 토큰 사용량 분석

- 총 prompt tokens: `10,103`
- 평균 prompt tokens: `841.92`
- 총 completion tokens: `390`
- 평균 completion tokens: `32.5`
- 총 tokens: `11,073`

### 핵심 지표 분석

- 정답 기준 `needs_clarification=true` 필요 건수: `4건`
- 예측 `needs_clarification=true`: `2건`
- 정답 기준 `intent=other` 필요 건수: `3건`
- 예측 `intent=other`: `3건`
- 정답 기준 `route_to=human_support` 필요 건수: `3건`
- 예측 `route_to=human_support`: `3건`

### 이전 결과와 비교

- 베이스라인 대비 완전 일치율: `75.0% -> 75.0%`로 동일
- 베이스라인 대비 필드 정확도: `93.8% -> 93.8%`로 동일
- 1차 개선 대비 완전 일치율: `75.0% -> 75.0%`로 동일
- 1차 개선 대비 필드 정확도: `93.8% -> 93.8%`로 동일
- 베이스라인 대비 평균 prompt tokens: `612.92 -> 841.92`로 증가
- 1차 개선 대비 평균 prompt tokens: `786.92 -> 841.92`로 증가

### 해석

- few-shot 프롬프트와 결과는 사실상 동일했다.
- `needs_clarification`, `intent`, `route_to`의 기대값 일치 패턴도 few-shot과 사실상 동일했다.
- 정확도 개선 없이 토큰만 더 늘어났다.
- 따라서 XML 태그 구조화는 현재 과제 기준으로 실익이 없다.

### 결론

- 구조를 더 명확히 나누는 효과보다는 프롬프트 길이 증가 영향이 더 컸다.
- 채택하지 않는 것이 맞다.

### 사용한 XML 프롬프트

```text
<role>
당신은 전자상거래 고객문의 분류 담당자입니다.
</role>

<instruction>
사용자가 입력한 고객 문의를 읽고, 반드시 아래 기준에 따라 분류하여 정해진 JSON 스키마에 맞게만 응답하세요.
추가 설명, 자연어 문장, 마크다운 없이 JSON만 반환해야 합니다.
</instruction>

<criteria>
<intent>
- order_change: 주문 수정, 취소, 주소 변경, 옵션 변경
- shipping_issue: 출고, 배송 지연, 배송 누락, 배송 완료 오표시
- payment_issue: 결제 실패, 중복 결제, 청구 이상
- refund_exchange: 반품, 환불, 교환, 불량 접수
- other: 위 카테고리로 단정하기 어렵거나 맥락이 부족한 경우
</intent>

<urgency>
- low: 일반 문의, 즉시 장애 아님
- medium: 처리가 필요하지만 긴급 장애 또는 금전 리스크는 아님
- high: 결제 이상, 분실/오배송, 고객 불만 고조, 수동 확인이 시급함
</urgency>

<needs_clarification>
- true: 현재 텍스트만으로 intent 또는 처리 방향을 단정하기 어려움
- false: 현재 정보만으로 1차 분류 가능함
</needs_clarification>

<route_to>
- order_ops: 주문/수정 담당
- shipping_ops: 배송 담당
- billing_ops: 결제/청구 담당
- returns_ops: 환불/교환 담당
- human_support: 맥락 부족, 다부서 이슈, 에스컬레이션 필요
</route_to>
</criteria>

<rules>
- 문의의 핵심 이슈를 기준으로 intent를 하나만 선택하세요.
- 문의가 모호하거나 복합적이어서 하나의 intent 또는 처리 부서를 확정하기 어렵다면 intent는 other, needs_clarification은 true로 설정하세요.
- 결제 이상, 중복 결제, 청구 문제는 payment_issue 및 billing_ops를 우선 고려하세요.
- 배송 지연, 배송 누락, 배송 완료 오표시 등 배송 상태 문제는 shipping_issue 및 shipping_ops를 우선 고려하세요.
- 주문 변경, 옵션 변경, 주소 변경, 취소 요청은 order_change 및 order_ops를 우선 고려하세요.
- 환불, 반품, 교환, 불량 접수는 refund_exchange 및 returns_ops를 우선 고려하세요.
- 맥락 부족, 다부서 이슈, 에스컬레이션 필요 상황은 human_support로 라우팅하세요.
- route_to는 intent 및 needs_clarification 판단과 일관되게 선택하세요.
- 반드시 제공된 스키마의 허용값만 사용하세요.
</rules>

<examples>
<example>
입력: "배송지를 변경하고 싶어요. 아직 출고 전인가요?"
응답: {"intent": "order_change", "urgency": "medium", "needs_clarification": false, "route_to": "order_ops"}
</example>

<example>
입력: "결제가 두 번 됐어요. 확인 부탁드립니다."
응답: {"intent": "payment_issue", "urgency": "high", "needs_clarification": false, "route_to": "billing_ops"}
</example>

<example>
입력: "안녕하세요"
응답: {"intent": "other", "urgency": "low", "needs_clarification": true, "route_to": "human_support"}
</example>
</examples>
```

## 5. 컨텍스트 먼저, 지시 나중에

### 개선 목적

- 카테고리 정의와 예시를 먼저 보여주고, 마지막에 판단 규칙과 출력 지시를 배치한다.
- 모델이 먼저 의미를 이해한 뒤 지시를 따르는 구조가 더 안정적인지 확인한다.

### 적용 내용

- 수정 파일: `1week/V2/prompts/inquiry_prompt.py`
- 변경 사항:
- 분류 기준과 few-shot 예시를 프롬프트 상단에 배치
- 판단 규칙과 출력 지시는 프롬프트 하단으로 이동

### 평가 기준

- 정답 데이터: `1week/dataset.pretty.json`
- 실험 결과 데이터: `1week/V2/json/result/20260319-205236-Context-first/analysis-results.json`
- 비교 기준:
- 베이스라인 `1week/V2/V1PromptResult.md`
- 1차 개선 `1week/V2/json/result/20260319-202059-Few-shot`

### 결과 요약

- 완전 일치(4개 필드 모두 일치): `9/12` = `75.0%`
- 필드 단위 정확도: `43/48` = `89.6%`

#### 필드별 정확도

- `intent`: `11/12` = `91.7%`
- `urgency`: `11/12` = `91.7%`
- `needs_clarification`: `9/12` = `75.0%`
- `route_to`: `11/12` = `91.7%`

### 토큰 사용량 분석

- 총 prompt tokens: `9,275`
- 평균 prompt tokens: `772.92`
- 총 completion tokens: `392`
- 평균 completion tokens: `32.67`
- 총 tokens: `9,667`

### 핵심 지표 분석

- 정답 기준 `needs_clarification=true` 필요 건수: `4건`
- 예측 `needs_clarification=true`: `2건`
- 정답 기준 `intent=other` 필요 건수: `3건`
- 예측 `intent=other`: `2건`
- 정답 기준 `route_to=human_support` 필요 건수: `3건`
- 예측 `route_to=human_support`: `2건`

### 이전 결과와 비교

- 베이스라인 대비 완전 일치율: `75.0% -> 75.0%`로 동일
- 베이스라인 대비 필드 정확도: `93.8% -> 89.6%`로 하락
- 1차 개선 대비 완전 일치율: `75.0% -> 75.0%`로 동일
- 1차 개선 대비 필드 정확도: `93.8% -> 89.6%`로 하락
- 베이스라인 대비 평균 prompt tokens: `612.92 -> 772.92`로 증가
- 1차 개선 대비 평균 prompt tokens: `786.92 -> 772.92`로 소폭 감소

### 해석

- 겉으로는 `intent=other`, `route_to=human_support`가 줄어든 것처럼 보였다.
- 하지만 이는 `ticket-11`을 정답인 `other/human_support`가 아닌 `order_change/order_ops`로 잘못 분류해서 생긴 감소다.
- `needs_clarification`도 필요한 것보다 덜 나와서 품질은 오히려 하락했다.
- 따라서 보조 지표 숫자는 줄었어도 `expected_output` 일치도 기준으로는 악화된 실험이다.

### 결론

- 순서 변경만으로는 의미 있는 개선이 없었다.
- 수치상 일부 감소가 보여도 정답 불일치에서 나온 착시이므로 채택하지 않는다.

## 6. Temperature 0.7

### 개선 목적

- few-shot 프롬프트는 유지한 채 `temperature`만 높여서 Gemini 권장값 방향으로 이동했을 때 분류 품질이 좋아지는지 확인한다.
- 낮은 온도에서의 과도한 보수성을 줄일 수 있는지 본다.

### 적용 내용

- 수정 파일: `1week/V2/services/gemini_service.py`
- 실행 방식: 코드 기본값은 유지하고 실행 시 `temperature=0.7` 오버라이드
- 프롬프트는 1차 개선 few-shot 버전을 그대로 사용

### 평가 기준

- 정답 데이터: `1week/dataset.pretty.json`
- 실험 결과 데이터: `1week/V2/json/result/20260319-205418-Temp-0.7/analysis-results.json`
- 비교 기준:
- 베이스라인 `1week/V2/V1PromptResult.md`
- 1차 개선 `1week/V2/json/result/20260319-202059-Few-shot`

### 결과 요약

- 완전 일치(4개 필드 모두 일치): `9/12` = `75.0%`
- 필드 단위 정확도: `43/48` = `89.6%`

#### 필드별 정확도

- `intent`: `11/12` = `91.7%`
- `urgency`: `11/12` = `91.7%`
- `needs_clarification`: `9/12` = `75.0%`
- `route_to`: `11/12` = `91.7%`

### 토큰 사용량 분석

- 총 prompt tokens: `9,443`
- 평균 prompt tokens: `786.92`
- 총 completion tokens: `392`
- 평균 completion tokens: `32.67`
- 총 tokens: `10,068`
- 평균 total tokens: `839.0`

### 핵심 지표 분석

- 정답 기준 `needs_clarification=true` 필요 건수: `4건`
- 예측 `needs_clarification=true`: `2건`
- 정답 기준 `intent=other` 필요 건수: `3건`
- 예측 `intent=other`: `2건`
- 정답 기준 `route_to=human_support` 필요 건수: `3건`
- 예측 `route_to=human_support`: `2건`

### 이전 결과와 비교

- 베이스라인 대비 완전 일치율: `75.0% -> 75.0%`로 동일
- 베이스라인 대비 필드 정확도: `93.8% -> 89.6%`로 하락
- 1차 개선 대비 완전 일치율: `75.0% -> 75.0%`로 동일
- 1차 개선 대비 필드 정확도: `93.8% -> 89.6%`로 하락
- 1차 개선 대비 평균 prompt tokens: `786.92 -> 786.92`로 동일
- 1차 개선 대비 평균 total tokens: `819.42 -> 839.0`로 증가

### 해석

- `intent=other`, `route_to=human_support`가 줄어든 것처럼 보이지만 역시 `ticket-11`을 정답과 다르게 분류한 영향이다.
- few-shot 기본값보다 필드 정확도가 낮아졌고 total token도 늘었다.
- 즉, `temperature=0.7`은 현재 작업에서는 더 좋은 균형점을 만들지 못했다.

### 결론

- Gemini 권장값 방향으로 온도를 높였지만, 현재 분류 과제에서는 이득보다 손해가 컸다.
- 채택하지 않는 것이 맞다.
