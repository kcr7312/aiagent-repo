# 4주차 실습 과제: Basic RAG 완성 + Advanced RAG (Hybrid Search & Re-ranking)

## 배경

3주차에서는 RAG Indexing 파이프라인(PDF → 청킹 → 임베딩 → 벡터 저장소)을 구축하고, Golden Dataset으로 검색 품질을 확인했습니다. 하지만 검색된 청크를 실제로 LLM에게 전달하여 답변을 생성하는 단계는 아직 구현하지 않았습니다.

이번 과제에서는 **다년도 문서를 다루는 RAG 시스템**을 구축합니다. 실무에서는 동일한 제도가 매년 개정되며, 사용자는 특정 년도의 정보를 정확히 알고 싶어합니다. 2025년과 2026년 두 해의 의료급여제도 문서를 동시에 인덱싱하고, 올바른 년도의 정보를 검색하여 답변을 생성하는 것이 핵심 과제입니다.

이번 과제에서는 세 가지를 합니다.

1. **Basic RAG 완성**: 두 해의 문서를 벡터 저장소에 인덱싱하고 Generation을 연결하여 end-to-end RAG를 완성합니다
2. **Advanced RAG 구현**: Hybrid Search(벡터 + BM25)와 Re-ranking(Cohere Rerank)을 적용하여 검색 품질을 개선합니다
3. **년도 인식 검색**: 질문이 요구하는 년도의 문서에서 정확히 검색하는 능력을 평가합니다


## 데이터

- `data/2025 알기 쉬운 의료급여제도.pdf`: 2025년 의료급여제도 문서
- `data/2026 알기 쉬운 의료급여제도.pdf`: 2026년 의료급여제도 문서

두 해의 문서를 모두 벡터 저장소에 인덱싱합니다. 각 청크에는 출처 년도를 나타내는 메타데이터(`source_year`)를 반드시 포함시켜야 합니다.

### Golden Dataset 구축

이번 과제에서는 각 년도별로 새로운 Golden Dataset을 직접 구축합니다.

- **년도별 최소 10문제, 총 20문제 이상** 작성합니다
- JSONL 형식에 `source_year` 필드를 추가합니다

```jsonl
{"question": "2025년 의료급여 1종 수급권자의 외래 본인부담금은?", "expected_answer": "1,000원", "difficulty": "easy", "source_year": "2025"}
{"question": "2026년 의료급여 1종 수급권자의 외래 본인부담금은?", "expected_answer": "1,500원", "difficulty": "easy", "source_year": "2026"}
```

- **년도 간 차이가 있는 문항을 반드시 포함하세요.** 예를 들어 2025년과 2026년에 달라진 본인부담률, 급여 기준, 지원 금액 등을 질문으로 만들면 검색 품질을 정확하게 평가할 수 있습니다.
- **교차 비교 문항도 권장합니다.** 예: "2025년 대비 2026년에 달라진 본인부담률은?", "2025년과 2026년의 입원 급여 기준 차이는?" 같은 문항은 두 년도의 정보를 동시에 검색해야 하므로 고난이도 문항으로 분류합니다.
- 난이도 분류: `easy`, `medium`, `hard`, `cross-year` (교차 비교)

## 실습 구조

### Step 1: Basic RAG 완성 (Retrieval + Generation)

두 해의 PDF를 모두 인덱싱한 벡터 저장소를 사용하여 end-to-end RAG 파이프라인을 완성합니다.

```
질문 → 임베딩 → 벡터 검색 (Top-K) → 검색된 청크를 컨텍스트로 구성 → LLM 생성 → 답변
```

**1-1. 인덱싱**
1. 2025년, 2026년 PDF를 각각 로드하고 청킹합니다
2. 각 청크의 메타데이터에 `source_year` 필드를 추가합니다 (예: `{"source_year": "2025"}`)
3. 두 년도의 청크를 하나의 벡터 저장소에 함께 인덱싱합니다 (FAISS 또는 Chroma)

**1-2. Generation 파이프라인 연결**
1. 벡터 저장소를 로드합니다
2. Retriever를 생성합니다 (Top-K 설정)
3. 검색된 청크를 LLM 프롬프트에 컨텍스트로 전달하는 체인을 구성합니다
4. RAG 프롬프트 템플릿을 작성합니다 — 년도 정보를 인식할 수 있도록 컨텍스트에 출처 년도를 포함합니다

