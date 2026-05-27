#!/usr/bin/env python3
r"""
retry_encoding.py

LLM Agent workflow에서 noise_cleanup_tool 이후 normalized_candidates를 실제 재디코딩하는 retry tool.

역할
- data/strategy/*.pending.json 중 required_next_action == run_encoding_decode_tool 인 파일을 처리한다.
- pending 파일 내부의 normalized_candidates / best_normalized_candidates를 읽는다.
- base64 디코딩 가능한 후보를 재검증한다.
- 가장 적절한 후보를 선택한다.
- 성공 시 원본 .pending.json 파일을 .done.json으로 전환한다.
- 실패 시 원본 .pending.json을 유지하고 needs_llm_review=true로 되돌릴 수 있다.

중요
- encoding_decode_tool.py는 최초 segments 디코딩 전용으로 유지한다.
- retry_encoding.py는 strategy pending 전용 후속 retry tool이다.
- llm_agent.py가 다음 배치에서 required_next_action을 보고 이 스크립트를 호출할 예정이다.

실행 예시
    py .\retry_encoding.py

단일 파일 처리
    py .\retry_encoding.py --strategy-file .\data\strategy\01_sample_packet_ldap-basic-auth-ev1_strategy.pending.json

dry-run
    py .\retry_encoding.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_STRATEGY_DIR = Path(r".\data\strategy")


# -----------------------------------------------------------------------------
# JSON helpers
# -----------------------------------------------------------------------------


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return obj


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


# -----------------------------------------------------------------------------
# Path helpers
# -----------------------------------------------------------------------------


def replace_status_suffix(path: Path, new_status: str) -> Path:
    name = path.name
    if ".pending.json" in name:
        name = name.replace(".pending.json", f".{new_status}.json")
    elif ".done.json" in name:
        name = name.replace(".done.json", f".{new_status}.json")
    elif ".failed.json" in name:
        name = name.replace(".failed.json", f".{new_status}.json")
    else:
        name = f"{path.stem}.{new_status}.json"
    return path.with_name(name)


# -----------------------------------------------------------------------------
# Decode helpers
# -----------------------------------------------------------------------------


def safe_b64decode(value: str) -> Optional[str]:
    if not value:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    # padding repair
    missing_padding = len(candidate) % 4
    if missing_padding:
        candidate += "=" * (4 - missing_padding)

    try:
        if "-" in candidate or "_" in candidate:
            decoded_bytes = base64.urlsafe_b64decode(candidate)
        else:
            decoded_bytes = base64.b64decode(candidate, validate=False)
    except (binascii.Error, ValueError):
        return None
    except Exception:
        return None

    decoded_text = decoded_bytes.decode("utf-8", errors="replace")
    if not decoded_text:
        return None

    printable_ratio = sum(ch.isprintable() or ch in "\r\n\t" for ch in decoded_text) / max(len(decoded_text), 1)
    if printable_ratio < 0.85:
        return None

    return decoded_text


def printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
    return printable / max(len(text), 1)


def trim_count(candidate: Dict[str, Any]) -> int:
    steps = candidate.get("normalization_steps") or []
    if not isinstance(steps, list):
        return 999

    for step in steps:
        if not isinstance(step, str):
            continue
        m = re.match(r"trim_trailing_base64_chars:(\d+)", step)
        if m:
            return int(m.group(1))
    return 0


def has_padding_repair(candidate: Dict[str, Any]) -> bool:
    steps = candidate.get("normalization_steps") or []
    if not isinstance(steps, list):
        return False
    return "repair_base64_padding" in steps


def candidate_rank_key(candidate: Dict[str, Any]) -> Tuple[int, float, int, int, int]:
    """
    후보 우선순위.

    목표:
    - 정상적으로 완전한 decoded_preview 우선
    - trim_count가 작은 후보 우선
    - decoded_preview가 긴 후보 우선
    - printable_ratio 높은 후보 우선
    - padding repair만으로 억지로 짧아진 후보보다 trim:1 후보 우선

    반환값은 sorted(..., reverse=True)에 사용할 수 있게 구성한다.
    """
    decoded = candidate.get("retry_decoded_preview") or candidate.get("decoded_preview") or ""
    if not isinstance(decoded, str):
        decoded = str(decoded)

    possible = 1 if decoded else 0
    ratio = printable_ratio(decoded)
    length = len(decoded)

    tc = trim_count(candidate)
    # 작은 trim_count가 좋으므로 음수 변환. trim 없음/trim1이 trim2/3보다 우선.
    trim_score = -tc

    # padding repair는 나쁜 것은 아니지만, 같은 조건이면 repair 없는 후보를 조금 우선.
    repair_score = 0 if has_padding_repair(candidate) else 1

    return (possible, ratio, length, trim_score, repair_score)


# -----------------------------------------------------------------------------
# Candidate extraction / retry decode
# -----------------------------------------------------------------------------


def get_retry_candidates(strategy_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = strategy_obj.get("normalized_candidates")
    if isinstance(candidates, list) and candidates:
        return [c for c in candidates if isinstance(c, dict)]

    best = strategy_obj.get("best_normalized_candidates")
    if isinstance(best, list) and best:
        return [c for c in best if isinstance(c, dict)]

    return []


def retry_decode_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    retried: List[Dict[str, Any]] = []

    for idx, candidate in enumerate(candidates):
        raw = candidate.get("normalized_raw")
        if not isinstance(raw, str) or not raw.strip():
            continue

        decoded = safe_b64decode(raw)
        item = dict(candidate)
        item["retry_index"] = idx
        item["retry_tool"] = "retry_encoding"
        item["retry_candidate_type"] = "base64"
        item["retry_decode_status"] = "success" if decoded else "failed"
        item["retry_decoded_preview"] = decoded
        item["retry_printable_ratio"] = printable_ratio(decoded or "") if decoded else None
        retried.append(item)

    return retried


def select_best_candidates(retried: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    successful = [c for c in retried if c.get("retry_decode_status") == "success"]
    successful = sorted(successful, key=candidate_rank_key, reverse=True)

    # 동일 decoded_preview 중복 제거
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for candidate in successful:
        decoded = candidate.get("retry_decoded_preview")
        normalized_raw = candidate.get("normalized_raw")
        key = (decoded, normalized_raw)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
        if len(deduped) >= limit:
            break

    return deduped


# -----------------------------------------------------------------------------
# Strategy status handling
# -----------------------------------------------------------------------------


def is_retry_encoding_pending(path: Path) -> bool:
    try:
        obj = load_json(path)
    except Exception:
        return False

    if obj.get("required_next_action") != "run_encoding_decode_tool":
        return False
    if obj.get("next_tool") not in {None, "encoding_decode_tool"}:
        return False
    if not get_retry_candidates(obj):
        return False

    return True


def iter_retry_pending_files(strategy_dir: Path) -> List[Path]:
    return sorted(p for p in strategy_dir.glob("*.pending.json") if is_retry_encoding_pending(p))


def build_retry_result(strategy_path: Path, strategy_obj: Dict[str, Any]) -> Dict[str, Any]:
    candidates = get_retry_candidates(strategy_obj)
    retried = retry_decode_candidates(candidates)
    selected = select_best_candidates(retried, limit=5)

    status = "retry_decode_success" if selected else "retry_decode_failed"

    return {
        "ok": True,
        "tool": "retry_encoding",
        "source_strategy": str(strategy_path),
        "status": status,
        "checked_candidates": len(candidates),
        "retried_candidates": len(retried),
        "success_candidates": len([c for c in retried if c.get("retry_decode_status") == "success"]),
        "selected_candidates": selected,
        "retried_candidates_preview": retried[:20],
        "error": None,
    }


def update_strategy_success(
    strategy_obj: Dict[str, Any],
    retry_result: Dict[str, Any],
) -> Dict[str, Any]:
    selected = retry_result.get("selected_candidates") or []

    new_obj = dict(strategy_obj)
    new_obj["decision"] = "stop"
    new_obj["completion_status"] = "retry_decode_success"
    new_obj["needs_llm_review"] = False
    new_obj["required_next_action"] = None
    new_obj["next_tool"] = None
    new_obj["next_tool_input"] = None
    new_obj["retry_encoding_result"] = retry_result

    # 최종 decoded 결과 요약 추가
    new_obj["final_retry_decoded_candidates"] = selected

    existing_decoded = new_obj.get("decoded_candidates_preview")
    if isinstance(existing_decoded, list):
        merged = list(existing_decoded)
    else:
        merged = []

    for item in selected:
        merged.append(
            {
                "segment_no": item.get("segment_no"),
                "stream_key": item.get("stream_key"),
                "protocol": item.get("protocol"),
                "position": item.get("position"),
                "source": item.get("source"),
                "candidate_type": item.get("candidate_type") or item.get("retry_candidate_type"),
                "decode_status": "success",
                "raw": item.get("normalized_raw"),
                "decoded_preview": item.get("retry_decoded_preview"),
                "retry_from_original_raw": item.get("original_raw"),
                "normalization_steps": item.get("normalization_steps"),
            }
        )

    new_obj["decoded_candidates_preview"] = merged

    counts = dict(new_obj.get("counts") or {})
    counts["retry_decoded_candidates"] = len(selected)
    counts["retry_checked_candidates"] = retry_result.get("checked_candidates")
    counts["retry_success_candidates"] = retry_result.get("success_candidates")
    new_obj["counts"] = counts

    return new_obj


def update_strategy_failure(
    strategy_obj: Dict[str, Any],
    retry_result: Dict[str, Any],
    keep_pending: bool = True,
) -> Dict[str, Any]:
    new_obj = dict(strategy_obj)
    new_obj["completion_status"] = "retry_decode_failed"
    new_obj["retry_encoding_result"] = retry_result

    if keep_pending:
        # 다시 LLM 리뷰로 넘길 수 있게 pending 유지
        new_obj["needs_llm_review"] = True
        new_obj["required_next_action"] = None
        new_obj["next_tool"] = None
        new_obj["next_tool_input"] = None
        new_obj["llm_review_prompt"] = build_retry_failure_prompt(new_obj, retry_result)
    else:
        new_obj["needs_llm_review"] = False
        new_obj["required_next_action"] = None
        new_obj["next_tool"] = None
        new_obj["next_tool_input"] = None

    return new_obj


def build_retry_failure_prompt(strategy_obj: Dict[str, Any], retry_result: Dict[str, Any]) -> str:
    return (
        "You are reviewing a retry decoding failure.\n"
        "The previous LLM step requested noise cleanup and retry decoding, but retry_encoding did not find a successful candidate.\n"
        "Decide whether another tool should be called, whether the case should stop, or whether it should fail.\n\n"
        f"Current completion_status: retry_decode_failed\n"
        f"Retry result:\n{json.dumps(retry_result, ensure_ascii=False, indent=2)[:4000]}\n\n"
        "Return JSON only with fields:\n"
        "{decision, completion_status, requires_additional_verification, reason, recommended_tool, recommended_options}\n"
    )


# -----------------------------------------------------------------------------
# Processing
# -----------------------------------------------------------------------------


def process_strategy_file(
    *,
    strategy_path: Path,
    dry_run: bool = False,
    keep_pending_on_failure: bool = True,
) -> Dict[str, Any]:
    strategy_obj = load_json(strategy_path)
    retry_result = build_retry_result(strategy_path, strategy_obj)

    if dry_run:
        return {
            "input": str(strategy_path),
            "dry_run": True,
            "would_status": retry_result.get("status"),
            "checked_candidates": retry_result.get("checked_candidates"),
            "success_candidates": retry_result.get("success_candidates"),
            "selected_candidates": retry_result.get("selected_candidates"),
        }

    if retry_result.get("status") == "retry_decode_success":
        updated = update_strategy_success(strategy_obj, retry_result)
        output_path = replace_status_suffix(strategy_path, "done")
        write_json(output_path, updated)
        if output_path != strategy_path and strategy_path.exists():
            strategy_path.unlink()

        return {
            "input": str(strategy_path),
            "output": str(output_path),
            "file_status": "done",
            "status": retry_result.get("status"),
            "checked_candidates": retry_result.get("checked_candidates"),
            "success_candidates": retry_result.get("success_candidates"),
            "selected_count": len(retry_result.get("selected_candidates") or []),
        }

    updated = update_strategy_failure(
        strategy_obj,
        retry_result,
        keep_pending=keep_pending_on_failure,
    )

    if keep_pending_on_failure:
        output_path = strategy_path
        write_json(output_path, updated)
        file_status = "pending"
    else:
        output_path = replace_status_suffix(strategy_path, "failed")
        write_json(output_path, updated)
        if output_path != strategy_path and strategy_path.exists():
            strategy_path.unlink()
        file_status = "failed"

    return {
        "input": str(strategy_path),
        "output": str(output_path),
        "file_status": file_status,
        "status": retry_result.get("status"),
        "checked_candidates": retry_result.get("checked_candidates"),
        "success_candidates": retry_result.get("success_candidates"),
        "selected_count": len(retry_result.get("selected_candidates") or []),
    }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy-dir",
        default=str(DEFAULT_STRATEGY_DIR),
        help="Directory containing strategy *.pending.json files",
    )
    parser.add_argument(
        "--strategy-file",
        default="",
        help="Process one strategy pending file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without writing files",
    )
    parser.add_argument(
        "--fail-to-failed",
        action="store_true",
        help="On retry failure, move file to .failed.json instead of keeping pending for LLM review",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    keep_pending_on_failure = not args.fail_to_failed

    if args.strategy_file:
        strategy_path = Path(args.strategy_file)
        if not strategy_path.exists():
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": "RETRY_ENCODING_ERROR",
                            "message": f"strategy file not found: {str(strategy_path)}",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise SystemExit(1)

        try:
            result = process_strategy_file(
                strategy_path=strategy_path,
                dry_run=args.dry_run,
                keep_pending_on_failure=keep_pending_on_failure,
            )
            print(json.dumps({"ok": True, "processed_files": 1, "results": [result]}, ensure_ascii=False, indent=2))
            raise SystemExit(0)
        except Exception as e:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": "RETRY_ENCODING_ERROR",
                            "message": str(e),
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise SystemExit(1)

    strategy_dir = Path(args.strategy_dir)
    if not strategy_dir.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "RETRY_ENCODING_ERROR",
                        "message": f"strategy directory not found: {str(strategy_dir)}",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)

    pending_files = iter_retry_pending_files(strategy_dir)

    if not pending_files:
        print(
            json.dumps(
                {
                    "ok": True,
                    "message": "No retry-encoding pending files found.",
                    "processed_files": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(0)

    summary = []
    errors = []

    for strategy_path in pending_files:
        try:
            summary.append(
                process_strategy_file(
                    strategy_path=strategy_path,
                    dry_run=args.dry_run,
                    keep_pending_on_failure=keep_pending_on_failure,
                )
            )
        except Exception as e:
            errors.append({"input": str(strategy_path), "error": str(e)})

    print(
        json.dumps(
            {
                "ok": not errors,
                "processed_files": len(summary),
                "error_count": len(errors),
                "results": summary,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
