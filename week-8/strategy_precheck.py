import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


PERCENT_ENCODING_RE = re.compile(r"%[0-9A-Fa-f]{2}")
COMMON_URL_ENCODED_TOKENS = {
    "%24": "$",
    "%7b": "{",
    "%7d": "}",
    "%3a": ":",
    "%2f": "/",
    "%3d": "=",
    "%26": "&",
    "%3f": "?",
    "%25": "%",
}


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



def _candidate_text_blob(candidate: Dict[str, Any]) -> str:
    """
    Build a compact text blob for lightweight URL/percent-encoding detection.
    This intentionally looks across the whole candidate object because different
    upstream tools may store suspicious values in raw, decoded_preview,
    normalized_payload, nested_candidates, residue_signals, or custom fields.
    """
    try:
        return json.dumps(candidate, ensure_ascii=False)
    except Exception:
        return str(candidate)


def find_url_encoding_signals(candidate: Dict[str, Any]) -> List[str]:
    blob = _candidate_text_blob(candidate)
    matches = PERCENT_ENCODING_RE.findall(blob)
    if not matches:
        return []

    signals: List[str] = []
    lowered = blob.lower()

    for token in sorted(set(m.lower() for m in matches)):
        if token in COMMON_URL_ENCODED_TOKENS:
            signals.append(f"{token}->{COMMON_URL_ENCODED_TOKENS[token]}")
        else:
            signals.append(token)

    if "%2524" in lowered or "%257b" in lowered or "%253a" in lowered:
        signals.append("possible_double_url_encoding")

    if "%24%7b" in lowered or "%7bjndi" in lowered or "jndi%3a" in lowered:
        signals.append("possible_url_encoded_log4shell")

    return signals[:20]


def is_url_encoded_candidate(candidate: Dict[str, Any]) -> bool:
    signals = find_url_encoding_signals(candidate)
    if not signals:
        return False

    # Avoid treating a single harmless percent escape as a high-confidence case.
    blob = _candidate_text_blob(candidate)
    match_count = len(PERCENT_ENCODING_RE.findall(blob))
    lowered = blob.lower()

    if match_count >= 2:
        return True
    if any(marker in lowered for marker in ["%24%7b", "%7bjndi", "jndi%3a", "%2524%257b"]):
        return True
    return False


def summarize_url_encoded_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    summary = summarize_candidate(candidate)
    summary["url_encoding_signals"] = find_url_encoding_signals(candidate)
    return summary


def collect_url_encoded_candidates(
    decoded_candidates: List[Dict[str, Any]],
    failed_candidates: List[Dict[str, Any]],
    residue_candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    seen = set()

    for source_bucket, candidates in [
        ("decoded_candidates", decoded_candidates),
        ("failed_candidates", failed_candidates),
        ("residue_candidates", residue_candidates),
    ]:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if not is_url_encoded_candidate(candidate):
                continue

            key = (
                source_bucket,
                candidate.get("segment_no"),
                candidate.get("stream_key"),
                candidate.get("position"),
                candidate.get("raw"),
                candidate.get("decoded_preview"),
                candidate.get("normalized_payload"),
            )
            key_text = json.dumps(key, ensure_ascii=False, sort_keys=True)
            if key_text in seen:
                continue
            seen.add(key_text)

            item = dict(candidate)
            item["_source_bucket"] = source_bucket
            collected.append(item)

    return collected


def build_llm_review_prompt(
    *,
    completion_status: str,
    reason: str,
    decoded_preview: List[Dict[str, Any]],
    failed_preview: List[Dict[str, Any]],
    residue_preview: List[Dict[str, Any]],
    url_encoded_preview: List[Dict[str, Any]],
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
        f"URL-encoded candidates preview:\n{json.dumps(url_encoded_preview, ensure_ascii=False, indent=2)}\n\n"
        "URL-encoded routing guidance:\n"
        "- If URL-encoded candidates preview is not empty, prefer decision = call_other_tool.\n"
        "- In that case, set recommended_tool = url_decode_tool.\n"
        "- Use recommended_options such as recursive=true, max_depth=2, plus_as_space=true, deduplicate=true.\n"
        "- Do not use noise_cleanup_tool for percent-encoded URI/query/header values unless the issue is actually base64 suffix noise.\n\n"
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

    url_encoded_candidates = collect_url_encoded_candidates(
        decoded_candidates=decoded_candidates,
        failed_candidates=failed_candidates,
        residue_candidates=residue_candidates,
    )
    has_url_encoded = len(url_encoded_candidates) > 0

    # URL/percent-encoded 후보는 기존 base64 noise cleanup과 다른 tool family로 라우팅한다.
    # 이 분기는 llm_agent.py가 call_other_tool + url_decode_tool을 선택하도록 프롬프트에 신호를 준다.
    if has_url_encoded:
        return {
            "file_status": "pending",
            "decision": "ai_review_required",
            "needs_llm_review": True,
            "completion_status": "url_encoded_candidate_detected",
            "reason": "URL/percent-encoded payload candidates were detected and should be reviewed with url_decode_tool.",
            "required_next_action": "review_url_encoded_candidates",
            "recommended_tool_hint": "url_decode_tool",
        }

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

    url_encoded_candidates = collect_url_encoded_candidates(
        decoded_candidates=decoded_candidates,
        failed_candidates=failed_candidates,
        residue_candidates=residue_candidates,
    )

    decoded_preview = [summarize_candidate(c) for c in decoded_candidates[:5]]
    failed_preview = [summarize_candidate(c) for c in failed_candidates[:5]]
    residue_preview = [summarize_candidate(c) for c in residue_candidates[:5]]
    url_encoded_preview = [summarize_url_encoded_candidate(c) for c in url_encoded_candidates[:5]]

    llm_prompt = None
    if classification["needs_llm_review"]:
        llm_prompt = build_llm_review_prompt(
            completion_status=classification["completion_status"],
            reason=classification["reason"],
            decoded_preview=decoded_preview,
            failed_preview=failed_preview,
            residue_preview=residue_preview,
            url_encoded_preview=url_encoded_preview,
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
            "url_encoded_candidates": len(url_encoded_candidates),
            "excluded_streams": len(excluded_streams),
            "checked_streams": data.get("checked_streams"),
            "checked_segments": data.get("checked_segments"),
        },
        "decoded_candidates_preview": decoded_preview,
        "failed_candidates_preview": failed_preview,
        "residue_candidates_preview": residue_preview,
        "url_encoded_candidates_preview": url_encoded_preview,
        "excluded_streams": excluded_streams,
        "recommended_tool_hint": classification.get("recommended_tool_hint"),
        "tool_routing_hints": {
            "url_decode_tool": {
                "enabled": len(url_encoded_candidates) > 0,
                "reason": "Use when percent-encoded URI/query/header/payload candidates are present.",
                "preferred_decision": "call_other_tool",
                "default_options": {
                    "recursive": True,
                    "max_depth": 2,
                    "plus_as_space": True,
                    "deduplicate": True,
                },
            }
        },
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
            "recommended_tool_hint": strategy_payload.get("recommended_tool_hint"),
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