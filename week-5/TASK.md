Step 1. Ragas 평가 환경 구성
Ragas 기반 평가를 수행하기 위한 실행 환경을 구성하였다. 필요한 패키지와 API 키를 준비하고, 평가 데이터셋에 `question`, `ground_truth`, `ground_truth_contexts` 필드를 포함하도록 정비하였다. 또한 Basic/Advanced 파이프라인을 대상으로 Ragas 평가를 수행할 수 있도록 평가 스크립트를 수정하였고, 실행 결과가 `basic_rag_run_traces`, `advanced_rag_run_traces`, `basic_ragas_scores`, `advanced_ragas_scores` 형태로 저장되는 것까지 확인하였다. 이후 Step 2~4의 분석은 이 과정에서 생성된 결과 파일을 기반으로 진행하였다.



2-2. 결과 기록

본 절의 정량 비교는 다음 산출물을 기준으로 작성하였다.

전체 평균 비교표: comparison_step2/step2_overall_means.csv
대표 문항별 비교표: comparison_step2/step2_representative_questions.csv
Markdown 정리본: comparison_step2/step2_tables.md

이들 파일을 바탕으로 Basic(Vector Search)와 Advanced(Hybrid Search)의 Ragas 평가 결과를 비교하였다. 전체 평균 기준으로 Advanced는 Context Recall과 Answer Correctness에서 상승을 보였으나, Context Precision과 Faithfulness는 소폭 하락하였고, Answer Relevancy는 크게 하락하였다. 이러한 결과는 Hybrid 검색이 더 많은 근거를 회수하는 데에는 유리하지만, 질문과 직접적으로 관련된 답변을 안정적으로 생성하는 측면에서는 추가 보완이 필요함을 보여준다.

2-3. 4주차 수동/규칙 판정과 5주차 Ragas 비교

본 절의 비교는 다음 산출물을 기준으로 작성하였다.

4주차 vs 5주차 비교표: comparison_step2/step2_manual_vs_ragas.csv
요약 정보: comparison_step2/step2_summary.json
Markdown 정리본: comparison_step2/step2_tables.md

비교 결과, baseline vs basic은 20문항 중 12문항 일치, hybrid vs advanced는 20문항 중 10문항 일치하였다. 이는 Ragas의 Answer Correctness가 기존 규칙 기반 판정과 일부 일치하는 경향을 보이지만, 완전히 동일한 기준으로 동작하지는 않음을 의미한다. 즉, 5주차 자동 평가는 4주차 판정을 대체하는 것이 아니라, 기존 평가를 보완하는 추가 정량 지표로 해석하는 것이 적절하다.


3-1. 다차원 비교
Advanced가 개선한 지표
  Context Recall: `0.5417 → 0.7895`
  Answer Correctness: `0.3871 → 0.4965`

Advanced가 악화한 지표
  Context Precision: `0.3667 → 0.3500`
  Faithfulness: `0.6892 → 0.6826`
  Answer Relevancy: `0.7660 → 0.3067`

해석
  Advanced는 근거를 더 많이 찾는 데는 효과적이었다.
  하지만 질문과 직접 맞는 답변을 안정적으로 생성하는 데는 실패한 문항이 늘었다.
  따라서 이번 결과는 “Advanced가 전반적으로 우수”가 아니라, Recall 향상과 Relevancy 저하의 trade-off로 보는 게 맞다.


3-2. 년도 혼동 재진단
`Context Recall`이 높아져도 `Answer Correctness`가 같이 올라가지 않은 문항이 있었다.
예:
  q09: basic correctness `0.6055`, advanced `0.0622`
  q10: basic correctness `0.6999`, advanced `0.0475` 

반대로 advanced가 더 나아진 문항도 있었다.
  q11: basic `0.2157`, advanced `0.7216`
  q12: basic `N/A`, advanced `0.8637` 

해석
  연도 관련 문항에서는 문서를 많이 찾는 것만으로 충분하지 않았다.
  실제 답변에 올바른 연도 정보를 반영했는지가 더 중요했다.
  따라서 년도 혼동 진단에는 `Context Recall`보다 `Answer Correctness`가 더 직접적인 지표였다. 


3-3. 인사이트 정리
4주차 결론의 재평가
  “Advanced가 더 낫다”는 결론은 부분적으로만 맞았다.
  Recall과 Correctness는 개선됐지만, Relevancy와 일부 Faithfulness는 악화됐다.

4주차 판정과의 일치도
  baseline vs basic: `12/20` 일치
  hybrid vs advanced: `10/20` 일치

추가 해석
  이번 결과는 검색 구조 차이만이 아니라, 사용한 LLM 성능 등급의 영향도 포함했을 가능성이 있다.
  생성에 사용한 경량 모델(Gemini 3.1 Flash Lite 계열)은 비용 절감에는 유리하지만, 연도 구분·조건 해석이 중요한 문항에서 정밀도가 떨어졌을 가능성이 있다.
  따라서 이번 결과는 “Advanced 검색 구조 자체의 성능”과 “경량 생성 모델의 한계”가 함께 반영된 결과로 보는 것이 타당하다.

