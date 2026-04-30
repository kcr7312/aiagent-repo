# 5주차 실습 과제: RAG 시스템 정량 평가 — Ragas

## 배경

4주차 RAG를 수동 채점으로 평가했지만 한계가 명확합니다.

- 확장성 부족: 문제가 많아지면 채점 불가
- 진단 불가: 실패 원인이 검색인지 생성인지 구분 안 됨
- 재현성 낮음: 채점 기준이 매번 달라짐

이번 과제는 4주차 RAG를 재사용해 Ragas 기반 자동·정량 평가 파이프라인을 구축합니다.

1. Golden Dataset 확장: `ground_truth_contexts` 수동 어노테이션
2. Ragas 자동 평가: 4대 메트릭 + Answer Correctness (Basic/Advanced)
3. Basic vs Advanced 비교 분석, 실패 케이스 Deep Dive

### 이전 주차와의 연결

| 주차 | 이번 주와의 연결 |
|------|---------------|
| 2주차 | 실습 심화 C에서 2주차 정답률과 Ragas Ans Correctness 비교 |
| 3주차 | `evidence_text` → `ground_truth_contexts` (문자열 → 리스트) |
| 4주차 | 파이프라인·Golden Dataset 재사용, `expected_answer`는 `ground_truth`의 출발점 |

## 데이터

- 4주차와 동일한 의료급여 PDF (`data/2025 알기 쉬운 의료급여제도.pdf`, `data/2026 알기 쉬운 의료급여제도.pdf`)
- 4주차 벡터 저장소(`source_year` 메타데이터 포함) 재사용 권장
- 성능 변별이 어려우면 자료 추가: https://www.hira.or.kr/ra/ebook/list.do?pgmid=HIRAA030402000000

### Golden Dataset 확장

4주차 Dataset(20문제)에 두 필드를 추가합니다.

| 필드 | 의미 | 준비 방법 | 이전 주차 대응 |
|------|------|---------|------------|
| `ground_truth` | 기대 답변 | `expected_answer`를 완전한 문장으로 정제 | 4주차 `expected_answer` 확장 |
| `ground_truth_contexts` | 정답 근거 청크 (리스트) | PDF에서 근거 문단 발췌 | 3주차 `evidence_text` (문자열 → 리스트) |

#### `ground_truth`는 완전한 문장으로

Ragas Answer Correctness는 의미 유사도(임베딩) + 사실 일치도(LLM)의 가중 평균입니다. RAG 답변이 완전한 문장이므로 `ground_truth`도 같은 형태여야 유사도가 제대로 측정됩니다.

| 형태 | 예시 | 체감 |
|------|------|------|
| 나쁨 | `"1,000원"` | 유사도 낮아 저평가 |
| 좋음 | `"2025년 의료급여 1종 수급권자의 외래 본인부담금은 1,000원입니다."` | 유사도·사실 일치도 모두 높음 |
| 장황 | 2~3줄 장문 | RAG 답변보다 길어져 유사도 하락 |

> 정제 원칙(예: "년도 + 대상 + 조건 + 값 순으로 한 문장")을 README.md에 기록.

#### 확장 Dataset 예시 (JSONL)

```jsonl
{"question": "2025년 의료급여 1종 수급권자의 외래 본인부담금은?", "ground_truth": "2025년 의료급여 1종 수급권자의 외래 본인부담금은 1,000원입니다.", "ground_truth_contexts": ["1종 수급권자 외래 본인부담금은 1,000원이며..."], "difficulty": "easy", "source_year": "2025"}
{"question": "2025년 대비 2026년에 달라진 본인부담률은?", "ground_truth": "2026년에는 외래 본인부담금이 1,000원에서 1,500원으로 인상되었습니다.", "ground_truth_contexts": ["2025년 본인부담금 1,000원...", "2026년 본인부담금 1,500원..."], "difficulty": "cross-year", "source_year": "2025+2026"}
```

> 파일에는 `question` / `ground_truth` / `ground_truth_contexts`로 저장. Ragas v0.2+ 입력 시 `user_input` / `reference` / `reference_contexts`로 매핑 (Step 1-2).

#### 주의사항

