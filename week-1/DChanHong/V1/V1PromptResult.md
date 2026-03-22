# V1 Prompt Result

## 실행 대상

- 비교 기준 데이터: `1week/dataset.jsonl`
- 분석 결과 데이터: `1week/V1/json/result/20260317-230922/analysis-results.json`

## 정확도 요약

- 완전 일치(4개 필드 모두 일치): `9/12` = `75.0%`
- 필드 단위 정확도: `44/48` = `91.7%`

### 필드별 정확도

- `intent`: `12/12` = `100%`
- `urgency`: `9/12` = `75.0%`
- `needs_clarification`: `11/12` = `91.7%`
- `route_to`: `12/12` = `100%`

## 오차 항목

### ticket-08

- 기대값: `urgency=medium`
- 예측값: `urgency=low`

### ticket-09

- 기대값: `urgency=high`
- 예측값: `urgency=medium`

### ticket-12

- 기대값:
  - `urgency=medium`
  - `needs_clarification=true`
- 예측값:
  - `urgency=low`
  - `needs_clarification=false`

## 결과 해석

- `intent`와 `route_to`는 모두 정확하게 분류되었다.
- 전체적으로 문의 유형 분류와 담당 부서 라우팅은 안정적이다.
- 반면 `urgency`는 다소 보수적으로 낮게 판단하는 경향이 있었다.
- `ticket-12` 사례를 보면 애매한 절차 문의를 명확한 요청으로 판단하는 경향도 일부 보였다.

## 난이도별 관찰

- `normal`: `4/6` 완전 일치
- `boundary`: `3/3` 완전 일치
- `ambiguous`: `2/3` 완전 일치

## 비용 메모

- 총 12건 호출 비용: 약 `7원`

## V2 개선 방향

- `urgency` 판단 기준을 프롬프트에서 더 명확히 보강
- `needs_clarification` 판정 기준을 애매한 절차 문의 중심으로 보강
- 필요 시 `temperature`, `seed` 등 재현성 중심 옵션 재조정 검토