최종 결론
  이번 프로젝트는 Advanced의 장점과 한계를 동시에 드러낸 결과가 나왔다.
  즉, 검색 커버리지는 좋아졌지만, 답변 품질은 아직 안정적이지 않았다.
  이후 개선 우선순위는 `Answer Relevancy`, `Faithfulness`, 그리고 연도 혼동을 직접 잡는 보조 지표 설계다.




좋아. 제출용으로 바로 넣을 수 있게 **짧고 단정하게** 정리해줄게.

4-1. 문항 선별

| 케이스    | 질문 ID | 선정 이유                                                                                                                      |
| ------ | ----- | -------------------------------------------------------------------------------------------------------------------------- |
| Case A | q09   | Basic의 `Answer Correctness`는 `0.6055`였으나, Advanced는 `0.0622`로 크게 하락하였다. Advanced 적용 시 오히려 성능이 악화된 대표 사례로 판단하였다.            |
| Case B | q11   | Basic의 `Answer Correctness`는 `0.2157`, Advanced는 `0.7216`으로 크게 상승하였다. 같은 연도 조건 문항에서 검색 결과 차이가 답변 품질 차이로 직접 이어진 사례로 판단하였다.  |


4-2. 케이스별 분석
Case A. q09

질문**: 2025년 의료급여에서 2종 수급권자의 제2차 또는 제3차의료급여기관 외래 본인부담률은 얼마인가?
참고 정답**: 15%
검색된 청크 — Basic**: 일반 본인부담률 표(p.9) 포함
검색된 청크 — Advanced**: 아동 5%, 틀니 15%, 의뢰서 없이 이용 시 100/100 등 주변 규정이 함께 검색됨
생성된 답변**
  * Basic: 15%로 답변
  * Advanced: 일반 수치가 문맥에 없다고 답변

메트릭**
  * Basic: Recall `1.0`, Precision `0.3333`, Correctness `0.6055`
  * Advanced: Recall `0.0`, Precision `0.0`, Faithfulness `0.75`, Correctness `0.0622` 

원인 분석**: Advanced는 관련은 있으나 질문 핵심과 직접 대응하지 않는 청크가 섞이면서 정답 청크를 놓쳤다. 즉 검색 단계의 노이즈 증가가 생성 오답으로 이어진 사례였다.
조치**: 일반 규정 청크 우선 retrieval, 예외 규정/특정 급여 항목 청크 분리, 프롬프트에 일반 규정 우선 답변 제약 추가

Case B. q11

질문**: 2025년 의료급여에서 15세 이하 아동이 의료급여의뢰서 없이 제2차의료급여기관에서 진료받을 수 있는가?
참고 정답**: 가능함. 15세 이하 아동은 단계별 진료 예외 대상임
검색된 청크 — Basic**: 아동 관련 주변 규정, 의뢰서 없이 이용 시 100/100 규정
검색된 청크 — Advanced**: “15세 이하 아동은 의뢰서 없이 제2차 의료급여기관 적용 가능” 청크 직접 회수
생성된 답변**
  * Basic: 예외 규정이 없다고 답변
  * Advanced: 예외 대상이므로 가능하다고 답변

메트릭**
  * Basic: Recall `0.0`, Faithfulness `0.75`, Correctness `0.2157`
  * Advanced: Recall `1.0`, Precision `1.0`, Faithfulness `1.0`, Correctness `0.7216` 

원인 분석**: 핵심 원인은 검색 차이였다. Basic은 정답 청크를 찾지 못했고, Advanced는 정답 청크를 직접 회수하여 생성 단계까지 올바르게 연결하였다.
조치**: “15세 이하 / 예외 / 의뢰서 없이 / 제2차” 키워드 가중치 강화, 예외 규정 전용 태그 추가

4-3. 공통 교훈
* Advanced는 항상 우수하지 않았다. q09처럼 검색 범위가 넓어지면서 오히려 질문과 직접 관련 없는 청크가 섞여 성능이 악화될 수 있었다. 
* 반대로 q11처럼 정답 청크를 직접 회수한 경우에는 Advanced가 Basic보다 분명한 개선을 보였다. 
* 따라서 이번 결과는 Advanced가 **검색 커버리지를 넓히는 데는 강점**이 있지만, **질문 중심의 정밀한 청크 선택이 동반되지 않으면 오히려 오답 가능성이 커질 수 있음**을 보여준다.
* 사견으로는, Basic은 보수적이지만 질문 핵심 청크만 잡으면 안정적이고, Advanced는 잠재력이 더 크지만 청크 정제와 예외 규정 처리까지 함께 설계되지 않으면 성능 변동성이 더 큰 구조라고 판단된다.