- `ground_truth_contexts`는 리스트 (cross-year 문항은 두 년도 청크 포함)
- 벡터 저장소 청크와 일치할 필요 없음. PDF 원본 문단을 의미 단위로 발췌
- 최소 10문제, 권장 15문제. 난이도별(`easy`/`medium`/`hard`/`cross-year`) 고른 분포
- 파일명: `golden_dataset_v2.jsonl`

## 실습 구조

### Step 1: Ragas 자동 평가 환경 구축

Ragas 0.4.x 기준. v0.2에서 스키마가 바뀌었으니 `pip show ragas`로 0.2 이상 확인. `question`/`answer`/`contexts` 예시는 대부분 v0.1이라 최신 버전과 호환되지 않음.

#### 1-1. 설치 및 API 키

Ragas 0.2 이상과 LangChain 연동 패키지(Anthropic, OpenAI)를 설치하고 `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 환경변수를 설정합니다.

평가용 LLM / 임베딩 선택:

- 생성 LLM이 GPT-4o면 평가용은 Claude Sonnet 계열 권장
- 임베딩: OpenAI `text-embedding-3-small` 또는 4주차 한국어 임베딩 재사용
- Ragas 내부 프롬프트는 기본 영어 → `adapt_prompts(language="korean", llm=evaluator_llm)`로 한국어 전환

#### 1-2. 평가 데이터 준비 (v0.2+ 스키마)

각 질문에 대해 Basic/Advanced RAG를 실행하여 `retrieved_contexts`(검색 청크)와 `response`(답변)를 수집. `SingleTurnSample` + `EvaluationDataset`으로 구성합니다.

| JSONL 필드 | `SingleTurnSample` 필드 |
|-----------|----------------------|
| `question` | `user_input` |
| (RAG 실행 결과) | `response` |
| (RAG 실행 결과) | `retrieved_contexts` |
| `ground_truth` | `reference` |
| `ground_truth_contexts` | `reference_contexts` |

JSONL을 한 줄씩 읽어 RAG에 질문을 넣고, 파일 필드와 실행 결과를 매핑 표에 따라 `SingleTurnSample`로 묶어 파이프라인별 `EvaluationDataset`을 만듭니다.

> RAG의 `invoke()` 반환 형태는 구현마다 다름. "검색 청크 리스트"와 "답변 문자열"을 분리해 꺼낼 수 있어야 함.

#### 1-3. 평가용 LLM / 임베딩 래핑

평가용 LLM(ChatAnthropic `claude-sonnet-4-5`, temperature=0)과 임베딩(`text-embedding-3-small`)을 `LangchainLLMWrapper` / `LangchainEmbeddingsWrapper`로 래핑. 메트릭 다섯 개(`ContextRecall`, `LLMContextPrecisionWithReference`, `Faithfulness`, `ResponseRelevancy`, `AnswerCorrectness`) 인스턴스를 만들고 `adapt_prompts(language="korean", llm=evaluator_llm)` → `set_prompts(**adapted)`로 한국어 프롬프트 적용.

> 첫 실행 시 번역 결과를 로그로 확인.

### Step 2: Ragas 4대 메트릭 + Answer Correctness 측정

#### 2-1. 메트릭 실행

`evaluate()`에 `dataset`, `metrics`, `llm`, `embeddings` 주입 → Basic/Advanced 각각 실행. `to_pandas()` 변환 후 `basic_ragas_scores.csv`, `advanced_ragas_scores.csv`로 저장.

메트릭 선택 이유:

- `ContextRecall()`: `reference` 기준 검색 재현율
- `LLMContextPrecisionWithReference()`: `reference` 있는 경우 표준 Precision (v0.2+ 권장)
- `Faithfulness()`: 환각 체크 (`reference` 불필요)
- `ResponseRelevancy()`: 구 `answer_relevancy`
- `AnswerCorrectness()`: End-to-end 정확도

> 소문자 함수형은 deprecation 대상. 클래스형 사용.

비용: 20문항 × 5메트릭 × 2파이프라인 = 200~300회 LLM 호출. 대략 3~8 USD. 파일럿 5문항으로 먼저 검증 권장.

#### 2-2. 결과 기록

전체 평균

| 메트릭 | Basic | Advanced | 변화 |
|--------|------|---------|-----|
| Context Recall | | | |
| Context Precision | | | |
| Faithfulness | | | |
| Answer Relevancy | | | |
| Answer Correctness | | | |

대표 문항별

| 질문 ID | 난이도 | source_year | Ctx Recall (B/A) | Ctx Precision (B/A) | Faithfulness (B/A) | Ans Relevancy (B/A) | Ans Correctness (B/A) |
|---------|--------|------------|-----------------|-------------------|------------------|-------------------|---------------------|
| q01 | easy | 2025 | / | / | / | / | / |
| q02 | medium | 2026 | / | / | / | / | / |
| q03 | cross-year | 2025+2026 | / | / | / | / | / |
| ... | | | | | | | |

> B/A = Basic/Advanced.

#### 2-3. 4주차 수동 채점 vs Ragas 비교

| 질문 ID | 4주차 판정 | Ragas Ans Correctness | 일치 | 불일치 원인 |
|---------|-----------|----------------------|-----|-----------|
| q01 | 정답 | 0.87 | 일치 | |
| q02 | 오답 | 0.42 | 일치 | |
| q03 | 정답 | 0.58 | 불일치 | 표현 차이 |
| ... | | | | |

### Step 3: Basic RAG vs Advanced RAG 비교 분석

#### 3-1. 다차원 비교

| 구분 | Ragas 5메트릭에서 개선/악화된 차원 |
|------|-----------------------------|
| 개선 | |
| 악화 | |

#### 3-2. 년도 혼동 재진단

- 년도 혼동 문항에서 어느 메트릭이 가장 민감한가?
- Ragas 기본 메트릭으로 충분한가, Year Accuracy 커스텀 메트릭이 필요한가? (→ 심화 A)

#### 3-3. 인사이트 정리

2~3문단 작성:

- 4주차 "Advanced가 낫다" 결론은 어디까지 유효한가?
- 도메인 임계값(예: Faithfulness ≥ 0.9)으로 보면 프로덕션 가능한가?
- 개선 우선순위 메트릭과 근거는?

### Step 4: 실패 케이스 Deep Dive

메트릭 점수 뒤의 실제 현상 분석. 문항 2개 필수 (Case C 선택).

#### 4-1. 문항 선별

| 케이스 | 선별 기준 | 필수 | 예시 |
|-------|----------|-----|------|
| Case A | Advanced가 Basic보다 악화된 문항 | 필수 | Re-ranker가 정답 청크를 뒤로 미룸 |
| Case B | 년도 혼동 발생 (Context 맞는데 답변 년도 틀림) | 필수 | 2025/2026 청크 혼합 |
| Case C | Ragas 메트릭 간 충돌 (예: Faithfulness 높은데 Answer Correctness 낮음) | 선택 | 환각 없지만 ground_truth와 의미 차이 |

> Case A가 없으면 "Basic·Advanced 모두 오답인 가장 어려운 문항"으로 대체. 선별 기준 명시.

#### 4-2. 케이스별 분석 양식

```
### Case [A/B/C]: q[XX]

