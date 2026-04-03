from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings


BASE_DIR = Path(__file__).resolve().parent
INDEX_DIR = BASE_DIR / "vectorstore" / "faiss_index"
GOLDEN_PATH = BASE_DIR / "golden_dataset.jsonl"
OUTPUT_PATH = BASE_DIR / "retrieval_eval_results.json"


def normalize_text(s: str) -> str:
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def load_embeddings():
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )


def load_golden(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def main():
    embeddings = load_embeddings()
    db = FAISS.load_local(
        str(INDEX_DIR),
        embeddings,
        allow_dangerous_deserialization=True,
    )

    golden = load_golden(GOLDEN_PATH)

    results = []
    hit_count = 0

    for i, item in enumerate(golden, start=1):
        question = item["question"]
        evidence = normalize_text(item["evidence_text"])

        docs = db.similarity_search(question, k=3)

        retrieved = []
        final_hit = False

        for rank, doc in enumerate(docs, start=1):
            raw_text = doc.page_content
            text = normalize_text(raw_text)

            matched = evidence in text
            if matched:
                final_hit = True

            retrieved.append({
                "rank": rank,
                "page": doc.metadata.get("page"),
                "chunk_id": doc.metadata.get("chunk_id"),
                "evidence_hit": matched,
                "preview": text[:300],
            })

        if final_hit:
            hit_count += 1

        results.append({
            "question_id": f"Q{i}",
            "question": question,
            "final_hit": final_hit,
            "retrieved": retrieved,
        })

    payload = {
        "summary": {
            "total_questions": len(golden),
            "hit_count": hit_count,
            "fail_count": len(golden) - hit_count,
            "top_k": 3,
            "success_rate": round(hit_count / len(golden), 4) if golden else 0.0,
        },
        "results": results,
    }

    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()