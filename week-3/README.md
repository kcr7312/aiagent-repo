# 3주차 이론 과제: RAG의 구성 요소

## 개요

이번 과제에서는 RAG(Retrieval-Augmented Generation)가 무엇이고, 어떤 구성 요소로 이루어져 있는지를 조사합니다. 실습에서 LangChain 기반 RAG 파이프라인을 직접 구현하기 위한 사전 지식을 갖추는 것이 목적입니다.

## 필수 조사 항목

### 1. RAG란?

- RAG의 정의와 왜 필요한지
- 2주차(system prompt에 전체 데이터 삽입)와 RAG 방식의 차이
- RAG 파이프라인의 전체 흐름: Indexing(문서 → 청크 → 벡터 → 저장) + Retrieval(질문 → 검색 → 생성)

참고 자료:
- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)
- [RAG Survey (Gao et al., 2024)](https://arxiv.org/abs/2312.10997)

### 2. RAG에서 사용되는 용어

아래 용어를 각각 한 줄 정의와 함께 정리하세요.

| 용어 | 조사 내용 |
|------|----------|
| Chunking | 문서를 분할하는 방법. chunk_size, chunk_overlap의 역할 |
| Embedding | 텍스트를 벡터로 변환하는 방법. 주요 임베딩 모델 비교 |
| Vector Store | 벡터를 저장하고 유사도 검색하는 저장소. FAISS, Chroma 등 |
| Retriever | 질문과 유사한 청크를 검색하는 컴포넌트. Top-K의 의미 |
| Generation | 검색된 청크를 바탕으로 LLM이 답변을 생성하는 단계 |

참고 자료:
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [FAISS Getting Started](https://github.com/facebookresearch/faiss/wiki/Getting-started)
- [Chroma Getting Started](https://docs.trychroma.com/getting-started)

### 3. 외부 데이터 소스 기반 응답 생성

- LLM 단독 응답 vs 외부 데이터를 검색하여 응답하는 방식의 차이
- API 호출 흐름: 질문 → 임베딩 → 벡터 검색 → 컨텍스트 구성 → LLM 호출
- 할루시네이션 방지에서 RAG가 하는 역할

### 4. LangChain 기반 RAG 파이프라인 구조

LangChain 공식 RAG Tutorial을 읽고, 파이프라인의 각 단계에서 사용되는 컴포넌트를 정리하세요.

| 단계 | LangChain 컴포넌트 |
|------|-------------------|
| 문서 로딩 | Document Loader (PyPDFLoader 등) |
| 청킹 | Text Splitter (RecursiveCharacterTextSplitter 등) |
| 임베딩 | Embeddings (OpenAIEmbeddings 등) |
| 벡터 저장 | Vector Store (FAISS, Chroma 등) |
| 검색 + 생성 | Retriever + Chain |

참고 자료:
- [LangChain RAG Tutorial](https://python.langchain.com/docs/tutorials/rag/)
- [LlamaIndex Starter Tutorial](https://docs.llamaindex.ai/en/stable/getting_started/starter_example/)

## 실습 과제 예측

실습 과제(TASK.md)와 의료급여 PDF를 보고, 실습 전에 아래 가설을 세워주세요.

1. 의료급여 PDF를 청킹할 때 가장 큰 어려움이 무엇일지 예측하세요
2. Golden Dataset의 5문제 중 어떤 난이도의 질문에서 검색 실패가 많을지 예측하고 이유를 설명하세요

> 실습 후에 가설과 실제 결과를 비교하여 본인의 제출 README(`week-3/<GithubID>/README.md`)에 포함하여 제출합니다.

## 제출 형식

- 제출 README(`week-3/<GithubID>/README.md`)에 이론 과제 답변 포함
- 실습 과제 결과와 함께 제출
- 가설은 실습 전/후 비교 포함