```python
# 프롬프트 템플릿 예시
rag_prompt = """아래 컨텍스트를 바탕으로 질문에 답하세요.
각 컨텍스트에는 출처 년도가 표시되어 있습니다. 질문이 특정 년도를 묻는 경우 해당 년도의 정보만 사용하세요.
컨텍스트에 없는 내용은 "정보를 찾을 수 없습니다"라고 답하세요.

컨텍스트:
{context}

질문: {question}

답변:"""
```

**1-3. Golden Dataset으로 end-to-end 정답률 측정**
1. Golden Dataset 전체 문항에 대해 RAG 파이프라인을 실행합니다
2. 생성된 답변을 `expected_answer`와 비교합니다
3. 정답/오답과 함께 **올바른 년도에서 검색했는지** 여부를 기록합니다

**판정 기준**
```
정답: LLM이 생성한 답변이 expected_answer의 핵심 값을 포함하는 경우
오답: 핵심 값이 누락되거나 다른 값을 답한 경우
년도 오류: 올바른 주제를 검색했지만 다른 년도의 정보를 사용한 경우 (부분 실패)
```

> 자동 판정이 어려우면 수동 판정도 가능합니다. 판정 기준을 README에 명시하세요.

**기록**

| 질문 ID | 난이도 | source_year | 검색된 청크 포함 여부 | 올바른 년도 검색 여부 | LLM 생성 답변 | 정답 여부 | 오답 원인 |
|---------|--------|-------------|-------------------|-------------------|-------------|----------|----------|
| q01 | easy | 2025 | O/X | O/X | | 정답/오답 | |
| q02 | medium | 2026 | O/X | O/X | | 정답/오답 | |
| q03 | cross-year | 2025+2026 | O/X | O/X | | 정답/오답 | |
| ... | ... | ... | ... | ... | ... | ... | ... |
| **Basic RAG 정답률** | | | | | | /N | |

**년도 혼동 분석**

올바른 주제를 검색했지만 다른 년도의 청크를 가져온 경우를 별도로 분석합니다.

| 항목 | 값 |
|------|-----|
| 올바른 년도 검색 성공률 | /N |
| 년도 혼동으로 인한 오답 수 | |
| 주요 년도 혼동 패턴 | |

**2주차 vs Basic RAG 비교** (해당하는 문항이 있는 경우)

| 방식 | 정답률 | 비고 |
|------|--------|------|
| 2주차 Zero-shot (전체 데이터 in system prompt) | % | |
| 2주차 최고 성능 기법 | % | 기법명 기재 |
| 4주차 Basic RAG | % | |

> Golden Dataset이 2주차 30문제와 다를 수 있으므로, 동일 문항 기준으로 비교하거나 전체 경향을 비교합니다.

### Step 2: Advanced RAG (Hybrid Search + Re-ranking)

Basic RAG의 검색을 개선합니다. 두 가지 기법을 적용할 수 있습니다.

#### 2-1. Hybrid Search (벡터 검색 + BM25 키워드 검색)

벡터 검색만으로는 놓치는 문서가 있습니다. 키워드 기반 검색(BM25)을 결합하여 검색 범위를 넓힙니다.

```
질문 → [벡터 검색 (Top-K)] + [BM25 검색 (Top-K)] → 결과 병합 → 중복 제거
```

**벡터DB와 BM25 구현 방식에 대한 주의사항**

BM25를 벡터DB와 결합하는 방식은 사용하는 벡터DB에 따라 달라집니다.

- **ChromaDB, FAISS**: Dense Vector만 지원하므로 BM25를 DB 내에서 직접 수행할 수 없습니다. LangChain의 `BM25Retriever.from_documents()`처럼 메모리에 별도의 BM25 인덱스를 구성하고, `EnsembleRetriever`로 벡터 검색 결과와 병합하는 방식을 사용해야 합니다. 이 경우 BM25 인덱스는 persist되지 않으므로, 앱 재시작 시 원본 문서를 다시 로드하여 인덱스를 재구축해야 합니다.
- **Qdrant, Weaviate, Pinecone, Milvus**: Sparse Vector를 네이티브로 지원하므로 DB 자체에서 Hybrid Search를 수행할 수 있습니다. Dense Vector와 Sparse Vector를 함께 저장하고, 검색 시 두 벡터를 동시에 활용하는 방식입니다. 별도의 메모리 기반 BM25 인덱스가 필요 없으며, 데이터가 DB에 persist되므로 재구축 부담이 없습니다.

이번 과제에서는 FAISS 또는 ChromaDB를 사용하므로 전자의 방식(메모리 기반 BM25 + EnsembleRetriever)으로 구현합니다. 실무에서 대규모 데이터에 Hybrid Search를 적용할 때는 Sparse Vector를 네이티브 지원하는 벡터DB를 고려하세요.

