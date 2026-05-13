import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_decoded_files(input_dir: Path) -> List[Path]:
    return sorted(input_dir.glob("*_decoded.json"))


def strip_status_suffix(stem: str) -> str:
    for suffix in [".pending", ".done", ".failed"]:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def build_strategy_output_path(decoded_file: Path, output_dir: Path, status_suffix: str) -> Path:
    """
    예:
    04_sample_xxx_decoded.json
    -> 04_sample_xxx_strategy.pending.json
    """
    stem = decoded_file.stem
    stem = strip_status_suffix(stem)

    if stem.endswith("_decoded"):
        stem = stem[:-8]

    return output_dir / f"{stem}_strategy.{status_suffix}.json"


def summarize_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "segment_no": candidate.get("segment_no"),
        "stream_key": candidate.get("stream_key"),
        "protocol": candidate.get("protocol"),
        "position": candidate.get("position"),
        "source": candidate.get("source"),
        "candidate_type": candidate.get("candidate_type"),
        "decode_status": candidate.get("decode_status"),
        "raw": candidate.get("raw"),
        "decoded_preview": candidate.get("decoded_preview"),
        "normalized_payload": candidate.get("normalized_payload"),
        "residue_signals": candidate.get("residue_signals", []),
        "nested_candidates": candidate.get("nested_candidates", []),
    }


def build_llm_review_prompt(
    *,
    completion_status: str,
    reason: str,
    decoded_preview: List[Dict[str, Any]],
    failed_preview: List[Dict[str, Any]],
    residue_preview: List[Dict[str, Any]],
    excluded_streams: List[Dict[str, Any]],
) -> str:
    return (
        "You are reviewing decoded packet analysis results.\n"
        "Do NOT do broad malware commentary.\n"
        "Your task is only to decide whether additional decode verification is needed,\n"
        "and whether the case should be classified as stop, retry_same_tool, call_other_tool,\n"
        "or stop_with_exclusion.\n\n"
        f"Current completion_status: {completion_status}\n"
        f"Reason: {reason}\n\n"
        f"Decoded candidates preview:\n{json.dumps(decoded_preview, ensure_ascii=False, indent=2)}\n\n"
        f"Failed candidates preview:\n{json.dumps(failed_preview, ensure_ascii=False, indent=2)}\n\n"
        f"Residue candidates preview:\n{json.dumps(residue_preview, ensure_ascii=False, indent=2)}\n\n"
        f"Excluded streams:\n{json.dumps(excluded_streams, ensure_ascii=False, indent=2)}\n\n"
        "Return JSON only with fields:\n"
        "{decision, completion_status, requires_additional_verification, reason, recommended_tool, recommended_options}\n"
    )


def classify_decoded(decoded_obj: Dict[str, Any]) -> Dict[str, Any]:
    data = decoded_obj.get("data") or {}

    status = data.get("status")
    decoded_candidates = data.get("decoded_candidates", []) or []
    failed_candidates = data.get("failed_candidates", []) or []
    residue_candidates = data.get("residue_candidates", []) or []
    excluded_streams = data.get("excluded_streams", []) or []

    has_decoded = len(decoded_candidates) > 0
    has_failed = len(failed_candidates) > 0
    has_residue = len(residue_candidates) > 0
    has_excluded = len(excluded_streams) > 0

    # 완전 실패
    if status == "no_encoding_candidate":
        return {
            "file_status": "done",
            "decision": "stop",
            "needs_llm_review": False,
            "completion_status": "no_candidate",
            "reason": "No encoding candidate was detected.",
            "required_next_action": None,
        }

    # decode 안 됐는데 실패 후보만 있음
    if not has_decoded and has_failed:
        return {
            "file_status": "pending",
            "decision": "ai_review_required",
            "needs_llm_review": True,
            "completion_status": "decode_failed",
            "reason": "No decoded candidates exist, but failed candidates remain and require retry strategy review.",
            "required_next_action": "review_failed_candidates",
        }

    # residue 남음
    if has_residue:
        return {
            "file_status": "pending",
            "decision": "ai_review_required",
            "needs_llm_review": True,
            "completion_status": "decode_success_with_residue",
            "reason": "Decoded candidates exist, but residue candidates remain and require additional verification.",
            "required_next_action": "review_residue_candidates",
        }

    # partial + exclusion
    if has_decoded and has_excluded:
        return {
            "file_status": "pending",
            "decision": "ai_review_required",
            "needs_llm_review": True,
            "completion_status": "partial_excluded",
            "reason": "Visible payload was decoded, but related encrypted/excluded streams remain.",
            "required_next_action": "reclassify_as_partial_excluded",
        }

    # 성공했지만 failed artifact 남음
    if has_decoded and has_failed:
        return {
            "file_status": "pending",
            "decision": "ai_review_required",
            "needs_llm_review": True,
            "completion_status": "decoded_with_failed_artifacts",
            "reason": "Primary decoding succeeded, but failed candidates remain and should be checked as noise, truncation, or retry target.",
            "required_next_action": "review_failed_candidates",
        }

    # 정상 종료
    if has_decoded:
        return {
            "file_status": "done",
            "decision": "stop",
            "needs_llm_review": False,
            "completion_status": "sufficient_within_scope",
            "reason": "Decoded candidates exist and no residue or excluded streams remain.",
            "required_next_action": None,
        }

    return {
        "file_status": "pending",
        "decision": "ai_review_required",
        "needs_llm_review": True,
        "completion_status": "unknown_state",
        "reason": "Unclassified decoded state requires manual or AI-assisted review.",
        "required_next_action": "manual_review",
    }


