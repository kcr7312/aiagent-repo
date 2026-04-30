# 5주차 이론 과제: RAG 평가 — Golden Dataset, LLM-as-a-Judge, Ragas

## 개요

4주차 RAG를 수동 채점했지만 실무에서는 매번 채점할 수 없고, 정답률 하나로는 검색/생성 중 어디가 문제인지 모릅니다. 이번 주에 Ragas 기반 자동·체계적 평가를 학습합니다.

1. Golden Dataset: 변경의 회귀를 객관적으로 검증하는 기준
2. LLM-as-a-Judge: LLM을 판정자로 활용해 정답·품질을 자동 채점하는 방식
3. Ragas 프레임워크: LLM-as-a-Judge 원리를 기반으로 검색·생성 단계를 분리 진단하는 메트릭 세트

### RAG 평가가 왜 어려운가

RAG는 두 단계이므로 답변이 틀렸을 때 원인을 쪼개서 봐야 합니다.

```
질문 → [Retrieval] → [Generation] → 답변
```

정답률 하나로는 어디가 문제인지(청킹? 검색? Re-ranker? 프롬프트?) 알 수 없음. Ragas는 네 메트릭으로 단계를 분리 진단.

| 메트릭 | 단계 | 정의 | ground_truth 필요? |
|--------|-----|-----|----------------|
| Context Recall | Retrieval | 정답에 필요한 내용이 검색에 들어왔는가 | 필요 |
| Context Precision | Retrieval | 관련 청크가 상위에 있는가 | 필요 |
| Faithfulness | Generation | 답변이 컨텍스트로 뒷받침되는가 (환각 체크) | 불필요 |
| Answer Relevancy | Generation | 답변이 질문에 답하고 있는가 | 불필요 |
| Answer Correctness | End-to-End | 답변이 ground_truth와 의미적으로 일치 | 필요 |

이번 주는 4주차 Basic/Advanced RAG를 재사용해 같은 시스템을 새 평가 렌즈로 측정합니다. "Advanced가 좋아 보였다"를 "어느 메트릭이 얼마나 좋아졌다"로 바꾸는 것이 목표.

### 이전 주차와의 연결

| 주차 | 이번 주와의 연결 |
|------|---------------|
| 2주차 | 실습 심화 C에서 2주차 정답률과 Ragas Ans Correctness 비교 |
| 3주차 | `evidence_text` → `ground_truth_contexts` (문자열 → 리스트) |
| 4주차 | 파이프라인·Golden Dataset 재사용, `expected_answer`는 `ground_truth` 출발점 |

## 조사 시 참고 원칙

공식 문서·논문 2개 이상 교차 참조. 본인 언어로 작성, 원문 출처 표기.

## 필수 조사 항목

### 1. Golden Dataset

평가의 기준점. 품질이 평가 전체 품질을 결정.

- 한 줄 정의와 왜 필요한가 (없으면 생기는 문제)
- 필수 스키마: Ragas 평가에 필요한 필드와 준비 주체·방법. v0.1/v0.2+ 필드명 차이 병기 (v0.2+ 권장)
- 권장 규모: 초기/성숙/대규모 단계별 적정 개수와 근거
- 양보다 질: 좋은 Dataset 조건 (실제 질문, 함정 케이스, 회귀 이력)
- `ground_truth_contexts` 수동 어노테이션 이유 (어느 메트릭에 필수인지)