> LangChain 또는 LlamaIndex 중 3주차에서 사용한 프레임워크를 그대로 쓰는 것을 권장합니다.

#### 2-2. 메타데이터 필터링 (선택)

년도 인식 검색을 개선하기 위해 메타데이터 필터링을 추가로 적용할 수 있습니다. 질문에서 년도를 추출하고, 해당 년도의 청크만 검색 대상으로 제한하는 방식입니다.

```python
# 메타데이터 필터링 예시 (Chroma)
vector_retriever = vectorstore.as_retriever(
    search_kwargs={"k": 5, "filter": {"source_year": "2025"}}
)
```

> 메타데이터 필터링은 필수가 아닌 선택 사항이지만, 년도 혼동 문제를 해결하는 효과적인 방법입니다. 적용 여부와 결과를 기록하세요.

#### 2-3. Re-ranking (Cohere Rerank)

Hybrid Search로 가져온 후보 문서들을 Re-ranker로 재정렬하여, 질문과 가장 관련성 높은 청크를 상위로 올립니다.

```
Hybrid Search 결과 (N개) → Re-ranker 스코어링 → 상위 K개 선택 → LLM 생성
```

**구현 방법 (권장: Cohere Rerank)**

Cohere Rerank API는 무료 티어(월 1,000회)를 제공하며 한국어를 포함한 다국어를 지원합니다.

