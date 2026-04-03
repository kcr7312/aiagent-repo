from __future__ import annotations

import json
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS


BASE_DIR = Path(__file__).resolve().parent
PDF_PATH = BASE_DIR / "data" / "2024_알기_쉬운_의료급여제도.pdf"
INDEX_DIR = BASE_DIR / "vectorstore" / "faiss_index"
CHUNK_INFO_PATH = BASE_DIR / "vectorstore" / "chunk_stats.json"


def load_documents(pdf_path: Path):
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF 파일을 찾을 수 없습니다.\n"
            f"찾은 경로: {pdf_path}\n"
            f"'build_index.py' 기준으로 data 폴더 아래에 PDF를 두세요."
        )

    loader = PyPDFLoader(str(pdf_path))
    docs = loader.load()

    # 페이지 번호를 metadata에 명시적으로 정리
    for i, doc in enumerate(docs):
        page = doc.metadata.get("page", i)
        doc.metadata["page"] = int(page) + 1  # 사람이 보기 쉽게 1-index
        doc.metadata["source_file"] = pdf_path.name

    return docs


def split_documents(docs):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", "Q", "A", "•", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = idx

    return chunks


def build_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )


def save_faiss(chunks, embeddings, index_dir: Path):
    vectorstore = FAISS.from_documents(chunks, embeddings)
    index_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(index_dir))
    return vectorstore


def export_chunk_stats(chunks, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for c in chunks:
        text = c.page_content[:300].replace("\n", " ")
        rows.append({
            "chunk_id": c.metadata["chunk_id"],
            "page": c.metadata.get("page"),
            "chars": len(c.page_content),
            "preview": text,
        })

    payload = {
        "total_chunks": len(chunks),
        "chunk_size": 800,
        "chunk_overlap": 150,
        "samples": rows[:10],
    }

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def main():
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"PDF_PATH: {PDF_PATH}")
    print(f"PDF exists: {PDF_PATH.exists()}")

    docs = load_documents(PDF_PATH)
    chunks = split_documents(docs)
    embeddings = build_embeddings()
    save_faiss(chunks, embeddings, INDEX_DIR)
    export_chunk_stats(chunks, CHUNK_INFO_PATH)

    print(f"pages loaded: {len(docs)}")
    print(f"chunks created: {len(chunks)}")
    print(f"index saved to: {INDEX_DIR}")
    print(f"chunk stats saved to: {CHUNK_INFO_PATH}")


if __name__ == "__main__":
    main()