# 4주차 이론 과제: Advanced RAG — Hybrid Search, Re-ranking, 메타데이터 필터링

## 개요

3주차에서 구축한 RAG Indexing 파이프라인에 Generation을 연결하여 end-to-end RAG를 완성하고, Naive RAG의 검색 한계를 넘어서는 Advanced RAG 기법을 학습합니다. 이론 과제에서는 Hybrid Search, Re-ranking, 메타데이터 필터링/컨텍스트 압축을 조사하고, 실습에서는 다년도 문서(2025/2026)를 다루는 RAG 시스템을 직접 구축합니다.

### Advanced RAG란?

RAG의 검색 성능을 한층 더 끌어올리기 위해 등장한 것이 Advanced RAG입니다. Gao et al.(2024)의 분류에 따르면 RAG는 다음과 같은 세 단계로 진화해왔습니다.

```
Naive RAG ──→ Advanced RAG ──→ Modular RAG
기본 검색 + 생성    검색 전/후 처리 추가    모듈 자유 조합
```

| 단계 | 핵심 특징 | 한계 |
|------|----------|------|
| **Naive RAG** | 질문을 벡터화하여 유사 문서를 검색하고 LLM에 전달하는 단순 파이프라인 | 검색 정밀도/재현율 부족, 키워드 매칭 실패, 도메인 용어 처리 취약 |
| **Advanced RAG** | 검색 **전**(Pre-Retrieval)에 쿼리 확장·재작성·HyDE 등을 적용하고, 검색 **후**(Post-Retrieval)에 재순위화·압축·필터링으로 결과를 정제 | Naive RAG 대비 복잡도 증가, 추가 모델/API 비용 발생 |
| **Modular RAG** | 검색·메모리·융합·라우팅·스케줄링 등 독립 모듈을 태스크에 맞게 자유롭게 조합 | 설계 복잡도 높음, 모듈 간 인터페이스 설계 필요 |

이번 4주차 과제는 **Naive RAG → Advanced RAG** 단계에 해당합니다. 구체적으로 Pre-Retrieval 단계에서 **Hybrid Search**(벡터 검색 + BM25 키워드 검색 결합)를, Post-Retrieval 단계에서 **Re-ranking**(Cross-encoder 기반 재순위화)을 적용하여, 기본 벡터 검색만으로는 해결하기 어려운 검색 품질 문제를 개선합니다.

## 필수 조사 항목

### 1. Hybrid Search란?

- Hybrid Search의 정의: 벡터 검색(Semantic Search)과 키워드 검색(BM25)을 결합하는 방식
- 왜 벡터 검색만으로 부족한지 — 벡터 검색이 놓치는 케이스 (정확한 키워드 매칭 실패, 도메인 용어 처리)
- BM25 알고리즘의 핵심 원리 (TF-IDF 기반, 정확한 토큰 매칭)
- 벡터 검색과 BM25 검색의 장단점 비교

| 검색 방식 | 강점 | 약점 |
|----------|------|------|
| 벡터 검색 (Semantic) | | |
| BM25 (Keyword) | | |
| Hybrid (결합) | | |

- 결합 방식: 가중치 기반 병합, Reciprocal Rank Fusion(RRF) 등

참고 자료:
- [LangChain EnsembleRetriever](https://python.langchain.com/docs/how_to/ensemble_retriever/)
- [Pinecone — Hybrid Search 설명](https://www.pinecone.io/learn/hybrid-search-intro/)
- [BM25 알고리즘 (Wikipedia)](https://en.wikipedia.org/wiki/Okapi_BM25)

### 2. Re-ranking이란?

- Re-ranking의 정의와 RAG 파이프라인에서의 위치 (Retrieval과 Generation 사이)
- Cross-encoder vs Bi-encoder 차이를 아래 관점에서 비교

| 구분 | Bi-encoder | Cross-encoder |
|------|-----------|---------------|
| 입력 방식 | 질문과 문서를 **각각** 인코딩 | 질문과 문서를 **함께** 인코딩 |
| 속도 | | |
| 정확도 | | |
| 사용 위치 | | |

- 왜 Cross-encoder를 검색 단계가 아닌 Re-ranking 단계에서 사용하는지 (속도 vs 정확도 트레이드오프)
- Two-stage retrieval 패턴: Bi-encoder로 후보 선별 → Cross-encoder로 재정렬
- 상용 Re-ranking API: Cohere Rerank의 동작 방식과 장점

참고 자료:
- [SBERT — Cross-encoder vs Bi-encoder](https://www.sbert.net/examples/applications/cross-encoder/README.html)
- [Cohere Rerank 개념 설명](https://docs.cohere.com/docs/reranking)
- [sentence-transformers CrossEncoder 문서](https://www.sbert.net/docs/cross_encoder/usage/usage.html)

### 3. 메타데이터 필터링과 컨텍스트 압축

Advanced RAG에서는 검색 결과의 양보다 질이 중요합니다. 아래 두 가지 Post-Retrieval 기법을 조사하세요.

| 기법 | 조사 내용 |
|------|----------|
| 메타데이터 필터링 | 청크에 포함된 메타데이터(출처, 날짜, 카테고리 등)를 기반으로 검색 범위를 제한하는 기법. 다년도 문서나 다중 소스 RAG에서 특히 중요 |
| Contextual Compression | 검색된 청크에서 질문과 관련 있는 부분만 추출하여 LLM에게 전달하는 기법. 불필요한 정보를 제거하여 LLM의 답변 정확도를 향상 |

각 기법별로 아래를 포함해주세요.
- **한 줄 정의**
- **왜 필요한지**: 이 기법이 없으면 어떤 문제가 발생하는지
- **구현 방식 예시**: LangChain 또는 LlamaIndex에서 어떻게 구현하는지

참고 자료:
- [Chroma Metadata Filtering](https://docs.trychroma.com/guides)

## 실습 과제 예측

실습 과제(TASK.md)를 보고, 실습 전에 아래 가설을 세워주세요.

1. 2025년과 2026년 문서를 동시에 인덱싱했을 때, 년도 혼동이 가장 많이 발생할 질문 유형을 예측하세요
2. Hybrid Search가 가장 효과를 볼 질문 유형을 예측하세요 (예: 특정 의료 용어가 포함된 질문 vs 일반적 표현의 질문)
3. Re-ranking이 결과를 개선할지, 또는 오히려 악화시킬 수 있는 경우가 있을지 예측하세요
4. 메타데이터 필터링이 년도 혼동 문제를 얼마나 해결할 수 있을지 예측하세요

> 실습 후에 가설과 실제 결과를 비교하여 본인의 제출 README(`week-4/<GithubID>/README.md`)에 포함하여 제출합니다.

## 추가 참고 자료

Advanced RAG 전체 흐름
- [RAG Survey (Gao et al., 2024)](https://arxiv.org/abs/2312.10997) — Naive / Advanced / Modular RAG 분류
- [Advanced RAG Techniques (LlamaIndex)](https://docs.llamaindex.ai/en/stable/optimizing/advanced_retrieval/)
- [Chunkviz — 청킹 전략 시각화 도구](https://chunkviz.up.railway.app/)

한국어 임베딩/리랭킹
- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) — 다국어 임베딩 성능 벤치마크
- Hugging Face에서 "korean cross-encoder" 검색

## 제출 형식

- 제출 README(`week-4/<GithubID>/README.md`)에 이론 과제 답변 포함
- 실습 과제 결과와 함께 제출
- 가설은 실습 전/후 비교 포함