1. Cohere API 키를 발급받습니다 (https://dashboard.cohere.com)
2. `langchain-cohere` 패키지를 설치합니다
3. Hybrid Search 결과를 Cohere Rerank로 재정렬합니다

```python
from langchain_cohere import CohereRerank
from langchain.retrievers import ContextualCompressionRetriever

reranker = CohereRerank(
    model="rerank-v3.5",
    top_n=3
)

compression_retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=ensemble_retriever
)

results = compression_retriever.invoke("질문")
```

**대안 Re-ranker 옵션**

| Re-ranker | 유형 | 한국어 지원 | 특징 |
|-----------|------|-----------|------|
| Cohere Rerank v3.5 | 상용 API | 100+ 언어 | 무료 티어(월 1,000회), 가장 쉬운 연동 |
| Jina Reranker v3 | 상용 API | 다국어 | 저지연, 긴 문서(8K 토큰) 지원 |
| bge-reranker-v2-m3 | 오픈 모델 | 다국어 | BAAI 제작, 무료, 로컬 실행, 한국어 성능 양호 |
| CrossEncoder | 오픈 모델 | 영어 위주 | sentence-transformers, 가장 기본적 |

오픈 모델을 사용하면 API 비용 없이 로컬에서 실행할 수 있습니다.

```python
# 오픈 모델 예시: bge-reranker-v2-m3 (다국어 지원)
from sentence_transformers import CrossEncoder

cross_encoder = CrossEncoder("BAAI/bge-reranker-v2-m3")

pairs = [(question, doc.page_content) for doc in hybrid_results]
scores = cross_encoder.predict(pairs)

reranked = [doc for _, doc in sorted(zip(scores, hybrid_results), reverse=True)][:top_k]
```

**기록**

| 항목 | 설정값 |
|------|--------|
| BM25 Retriever k | |
| Vector Retriever k | |
| Ensemble 가중치 (vector : BM25) | |
| Re-ranker 종류 및 모델명 | |
| Re-ranking 후 최종 Top-K | |

#### 2-4. Advanced RAG 정답률 측정

Golden Dataset 전체에 대해 Advanced RAG 파이프라인을 실행하고 정답률을 측정합니다.

**기록**

| 질문 ID | 난이도 | source_year | 검색 방식 | 검색 결과 포함 여부 | 올바른 년도 검색 여부 | Re-rank 후 순위 변화 | LLM 생성 답변 | 정답 여부 |
|---------|--------|-------------|----------|-------------------|-------------------|-------------------|-------------|----------|
| q01 | easy | 2025 | Hybrid | O/X | O/X | 예: 3위→1위 | | 정답/오답 |
| q02 | cross-year | 2025+2026 | Hybrid | O/X | O/X | | | 정답/오답 |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |
| **Advanced RAG 정답률** | | | | | | | | /N |

### Step 3: Basic RAG vs Advanced RAG 비교 분석

두 파이프라인의 성능을 비교하고, **왜** 차이가 나는지 분석합니다.

**3-1. 정답률 비교 테이블**

| 방식 | 전체 정답률 | easy 정답률 | medium 정답률 | hard 정답률 | cross-year 정답률 | 년도 검색 정확도 |
|------|-----------|-----------|-------------|-----------|-----------------|----------------|
| Basic RAG (벡터 검색만) | /N | /N | /N | /N | /N | /N |
| Advanced RAG (Hybrid + Re-ranking) | /N | /N | /N | /N | /N | /N |

**3-2. 문항별 변화 분석**

| 질문 ID | Basic RAG | Advanced RAG | 변화 | 변화 원인 분석 |
|---------|----------|-------------|------|-------------|
| q01 | 정답 | 정답 | 유지 | |
| q02 | 오답 | 정답 | 개선 | 예: BM25가 키워드 매칭으로 누락 청크를 보완 |
| q03 | 정답 | 오답 | 악화 | 예: Re-ranking이 관련 청크를 밀어냄 |
| ... | ... | ... | ... | ... |

**3-3. 기법별 기여도 분석** (선택이지만 권장)

Hybrid Search만 적용한 결과와 Hybrid + Re-ranking을 적용한 결과를 분리하여, 각 기법이 얼마나 기여했는지 확인합니다.

| 방식 | 정답률 |
|------|--------|
| Basic RAG (벡터만) | /N |
| + Hybrid Search (벡터 + BM25) | /N |
| + Hybrid Search + Re-ranking | /N |
| + 메타데이터 필터링 (적용 시) | /N |

## 구현 요구사항

### 필수

1. Step 1~3을 모두 구현하고 각 Step의 결과를 기록
2. 2025년, 2026년 두 PDF를 모두 인덱싱하여 벡터 저장소 구축 (각 청크에 `source_year` 메타데이터 포함)
3. 년도별 Golden Dataset 구축 (년도별 최소 10문제, 총 20문제 이상, `source_year` 필드 포함)
4. Hybrid Search (벡터 + BM25) 구현
5. Re-ranking (Cohere Rerank 또는 CrossEncoder) 구현
6. Golden Dataset 전체 문항에 대해 Basic RAG / Advanced RAG 정답률 측정 (년도 검색 정확도 포함)
7. 문항별 비교 분석 (어떤 문항이 개선/악화되었는지와 그 이유, 년도 혼동 분석 포함)

### 권장

- LangChain 또는 LlamaIndex 사용 (3주차에서 사용한 프레임워크 유지)
- Re-ranking: Cohere Rerank API (무료 티어로 충분) 또는 `bge-reranker-v2-m3` (오픈 모델, 다국어)
- 메타데이터 필터링을 활용한 년도 인식 검색 개선
- 교차 비교 문항(cross-year) 포함하여 다년도 검색 능력 평가
- Python 사용
- 기법별 기여도 분리 측정 (Step 3-3)

### 금지

- ChatGPT/Claude 웹 UI 사용

## 제출물

PR 하나로 아래를 제출합니다.

제출 위치
- 브랜치 생성 `week4/<GithubID>` 후 PR 등록

필수 파일
- `week-4/<GithubID>/`
- `golden_dataset.jsonl` (`source_year` 필드 포함, 년도별 최소 10문제)
- `README.md` (이론 과제 답변 + 실습 과제 결과 포함)
- 관련 코드 (참고용)

## README.md 필수 포함 항목

1. 사용한 프레임워크, 모델(LLM, 임베딩, Re-ranker), 실행 환경
2. 인덱싱 전략 — 두 년도 문서의 청킹 및 메타데이터 설정 방법
3. Golden Dataset 설계 — 년도별 문항 구성, 교차 비교 문항 설계 의도
4. Basic RAG 파이프라인 구성 — 프롬프트 템플릿(년도 인식), Retriever 설정, LLM 설정
5. Advanced RAG 파이프라인 구성 — Hybrid Search 설정, Re-ranking 설정, 메타데이터 필터링 적용 여부
6. Step 1 결과 — Basic RAG 정답률, 년도 검색 정확도, 2주차 대비 비교
7. Step 2 결과 — Advanced RAG 정답률, 년도 검색 개선 여부
8. Step 3 결과 — 비교 분석표, 문항별 분석, 년도 혼동 분석, 인사이트
9. 이론 과제 답변 (Hybrid Search, Re-ranking, 메타데이터 필터링과 컨텍스트 압축)

## 참고 자료

RAG 파이프라인
- [LangChain RAG Tutorial](https://python.langchain.com/docs/tutorials/rag/)
- [LangChain Retrievers How-to Guides](https://python.langchain.com/docs/how_to/#retrievers)

Hybrid Search
- [LangChain BM25Retriever](https://python.langchain.com/docs/integrations/retrievers/bm25/)
- [LangChain EnsembleRetriever](https://python.langchain.com/docs/how_to/ensemble_retriever/)
- [LlamaIndex BM25 Retriever](https://developers.llamaindex.ai/python/examples/retrievers/bm25_retriever/)
- [LlamaIndex Reciprocal Rerank Fusion](https://developers.llamaindex.ai/python/examples/retrievers/reciprocal_rerank_fusion/)
- [LlamaIndex Hybrid Search Alpha Tuning](https://www.llamaindex.ai/blog/llamaindex-enhancing-retrieval-performance-with-alpha-tuning-in-hybrid-search-in-rag-135d0c9b8a00)
- [BM25 알고리즘 설명 (Wikipedia)](https://en.wikipedia.org/wiki/Okapi_BM25)

Re-ranking
- [Cohere Rerank](https://docs.cohere.com/docs/reranking)
- [LangChain Cohere Reranker](https://python.langchain.com/docs/integrations/retrievers/cohere-reranker/)
- [Jina Reranker v3](https://jina.ai/models/jina-reranker-v3/)
- [BAAI bge-reranker-v2-m3 (Hugging Face)](https://huggingface.co/BAAI/bge-reranker-v2-m3)
- [sentence-transformers CrossEncoder](https://www.sbert.net/docs/cross_encoder/usage/usage.html)
- [Cross-encoder vs Bi-encoder 비교 (SBERT)](https://www.sbert.net/examples/applications/cross-encoder/README.html)
- [Reranker 벤치마크 비교](https://www.zeroentropy.dev/articles/ultimate-guide-to-choosing-the-best-reranking-model-in-2025)

메타데이터 필터링 & 컨텍스트 압축
- [LangChain Contextual Compression](https://python.langchain.com/docs/how_to/contextual_compression/)
- [LangChain Self-Query Retriever](https://python.langchain.com/docs/how_to/self_query/)
- [Chroma Metadata Filtering](https://docs.trychroma.com/guides)

## 힌트

- **인덱싱 시 메타데이터가 핵심입니다.** 각 청크에 `source_year`를 반드시 포함시키세요. 나중에 검색 결과가 어느 년도에서 왔는지 확인하고, 메타데이터 필터링을 적용하는 데 필수적입니다.
- **년도 혼동이 가장 큰 도전 과제입니다.** 2025년과 2026년 문서는 구조와 표현이 매우 유사합니다. 벡터 검색만으로는 올바른 년도의 청크를 구분하기 어렵습니다. 이것이 메타데이터 필터링과 Re-ranking이 필요한 이유입니다.
- **Basic RAG의 정답률이 낮아도 정상입니다.** 검색이 성공해도 LLM이 컨텍스트를 잘못 해석하거나, 프롬프트가 부정확하면 오답이 나옵니다. 특히 다른 년도의 정보를 참조하여 답변하는 경우가 빈번할 수 있습니다.
- **BM25는 정확한 키워드 매칭에 강합니다.** 벡터 검색이 의미는 비슷하지만 다른 표현을 찾아오는 반면, BM25는 "1종 수급권자", "틀니" 같은 정확한 용어가 포함된 청크를 직접 찾습니다. 의료 용어처럼 고유한 키워드가 많은 도메인에서 특히 효과적입니다.
- **Re-ranking은 "후보가 많을 때" 효과적입니다.** Hybrid Search로 충분한 후보(예: 10~20개)를 가져오고, Re-ranker로 상위 3~5개를 선별하는 구조가 일반적입니다.
- **Cohere Rerank 무료 티어는 월 1,000회입니다.** Golden Dataset 20문제를 여러 번 테스트해도 충분합니다. API 키는 https://dashboard.cohere.com 에서 발급받으세요.
- **교차 비교 문항은 난이도가 높습니다.** "2025년 대비 2026년에 달라진 점"을 묻는 문항은 두 년도의 청크를 모두 검색해야 하므로 RAG 시스템에 큰 도전이 됩니다. 이런 문항에서 성능이 낮은 것은 자연스러우며, 분석 자체가 학습 포인트입니다.
- **악화된 문항이 있으면 더 좋은 분석 기회입니다.** Advanced RAG가 항상 좋은 것은 아닙니다. Re-ranking이 오히려 관련 청크를 밀어내거나, BM25가 키워드만 겹치는 무관한 청크를 가져올 수 있습니다. 이런 케이스를 분석하는 것이 학습 포인트입니다.
- 이번 과제는 2주 기간입니다. Step 1을 먼저 완성하고, 그 다음 Step 2로 넘어가세요.
