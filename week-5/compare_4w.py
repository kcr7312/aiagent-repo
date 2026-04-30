from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_4W = BASE_DIR / "4outputs.zip"
DEFAULT_OUTPUT_5W = BASE_DIR / "outputs_ragas.zip"
DEFAULT_OUTPUT_DIR = BASE_DIR / "comparison_step2"


# =============================================================================
# 입력 유틸
# =============================================================================
def ask_value(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


# =============================================================================
# 기본 유틸
# =============================================================================
def read_jsonl_text(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return read_jsonl_text(text)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_float(v: Any) -> Any:
    try:
        if v is None:
            return None
        x = float(v)
        if math.isnan(x):
            return None
        return x
    except Exception:
        return None


def score_to_label(v: Any, threshold: float = 0.5) -> str:
    x = safe_float(v)
    if x is None:
        return "N/A"
    return "정답" if x >= threshold else "오답"


def bool_to_ox(v: Any) -> str:
    if v is True:
        return "일치"
    if v is False:
        return "불일치"
    return "N/A"


# =============================================================================
# ZIP / 폴더 로더
# =============================================================================
def read_jsonl_from_zip(zip_path: Path, member_name: str) -> List[Dict[str, Any]]:
    with zipfile.ZipFile(zip_path) as zf:
        text = zf.read(member_name).decode("utf-8")
    return read_jsonl_text(text)


def load_outputs_4w(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
        mapping = {
            "baseline": "baseline_eval_results.jsonl",
            "hybrid": "hybrid_eval_results.jsonl",
            "hybrid_rerank": "hybrid_rerank_eval_results.jsonl",
        }
        for key, filename in mapping.items():
            if filename not in names:
                raise FileNotFoundError(f"4주차 ZIP에 {filename} 이 없습니다.")
            result[key] = read_jsonl_from_zip(path, filename)
        return result

    mapping = {
        "baseline": path / "baseline_eval_results.jsonl",
        "hybrid": path / "hybrid_eval_results.jsonl",
        "hybrid_rerank": path / "hybrid_rerank_eval_results.jsonl",
    }
    for key, p in mapping.items():
        if not p.exists():
            raise FileNotFoundError(f"4주차 폴더에 {p.name} 이 없습니다.")
        result[key] = load_jsonl(p)
    return result


def load_outputs_5w(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())

        mapping = {
            "basic_scores": "basic_ragas_scores.jsonl",
            "advanced_scores": "advanced_ragas_scores.jsonl",
            "basic_traces": "basic_rag_run_traces.jsonl",
            "advanced_traces": "advanced_rag_run_traces.jsonl",
        }
        for key, filename in mapping.items():
            if filename not in names:
                raise FileNotFoundError(f"5주차 ZIP에 {filename} 이 없습니다.")
            result[key] = read_jsonl_from_zip(path, filename)
        return result

    mapping = {
        "basic_scores": path / "basic_ragas_scores.jsonl",
        "advanced_scores": path / "advanced_ragas_scores.jsonl",
        "basic_traces": path / "basic_rag_run_traces.jsonl",
        "advanced_traces": path / "advanced_rag_run_traces.jsonl",
    }
    for key, p in mapping.items():
        if not p.exists():
            raise FileNotFoundError(f"5주차 폴더에 {p.name} 이 없습니다.")
        result[key] = load_jsonl(p)
    return result


# =============================================================================
# 정규화 / 병합
# =============================================================================
def build_4w_table(outputs_4w: Dict[str, List[Dict[str, Any]]]) -> pd.DataFrame:
    frames = []
    for mode, rows in outputs_4w.items():
        df = pd.DataFrame(rows).copy()
        df["week4_mode"] = mode
        df = df.rename(
            columns={
                "question_id": "id",
                "generated_answer": f"w4_{mode}_generated_answer",
                "is_correct": f"w4_{mode}_is_correct",
                "retrieved_chunk_hit": f"w4_{mode}_retrieved_chunk_hit",
                "year_correct": f"w4_{mode}_year_correct",
                "error_reason": f"w4_{mode}_error_reason",
            }
        )
        keep_cols = [
            "id", "question", "difficulty", "source_year", "expected_answer",
            f"w4_{mode}_generated_answer",
            f"w4_{mode}_is_correct",
            f"w4_{mode}_retrieved_chunk_hit",
            f"w4_{mode}_year_correct",
            f"w4_{mode}_error_reason",
        ]
        available = [c for c in keep_cols if c in df.columns]
        frames.append(df[available])

    merged = frames[0]
    for other in frames[1:]:
        merged = merged.merge(
            other,
            on=[c for c in ["id", "question", "difficulty", "source_year", "expected_answer"] if c in merged.columns and c in other.columns],
            how="outer",
        )
    return merged


def build_5w_table(outputs_5w: Dict[str, List[Dict[str, Any]]]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    basic_df = pd.DataFrame(outputs_5w["basic_scores"]).copy()
    adv_df = pd.DataFrame(outputs_5w["advanced_scores"]).copy()

    basic_df = basic_df.rename(columns={"answer_relevancy": "response_relevancy"})
    adv_df = adv_df.rename(columns={"answer_relevancy": "response_relevancy"})

    metric_cols = [
        "context_recall",
        "llm_context_precision_with_reference",
        "faithfulness",
        "response_relevancy",
        "answer_correctness",
    ]

    base_meta = ["id", "question", "difficulty", "source_year", "category", "ground_truth", "response"]
    basic_keep = [c for c in base_meta + metric_cols if c in basic_df.columns]
    adv_keep = [c for c in base_meta + metric_cols if c in adv_df.columns]

    basic_df = basic_df[basic_keep].copy()
    adv_df = adv_df[adv_keep].copy()

    rename_basic = {c: f"basic_{c}" for c in metric_cols + ["response"]}
    rename_adv = {c: f"advanced_{c}" for c in metric_cols + ["response"]}

    basic_df = basic_df.rename(columns=rename_basic)
    adv_df = adv_df.rename(columns=rename_adv)

    merged = basic_df.merge(
        adv_df,
        on=["id", "question", "difficulty", "source_year", "category", "ground_truth"],
        how="outer",
    )
    return basic_df, merged


def build_overall_means(scores_merged: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metric_map = {
        "Context Recall": ("basic_context_recall", "advanced_context_recall"),
        "Context Precision": ("basic_llm_context_precision_with_reference", "advanced_llm_context_precision_with_reference"),
        "Faithfulness": ("basic_faithfulness", "advanced_faithfulness"),
        "Answer Relevancy": ("basic_response_relevancy", "advanced_response_relevancy"),
        "Answer Correctness": ("basic_answer_correctness", "advanced_answer_correctness"),
    }

    for metric_name, (b_col, a_col) in metric_map.items():
        b_mean = pd.to_numeric(scores_merged.get(b_col), errors="coerce").mean()
        a_mean = pd.to_numeric(scores_merged.get(a_col), errors="coerce").mean()
        rows.append(
            {
                "metric": metric_name,
                "basic": None if pd.isna(b_mean) else round(float(b_mean), 4),
                "advanced": None if pd.isna(a_mean) else round(float(a_mean), 4),
                "delta": None if (pd.isna(b_mean) or pd.isna(a_mean)) else round(float(a_mean - b_mean), 4),
            }
        )
    return pd.DataFrame(rows)


def build_representative_question_table(scores_merged: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "id",
        "difficulty",
        "source_year",
        "basic_context_recall",
        "advanced_context_recall",
        "basic_llm_context_precision_with_reference",
        "advanced_llm_context_precision_with_reference",
        "basic_faithfulness",
        "advanced_faithfulness",
        "basic_response_relevancy",
        "advanced_response_relevancy",
        "basic_answer_correctness",
        "advanced_answer_correctness",
    ]
    available = [c for c in cols if c in scores_merged.columns]
    df = scores_merged[available].copy()
    return df.sort_values(by=["id"]).reset_index(drop=True)


def build_manual_vs_ragas_table(outputs4_merged: pd.DataFrame, scores_merged: pd.DataFrame) -> pd.DataFrame:
    merged = outputs4_merged.merge(
        scores_merged,
        on=["id", "question", "difficulty", "source_year"],
        how="inner",
    )

    rows = []
    for _, row in merged.iterrows():
        w4_baseline = row.get("w4_baseline_is_correct")
        w4_hybrid = row.get("w4_hybrid_is_correct")
        w4_rerank = row.get("w4_hybrid_rerank_is_correct")

        b_score = safe_float(row.get("basic_answer_correctness"))
        a_score = safe_float(row.get("advanced_answer_correctness"))

        b_label = score_to_label(b_score)
        a_label = score_to_label(a_score)

        baseline_match = None
        if isinstance(w4_baseline, str) and b_label != "N/A":
            baseline_match = ((w4_baseline == "O" and b_label == "정답") or (w4_baseline == "X" and b_label == "오답"))

        hybrid_match = None
        if isinstance(w4_hybrid, str) and a_label != "N/A":
            hybrid_match = ((w4_hybrid == "O" and a_label == "정답") or (w4_hybrid == "X" and a_label == "오답"))

        rows.append(
            {
                "id": row["id"],
                "difficulty": row.get("difficulty"),
                "source_year": row.get("source_year"),
                "question": row.get("question"),
                "week4_baseline_judgement": w4_baseline,
                "week5_basic_answer_correctness": b_score,
                "week5_basic_label": b_label,
                "baseline_vs_basic_match": bool_to_ox(baseline_match),
                "week4_hybrid_judgement": w4_hybrid,
                "week5_advanced_answer_correctness": a_score,
                "week5_advanced_label": a_label,
                "hybrid_vs_advanced_match": bool_to_ox(hybrid_match),
                "week4_hybrid_rerank_judgement": w4_rerank,
                "week4_baseline_error_reason": row.get("w4_baseline_error_reason"),
                "week4_hybrid_error_reason": row.get("w4_hybrid_error_reason"),
                "week4_hybrid_rerank_error_reason": row.get("w4_hybrid_rerank_error_reason"),
                "notes": "",
            }
        )
    return pd.DataFrame(rows).sort_values(by=["id"]).reset_index(drop=True)


def build_summary_json(overall_means: pd.DataFrame, representative_df: pd.DataFrame, manual_vs_ragas_df: pd.DataFrame) -> Dict[str, Any]:
    return {
        "overall_means": overall_means.to_dict(orient="records"),
        "representative_question_count": int(len(representative_df)),
        "manual_vs_ragas_count": int(len(manual_vs_ragas_df)),
        "match_summary": {
            "baseline_vs_basic_일치": int((manual_vs_ragas_df["baseline_vs_basic_match"] == "일치").sum()) if "baseline_vs_basic_match" in manual_vs_ragas_df.columns else 0,
            "hybrid_vs_advanced_일치": int((manual_vs_ragas_df["hybrid_vs_advanced_match"] == "일치").sum()) if "hybrid_vs_advanced_match" in manual_vs_ragas_df.columns else 0,
        },
    }


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "(빈 표)"

    # tabulate 미설치 환경에서도 동작하도록 수동 markdown 테이블 생성
    cols = [str(c) for c in df.columns.tolist()]
    rows = []
    for _, row in df.iterrows():
        values = []
        for col in df.columns:
            v = row[col]
            if pd.isna(v):
                values.append("")
            else:
                values.append(str(v).replace("\n", " ").replace("|", "\\|"))
        rows.append(values)

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([header, sep] + body)


def build_step2_markdown(overall_means: pd.DataFrame, representative_df: pd.DataFrame, manual_vs_ragas_df: pd.DataFrame) -> str:
    text = []
    text.append("# Step 2 결과 초안")
    text.append("")
    text.append("## 2-2. 결과 기록 — 전체 평균")
    text.append("")
    text.append(markdown_table(overall_means))
    text.append("")
    text.append("## 2-2. 결과 기록 — 대표 문항별")
    text.append("")
    text.append(markdown_table(representative_df))
    text.append("")
    text.append("## 2-3. 4주차 수동/규칙 판정 vs 5주차 Ragas 비교")
    text.append("")
    text.append(markdown_table(manual_vs_ragas_df))
    text.append("")
    text.append("> 주의: 일부 문항에서는 특정 Ragas metric이 비어 있을 수 있으며, 평균은 산출 가능한 값 기준으로 계산했습니다.")
    return "\n".join(text)


def main() -> None:
    print("\n=== 4주차 / 5주차 비교 실행 설정 ===")
    output_4w = Path(ask_value("4주차 outputs 경로(zip 또는 폴더)", str(DEFAULT_OUTPUT_4W)))
    output_5w = Path(ask_value("5주차 outputs 경로(zip 또는 폴더)", str(DEFAULT_OUTPUT_5W)))
    output_dir = Path(ask_value("비교 결과 출력 폴더", str(DEFAULT_OUTPUT_DIR)))
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs_4w = load_outputs_4w(output_4w)
    outputs_5w = load_outputs_5w(output_5w)

    table_4w = build_4w_table(outputs_4w)
    _, table_5w_merged = build_5w_table(outputs_5w)

    overall_means = build_overall_means(table_5w_merged)
    representative_df = build_representative_question_table(table_5w_merged)
    manual_vs_ragas_df = build_manual_vs_ragas_table(table_4w, table_5w_merged)

    overall_means.to_csv(output_dir / "step2_overall_means.csv", index=False, encoding="utf-8-sig")
    representative_df.to_csv(output_dir / "step2_representative_questions.csv", index=False, encoding="utf-8-sig")
    manual_vs_ragas_df.to_csv(output_dir / "step2_manual_vs_ragas.csv", index=False, encoding="utf-8-sig")

    summary = build_summary_json(overall_means, representative_df, manual_vs_ragas_df)
    save_json(output_dir / "step2_summary.json", summary)

    markdown = build_step2_markdown(overall_means, representative_df, manual_vs_ragas_df)
    save_markdown(output_dir / "step2_tables.md", markdown)

    print("\nSaved files:")
    print(output_dir / "step2_overall_means.csv")
    print(output_dir / "step2_representative_questions.csv")
    print(output_dir / "step2_manual_vs_ragas.csv")
    print(output_dir / "step2_summary.json")
    print(output_dir / "step2_tables.md")


if __name__ == "__main__":
    main()