참고 자료
- [Ragas — Testset Generation](https://docs.ragas.io/en/stable/concepts/test_data_generation/)
- [Ragas — Schema](https://docs.ragas.io/en/stable/concepts/metrics/overview/)

### 2. 평가의 필요성과 LLM-as-a-Judge

LLM·RAG 시스템은 확률적 출력을 내기 때문에 전통 소프트웨어처럼 단위 테스트로만 검증하기 어렵습니다. 체계적 평가 없이는 변경의 영향을 판단할 수 없고 개선 방향도 설 수 없습니다. 이 체계를 구현하는 대표 방법이 LLM-as-a-Judge이며, Ragas의 핵심 메트릭도 이 원리 위에 있습니다.

#### 2-1. 왜 체계적 평가가 필요한가

평가 체계가 없을 때 생기는 문제:

- 회귀 탐지 불가: 프롬프트·모델·검색 설정을 바꿨을 때 성능 변화를 근거 있게 판단 못 함
- 디버깅 지점 모호: 답변이 틀렸을 때 어느 단계(검색/생성/프롬프트)가 원인인지 불명
- 비교 기준 부재: 여러 모델·파라미터 중 무엇이 나은지 직관으로 판단하게 됨
- 프로덕션 도입 판단 불가: "이 정도면 쓸 수 있다"는 합의 기준이 없음

조사 포인트:

- 소프트웨어 테스트와의 차이 (결정적 입출력 vs 확률적 생성)
- 회귀 검증(regression test) 개념과 Golden Dataset의 연결
- 자동 평가 vs 사람 평가 스펙트럼과 trade-off (비용·시간·신뢰성)

#### 2-2. LLM-as-a-Judge

텍스트 기반 자동 채점에 LLM을 판정자(judge)로 활용하는 방식. Ragas의 Faithfulness, Answer Correctness 등 핵심 메트릭이 이 원리 위에 구축되어 있으므로, Ragas 메트릭을 이해하기 전에 먼저 익혀야 하는 선행 개념입니다.

- 등장 배경: BLEU/ROUGE 등 n-gram 자동 평가의 한계, 사람 평가의 비용·시간 한계
- 작동 원리: 루브릭과 판정 기준을 프롬프트로 제공 → LLM이 답변을 읽고 점수·근거 출력
- 사람 평가와의 일치율: GPT-4 Judge가 사람 평가와 얼마나 일치하는가 (권장, 필수 아님)
- 루브릭 설계 원칙: 좋은 루브릭 vs 나쁜 루브릭 예시 직접 작성
- 한계와 신뢰성: 프롬프트·모델에 따른 결과 변동, 비결정성, 호출 비용
- Ragas와의 관계: 4대 메트릭 중 어디가 LLM Judge 기반이고 어디가 규칙 기반인지 구분 (→ 3번에서 실제 적용)

참고 자료
- [Judging LLM-as-a-Judge — Zheng et al. 2023 (MT-Bench)](https://arxiv.org/abs/2306.05685)
- [G-Eval — Liu et al. 2023](https://arxiv.org/abs/2303.16634)
- [Anthropic — Chain-of-Thought 프롬프팅](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought)

### 3. Ragas 4대 메트릭 (+ Answer Correctness)

#### 3-1. 검색 단계

| 구분 | Context Recall | Context Precision |
|------|---------------|------------------|
| 정의 | | |
| 계산 방식 | | |
| 낮을 때 의심할 점 | | |
| 개선 기법 | | |

#### 3-2. 생성 단계

| 구분 | Faithfulness | Answer Relevancy |
|------|-------------|------------------|
| 정의 | | |
| 계산 방식 | | |
| 낮을 때 의심할 점 | | |
| 개선 기법 | | |

#### 3-3. End-to-End

- Answer Correctness 정의, 계산 방식 (의미 유사도 + 사실 일치도 가중 평균), ground_truth 품질 의존성
- Answer Correctness만으로 부족한 이유 (검색/생성 어디가 문제인지 불가)

#### 3-4. 메트릭 간 관계

| 시나리오 | 낮아지는 메트릭 | 원인 | 대응 |
|---------|---------------|-----|------|
| 정답 청크 자체를 검색이 놓침 | | | |
| 정답 청크는 있지만 8~10위로 밀림 | | | |
| 검색은 맞는데 LLM이 외부 정보 추가 | | | |
| LLM이 질문을 잘못 이해 | | | |
| 답은 맞는데 장황 | (해당 없음 — 왜?) | | |

> 장황함·간결성 같은 주관적 품질은 Ragas 기본 메트릭으로 잡히지 않음. 도메인 임계값을 정하거나 Ragas 커스텀 메트릭(`MetricWithLLM` 상속)으로 보완. 실습 심화 A가 그 예.

참고 자료
- [Ragas Metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [Ragas Paper — Es et al. 2023](https://arxiv.org/abs/2309.15217)
- [Ragas — Faithfulness 내부 구현](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)

## 선택 심화 조사 항목

필수 아님.

### 심화 1. Ragas 메트릭 내부 LLM 동작

각 메트릭이 LLM에게 어떤 판단을 시키는지 공식 문서·소스로 확인. 예: Faithfulness의 claim 단위 대조, Context Precision의 청크별 관련성 판단. 호출 비용이 큰/작은 메트릭 구분.

참고: [Faithfulness 내부](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/), [Context Precision 내부](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)

### 심화 2. Ragas 커스텀 메트릭 설계

`MetricWithLLM` 상속으로 도메인 특화 메트릭을 만드는 방식. 프롬프트 템플릿, 출력 파서, `_single_turn_ascore()` 메서드. 실습 심화 A의 YearAccuracy가 이 방식을 사용.

참고: [Ragas — Write your own Metric](https://docs.ragas.io/en/stable/howtos/customizations/metrics/write_your_own_metric/)

## 실습 과제 예측

실습 전 아래 가설을 세우고, 실습 후 실제 결과와 비교하여 제출 README에 포함.

1. 4주차 정답률(사람)과 Ragas Ans Correctness(자동)의 일치 정도? 어느 문항에서 차이 예상?
2. Basic/Advanced의 네 메트릭 중 가장 크게 벌어질 메트릭은? 이유는?
3. 년도 혼동 문제는 어느 Ragas 메트릭에 주로 반영될 것인가?
4. Advanced에서 Faithfulness가 오히려 낮아질 시나리오가 있을까?

## 추가 참고 자료

- [Ragas 공식 문서](https://docs.ragas.io/)
- [RAGAS Paper — Es et al. 2023](https://arxiv.org/abs/2309.15217)
- [LangSmith Evaluation](https://docs.smith.langchain.com/evaluation)
- [DeepEval](https://docs.confident-ai.com/)
- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
- [KLUE 벤치마크](https://klue-benchmark.com/)

## 제출 형식

- 제출 README(`week-5/<GithubID>/README.md`)에 이론 답변 포함
- 실습 결과와 함께 제출
- 가설 실습 전/후 비교 포함
- 블로그 복붙 금지. 공식 문서·논문에서 확인한 내용을 본인 언어로 재구성 (출처 명시)