def build_strategy_payload(decoded_file: Path, decoded_obj: Dict[str, Any]) -> Dict[str, Any]:
    data = decoded_obj.get("data") or {}
    classification = classify_decoded(decoded_obj)

    decoded_candidates = data.get("decoded_candidates", []) or []
    failed_candidates = data.get("failed_candidates", []) or []
    residue_candidates = data.get("residue_candidates", []) or []
    excluded_streams = data.get("excluded_streams", []) or []

    decoded_preview = [summarize_candidate(c) for c in decoded_candidates[:5]]
    failed_preview = [summarize_candidate(c) for c in failed_candidates[:5]]
    residue_preview = [summarize_candidate(c) for c in residue_candidates[:5]]

    llm_prompt = None
    if classification["needs_llm_review"]:
        llm_prompt = build_llm_review_prompt(
            completion_status=classification["completion_status"],
            reason=classification["reason"],
            decoded_preview=decoded_preview,
            failed_preview=failed_preview,
            residue_preview=residue_preview,
            excluded_streams=excluded_streams,
        )

    return {
        "ok": True,
        "input": str(decoded_file),
        "decision": classification["decision"],
        "needs_llm_review": classification["needs_llm_review"],
        "completion_status": classification["completion_status"],
        "reason": classification["reason"],
        "required_next_action": classification["required_next_action"],
        "decoded_status": data.get("status"),
        "counts": {
            "decoded_candidates": len(decoded_candidates),
            "failed_candidates": len(failed_candidates),
            "residue_candidates": len(residue_candidates),
            "excluded_streams": len(excluded_streams),
            "checked_streams": data.get("checked_streams"),
            "checked_segments": data.get("checked_segments"),
        },
        "decoded_candidates_preview": decoded_preview,
        "failed_candidates_preview": failed_preview,
        "residue_candidates_preview": residue_preview,
        "excluded_streams": excluded_streams,
        "llm_review_prompt": llm_prompt,
        "error": None,
    }


def process_decoded_file(decoded_file: Path, output_dir: Path) -> Dict[str, Any]:
    try:
        decoded_obj = load_json(decoded_file)
        strategy_payload = build_strategy_payload(decoded_file, decoded_obj)
        file_status = "pending" if strategy_payload["needs_llm_review"] else "done"

        output_path = build_strategy_output_path(decoded_file, output_dir, file_status)

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(strategy_payload, f, ensure_ascii=False, indent=2)

        return {
            "input": str(decoded_file),
            "output": str(output_path),
            "status": file_status,
            "decision": strategy_payload["decision"],
            "completion_status": strategy_payload["completion_status"],
            "needs_llm_review": strategy_payload["needs_llm_review"],
        }

    except Exception as e:
        output_path = build_strategy_output_path(decoded_file, output_dir, "failed")
        error_payload = {
            "ok": False,
            "input": str(decoded_file),
            "error": {
                "code": "STRATEGY_PRECHECK_ERROR",
                "message": str(e),
            },
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(error_payload, f, ensure_ascii=False, indent=2)

        return {
            "input": str(decoded_file),
            "output": str(output_path),
            "status": "failed",
            "decision": None,
            "completion_status": None,
            "needs_llm_review": None,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        default=r".\data\decoded",
        help="Directory containing *_decoded.json files (default: .\\data\\decoded)",
    )
    parser.add_argument(
        "--output-dir",
        default=r".\data\strategy",
        help="Directory for *_strategy.<status>.json outputs (default: .\\data\\strategy)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists():
        print(json.dumps({
            "ok": False,
            "error": {
                "code": "STRATEGY_PRECHECK_ERROR",
                "message": f"input directory not found: {str(input_dir)}",
            }
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    decoded_files = iter_decoded_files(input_dir)

    if not decoded_files:
        print(json.dumps({
            "ok": True,
            "message": "No *_decoded.json files found.",
            "processed_files": 0,
        }, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    summary = [process_decoded_file(f, output_dir) for f in decoded_files]

    print(json.dumps({
        "ok": True,
        "processed_files": len(summary),
        "results": summary,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()