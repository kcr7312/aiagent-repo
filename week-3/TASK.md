# 3주차 실습 과제: RAG Indexing 파이프라인 구축

## 배경

2주차에서는 의료급여 본인부담률 표 전체를 system prompt에 넣고 프롬프트 엔지니어링으로 정답률을 개선했습니다. 하지만 이 방식은 데이터가 커지면 한계가 있습니다.

이번 과제에서는 LangChain(또는 LlamaIndex)을 사용하여 RAG Indexing 파이프라인을 직접 구축합니다. 의료급여 PDF를 청킹하고, 임베딩하여 벡터 저장소에 저장한 뒤, 질문으로 검색이 되는지 확인하는 것이 목표입니다.

## 데이터

- `data/2024 알기 쉬운 의료급여제도.pdf`: RAG 소스 문서

## 실습 구조

### Step 1: Golden Dataset 구축

RAG의 검색 품질을 측정하려면 **"어떤 질문에 어떤 답이 나와야 하고, 그 근거가 문서 어디에 있는지"**를 사전에 정의해야 합니다. 이것이 Golden Dataset입니다.

PDF 원문을 직접 읽고, **최소 5문제**를 설계하여 아래 형식으로 기록합니다.

```jsonl
{"id": "q01", "question": "65세 이상 1종 수급권자가 틀니를 하면 본인부담률은 몇 %인가요?", "expected_answer": "5%", "source_section": "04번 표 - 65세 이상 틀니 및 치과 임플란트 본인부담률", "evidence_text": "1종 → 틀니 = 5%", "conditions": ["65세 이상", "1종 수급권자", "틀니"], "difficulty": "easy"}
```

| 필드 | 설명 |
|------|------|
| `question` | 직접 설계한 질문 |
| `expected_answer` | 이 질문의 정답 |
| `source_section` | 정답 근거가 있는 PDF 섹션/표 이름 |
| `evidence_text` | 정답을 도출할 수 있는 원문의 핵심 텍스트 |
| `conditions` | 정답을 판단하기 위해 필요한 조건들 |
| `difficulty` | easy / medium / hard |

**질문 설계 가이드**

| 난이도 | 기준 | 최소 문항 |
|--------|------|----------|
| easy | 단일 조건 조회 (예: 1종 틀니 본인부담률) | 2문제 |
| medium | 2~3개 조건 조합 (예: 2종 + 아동 + 외래) | 2문제 |
| hard | 다중 조건 + 계산 또는 예외 규정 | 1문제 |

### Step 2: RAG Indexing 파이프라인 구축

LangChain 또는 LlamaIndex를 사용하여 아래 파이프라인을 구현합니다.

```
PDF 로딩 → 청킹 → 임베딩 → 벡터 저장소 저장
```

**2-1. PDF 로딩 및 청킹**
1. PDF 로더를 선택하여 문서를 로딩합니다
2. Text Splitter를 선택하고 청킹 설정(chunk_size, chunk_overlap)을 결정합니다
3. 청크 결과를 확인합니다 — 총 청크 수, 표 데이터가 깨지지 않았는지

**2-2. 임베딩 및 벡터 저장소**
1. 임베딩 모델을 선택합니다
2. 모든 청크를 벡터화하여 FAISS 또는 Chroma에 저장합니다

**기록**
- 사용한 PDF 로더, Text Splitter, chunk_size, chunk_overlap
- 총 청크 수
- 임베딩 모델명
- 벡터 저장소 종류
- 표 데이터가 포함된 청크 샘플 2~3개

### Step 3: 검색 품질 확인

Golden Dataset **5문제 전체**에 대해 벡터 저장소를 검색하고, 정답 근거가 검색되는지 확인합니다.

1. 각 질문을 벡터화하여 Top-K 검색을 수행합니다
2. 검색된 청크가 Golden Dataset의 `evidence_text`를 포함하는지 확인합니다

```
검색 성공: 검색된 Top-K 청크 중 evidence_text의 근거가 포함된 경우
검색 실패: Top-K 청크 어디에도 정답 근거가 없는 경우
```

**기록**

| 질문 ID | 난이도 | 검색 결과 | 검색된 청크 요약 |
|---------|--------|----------|----------------|
| q01 | easy | 성공/실패 | |
| ... | ... | ... | |
| **검색 성공률** | | /5 | |

- 검색 실패한 문항에 대한 원인 분석 (청킹 문제? 임베딩 문제? 질문 표현 문제?)

## 구현 요구사항

### 필수

1. Step 1~3을 모두 구현하고 각 Step의 결과를 기록
2. Golden Dataset(`golden_dataset.jsonl`)을 직접 구축하여 제출 (최소 5문제)
3. RAG Indexing 파이프라인 구현 (PDF → 청킹 → 임베딩 → 벡터 저장소)
4. 검색 품질 확인 (5문제 전수)

### 권장

- LangChain, LlamaIndex 등 RAG 프레임워크 사용
- Python 사용
- 벡터 저장소: FAISS 또는 Chroma (로컬 실행 가능한 것)
- 임베딩 모델: OpenAI text-embedding-3-small 또는 동등한 모델

### 금지

- ChatGPT/Claude 웹 UI 사용

## 제출물

PR 하나로 아래를 제출합니다.

제출 위치
- 브랜치 생성 `week3/<GithubID>` 후 PR 등록

필수 파일
- `week-3/<GithubID>/`
- `golden_dataset.jsonl` (Step 1 결과물)
- `README.md` (이론 과제 답변 + 실습 과제 결과 포함)
- 관련 코드 (참고용)

## README.md 필수 포함 항목

1. 사용한 프레임워크, 임베딩 모델, 벡터 저장소, 실행 환경
2. Golden Dataset 구축 과정 — 질문 설계 시 고려한 점
3. RAG Indexing 파이프라인 구성 — 로더, 청킹 설정, 임베딩 모델, 벡터 저장소
4. 검색 품질 확인 결과 — 5문제 결과표, 실패 원인 분석
5. 인사이트 및 다음 단계(Retrieval + Generation) 준비 사항

## 참고 자료

- [LangChain RAG Tutorial](https://python.langchain.com/docs/tutorials/rag/)
- [LlamaIndex Starter Tutorial](https://docs.llamaindex.ai/en/stable/getting_started/starter_example/)
- [FAISS Getting Started](https://github.com/facebookresearch/faiss/wiki/Getting-started)
- [Chroma Getting Started](https://docs.trychroma.com/getting-started)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [pdfplumber](https://github.com/jsvine/pdfplumber) — 표 추출에 강점

## 힌트

- **Golden Dataset 구축이 가장 중요한 단계입니다.** PDF를 읽으면서 데이터 구조를 파악하세요. 이 이해가 청킹 전략 결정에 직접 도움이 됩니다.
- hard 문제를 만들 때는 여러 조건이 교차하는 경우(예: 나이 + 수급권자 종별 + 질환 + 의료기관 종별)를 활용하세요.
- 의료급여 데이터는 표 형태가 많아서 **표 단위로 청킹**하는 것이 효과적입니다. 표를 일반 텍스트처럼 고정 크기로 자르면 행/열 관계가 깨집니다.
- 검색에서 실패가 나오면 정상입니다. 왜 실패했는지 분석하는 것이 중요합니다.
- LangChain RAG Tutorial을 따라하면 파이프라인 구축 코드는 20~30줄이면 충분합니다.