질문: {question}
참고 정답: {ground_truth}

[검색된 청크 — Basic RAG]
1. (청크 전문, source_year 포함)
2. ...

[검색된 청크 — Advanced RAG]
1. ...
2. ...

[생성된 답변]
- Basic: {답변}
- Advanced: {답변}

[메트릭 점수는 Step 2 결과표에서 해당 행 인용]

[원인 분석]
- 검색/생성/둘 다 중 어디가 문제?
- 어느 메트릭이 가장 잘 드러냈나?
- 조치 (청킹/프롬프트/Re-ranker/메타데이터 필터)?
```

#### 4-3. 공통 교훈

3~5개 bullet:

- 어떤 질문 유형에서 메트릭이 실제 품질과 어긋났나
- Ragas가 놓치는 실패 유형
- 4주차 수동과 5주차 자동 중 어느 쪽이 더 엄격/관대한가

---

## 선택 심화 과제

필수 아님. 하나 이상 수행 시 제출.

### 심화 A: Custom Metric — YearAccuracy

Ragas 기본 메트릭은 년도 혼동을 직접 포착하지 못함. `YearAccuracy` 커스텀 메트릭을 Ragas에 통합.

요구사항

- `MetricWithLLM` 등 베이스 클래스 상속
- 입력: `question`, `response`, `source_year`
- 출력: 0~1 점수
- `evaluate()`에서 기존 메트릭과 함께 사용 가능
- Basic/Advanced 측정 후 년도 혼동 진단 기여도 평가

참고: [Ragas — Write your own Metric](https://docs.ragas.io/en/stable/howtos/customizations/metrics/write_your_own_metric/)

### 심화 B: 평가 → 개선 → 재평가

Step 3-3의 "개선 우선순위 메트릭"을 한 번 개선하고 재평가.

절차

1. 개선할 메트릭 1개 선택 (예: Faithfulness)
2. 가설 수립 (예: "컨텍스트 외 정보 금지 지시 강화 → Faithfulness 0.72 → 0.85")
3. 변경 적용 (프롬프트·청킹·Re-ranker 중 하나만, 범위 최소)
4. Ragas 재실행
5. 변경 전/후 전체 메트릭 표 비교

| 메트릭 | 변경 전 | 변경 후 | 변화 |
|--------|--------|--------|------|
| Context Recall | | | |
| Context Precision | | | |
| Faithfulness | | | |
| Answer Relevancy | | | |
| Answer Correctness | | | |

- 가설 vs 결과 일치 여부
- 부작용 발생 시 원인

### 심화 C: 2주차~5주차 누적 개선 비교

"프롬프트만 → RAG → Advanced RAG → 평가 체계" 누적 가치 시각화.

조건

- 2주차 2024 PDF, 4/5주차 2025/2026 PDF라 정답값이 바뀔 수 있음. 교집합 문항 식별 선행
- 교집합 3문항 미만이면 평균 수준 비교로 대체 (같은 문항 비교가 아님을 명시)

| 방식 | 시점 | 비교 축 |
|------|-----|--------|
| 2주차 Zero-shot | 2주차 | 사람 정답률 |
| 2주차 최고 (CoT/Self-Consistency) | 2주차 | 사람 정답률 |
| 4주차 Basic RAG | 4주차 | 사람 정답률 |
| 4주차 Advanced RAG | 4주차 | 사람 정답률 |
| 5주차 Advanced RAG | 이번 주 | Ragas Ans Correctness |

- 척도 차이 주석 명시
- 누적 개선 곡선 bullet/표, 가장 큰 도약 구간 해석

### 심화 D: 건강보험심사평가원 데이터 확장 평가

4주차에서 쓴 의료급여 PDF 외에 건강보험심사평가원 e-book(https://www.hira.or.kr/ra/ebook/list.do?pgmid=HIRAA030402000000)에서 관련 자료를 추가 인덱싱하고 Golden Dataset을 확장해 평가 범위를 넓힙니다.

요구사항

- 건강보험심사평가원 e-book에서 1~2개 PDF 선택 (의료급여·건강보험 관련 주제)
- 4주차 벡터 저장소에 추가 인덱싱 (`source_document` 등 메타데이터 포함)
- Golden Dataset에 새 자료 기반 문제 5개 이상 추가 (`ground_truth`, `ground_truth_contexts` 포함)
- 확장 전/후 Ragas 5메트릭 비교
  - Context Recall/Precision 변화
  - Faithfulness·Answer Correctness 유지 여부
  - 자료 간 혼동·충돌 발생 여부

기록

- 추가한 자료 목록과 선택 이유
- 확장 전/후 메트릭 비교 표
- 새로 발견된 실패 유형 (있다면)

## 구현 요구사항

### 필수

1. Step 1~4 모두 구현 및 결과 기록
2. `golden_dataset_v2.jsonl` 작성 (`ground_truth_contexts` 포함, 최소 10문제 / 권장 15문제)
3. Ragas 5개 메트릭 측정 (Basic/Advanced)
4. 4주차 수동 채점과 Ragas Ans Correctness 일치도 분석
5. Basic vs Advanced 비교, 년도 혼동 재진단, 인사이트 정리
6. 실패 케이스 2~3건 분석 + 공통 교훈

### 권장

- 4주차 파이프라인 재사용
- 평가용 LLM: GPT-4o 또는 Claude Sonnet 이상 (한국어 품질)
- 평가용 LLM은 생성용과 다른 모델 패밀리

### 선택 심화

- 심화 A: YearAccuracy Custom Metric
- 심화 B: 평가 → 개선 → 재평가
- 심화 C: 2주차~5주차 누적 비교
- 심화 D: 건강보험심사평가원 데이터 확장 평가

### 금지

- ChatGPT/Claude 웹 UI 사용
- `ground_truth_contexts`를 LLM으로 자동 생성 (수동 어노테이션이 학습 포인트)

## 제출물

- 브랜치 `week5/<GithubID>` 생성 후 PR

필수 파일 (`week-5/<GithubID>/`):
- `golden_dataset_v2.jsonl`
- `README.md` (이론 + 실습 결과)
- 관련 코드 (Ragas 평가 스크립트)
- 평가 결과 로그 (JSON/CSV)

## README.md 필수 포함 항목

1. 프레임워크·모델(생성용 LLM, 평가용 LLM, 임베딩)·Ragas 버전·실행 환경
2. Golden Dataset 확장 전략 (`ground_truth_contexts` 발췌 원칙, `ground_truth` 정제 원칙, cross-year 처리)
3. Ragas 평가 파이프라인 (평가용 LLM 선택 이유, 데이터셋 구성)
4. Step 2 결과 (5메트릭 표, 4주차 수동 채점 비교)
5. Step 3 결과 (Basic vs Advanced 비교, 년도 혼동 재진단, 인사이트)
6. Step 4 결과 (실패 케이스, 공통 교훈)
7. 이론 과제 답변
8. 가설 vs 실제 결과 비교
9. (선택) 심화 과제 결과

## 참고 자료

Ragas
- [Ragas 공식 문서](https://docs.ragas.io/)
- [Ragas GitHub](https://github.com/explodinggradients/ragas)
- [Context Recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)
- [Context Precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)
- [Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)
- [Answer Relevancy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/)
- [Answer Correctness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_correctness/)
- [RAGAS Paper — Es et al. 2023](https://arxiv.org/abs/2309.15217)

평가 프레임워크
- [DeepEval](https://docs.confident-ai.com/)
- [Promptfoo](https://www.promptfoo.dev/docs/intro/)
- [LangSmith Evaluation](https://docs.smith.langchain.com/evaluation)

## 힌트

- Ragas 첫 사용이라면 공식 Quickstart(https://docs.ragas.io/en/stable/getstarted/)로 스키마를 익힌 뒤 시작. 블로그 튜토리얼 대부분이 v0.1 기준이라 최신 버전과 맞지 않음.
- 4주차 RAG 체인이 답변 문자열만 반환한다면 `retrieved_contexts`도 함께 꺼내도록 수정 필요. LangChain LCEL이면 `RunnablePassthrough.assign()`으로 중간 검색 결과를 병행 전달. AI 도움으로 10~20줄 수준.
- `ground_truth_contexts` 품질이 Context Recall 신뢰도를 결정. PDF에서 2~5문장 단위로 발췌.
- 파일럿 5~10문항으로 스키마·비용 먼저 검증.
- `pip show ragas`로 버전 확인 (v0.1/v0.2+ API 차이).
- Faithfulness·Answer Relevancy 높은데 Answer Correctness만 낮으면 `ground_truth` 품질 의심.
- Context Recall 높고 Answer Correctness 낮음 → 생성 단계. Faithfulness 낮으면 환각, 높으면 프롬프트/포맷 문제.
- Context Precision은 순서 민감. Recall과 함께 봐야 "검색이 뭘 못했나" 드러남.
- 년도 혼동은 Ragas 기본 메트릭으로 직접 잡히지 않음 (Year Accuracy 커스텀 메트릭이 필요한 이유, 심화 A 참고).
- Step 1~2로 숫자 확보 후 Step 3~4 진행. 심화는 마지막에.
