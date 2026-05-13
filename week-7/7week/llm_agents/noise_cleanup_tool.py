#!/usr/bin/env python3
r"""
llm_agents/noise_cleanup_tool.py

LLM Agent의 retry_same_tool 흐름에서 사용하는 노이즈 제거/정규화 전처리 도구.

역할
- strategy JSON 또는 decoded JSON에서 failed candidate raw 값을 추출한다.
- raw candidate에 대해 deterministic normalization variants를 생성한다.
- 직접 최종 decode 판정을 하지 않는다.
- 다음 단계 encoding_decode_tool.py가 사용할 normalized candidate JSON을 출력한다.

중요
- 이 도구는 디코딩 executor가 아니라 전처리 도구다.
- 다만 생성된 normalized_raw가 base64 decode 가능한지 sanity check하고 decoded_preview를 함께 기록한다.
- trailing '0'처럼 base64 alphabet에 포함되는 문자라도 noise일 수 있으므로,
  trim_trailing_base64_chars 옵션으로 뒤에서 1..N 글자를 잘라본다.

권장 workflow
1. llm_agent.py
   - LLM이 retry_same_tool 판단
   - recommended_options 생성

2. noise_cleanup_tool.py
   - failed candidate raw 정규화
   - normalized_candidates JSON 저장

3. encoding_decode_tool.py
   - normalized_candidates를 다시 decode
   - 성공 시 done 처리

실행 예시
    py .\llm_agents\noise_cleanup_tool.py ^
      --input .\data\strategy\01_sample_packet_ldap-basic-auth-ev1_strategy.pending.json ^
      --output .\data\strategy\01_sample_packet_ldap-basic-auth-ev1_noise_cleanup.result.json ^
      --strip-trailing-noise ^
      --strip-invalid-base64-chars ^
      --repair-base64-padding ^
      --trim-trailing-base64-chars ^
      --max-trailing-trim 3

    py .\llm_agents\noise_cleanup_tool.py ^
      --input .\data\strategy\01_sample_packet_ldap-basic-auth-ev1_strategy.pending.json ^
      --output .\data\strategy\01_sample_packet_ldap-basic-auth-ev1_noise_cleanup.result.json ^
      --options-json "{\"strip_trailing_noise\": true, \"strip_invalid_base64_chars\": true, \"repair_base64_padding\": true, \"trim_trailing_base64_chars\": true, \"max_trailing_trim\": 3}"
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BASE64_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
BASE64_URLSAFE_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")
BASE64_BODY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")
BASE64_URLSAFE_BODY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

DEFAULT_OPTIONS = {
    "url_decode_before_base64": False,
    "strip_whitespace": True,
    "strip_trailing_noise": False,
    "strip_invalid_base64_chars": False,
    "repair_base64_padding": False,
    "trim_trailing_base64_chars": False,
    "max_trailing_trim": 3,
    "deduplicate": True,
    "min_base64_length": 8,
}

CANDIDATE_FIELDS = [
    "failed_candidates_preview",
    "failed_candidates",
    "residue_candidates_preview",
    "residue_candidates",
]

RAW_KEYS = [
    "raw",
    "candidate",
    "value",
    "encoded",
    "payload",
    "preview",
]


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
# Option handling
# -----------------------------------------------------------------------------


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def merge_options(args: argparse.Namespace) -> Dict[str, Any]:
    options = dict(DEFAULT_OPTIONS)

    if args.options_json:
        try:
            loaded = json.loads(args.options_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--options-json 파싱 실패: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError("--options-json must be JSON object")
        options.update(loaded)

    # CLI flags override options-json.
    if args.url_decode_before_base64:
        options["url_decode_before_base64"] = True
    if args.no_strip_whitespace:
        options["strip_whitespace"] = False
    if args.strip_trailing_noise:
        options["strip_trailing_noise"] = True
    if args.strip_invalid_base64_chars:
        options["strip_invalid_base64_chars"] = True
    if args.repair_base64_padding:
        options["repair_base64_padding"] = True
    if args.trim_trailing_base64_chars:
        options["trim_trailing_base64_chars"] = True
    if args.max_trailing_trim is not None:
        options["max_trailing_trim"] = args.max_trailing_trim
    if args.no_deduplicate:
        options["deduplicate"] = False
    if args.min_base64_length is not None:
        options["min_base64_length"] = args.min_base64_length

    for key in [
        "url_decode_before_base64",
        "strip_whitespace",
        "strip_trailing_noise",
        "strip_invalid_base64_chars",
        "repair_base64_padding",
        "trim_trailing_base64_chars",
        "deduplicate",
    ]:
        options[key] = as_bool(options.get(key))

    options["min_base64_length"] = int(options.get("min_base64_length", 8))
    options["max_trailing_trim"] = int(options.get("max_trailing_trim", 3))

    if options["max_trailing_trim"] < 0:
        options["max_trailing_trim"] = 0
    if options["max_trailing_trim"] > 12:
        # 과도한 trimming은 정상 payload 훼손 위험이 크므로 hard cap.
        options["max_trailing_trim"] = 12

    return options


# -----------------------------------------------------------------------------
# Base64-ish helpers
# -----------------------------------------------------------------------------


def strip_whitespace(text: str) -> str:
    return re.sub(r"\s+", "", text)


def looks_like_base64ish(text: str, min_len: int = 8) -> bool:
    compact = strip_whitespace(text)
    if len(compact) < min_len:
        return False

    allowed_count = sum(1 for ch in compact if ch in BASE64_CHARS or ch in BASE64_URLSAFE_CHARS)
    ratio = allowed_count / max(len(compact), 1)
    return ratio >= 0.75


def base64ish_score(text: str) -> float:
    compact = strip_whitespace(text)
    if not compact:
        return 0.0

    allowed_count = sum(1 for ch in compact if ch in BASE64_CHARS or ch in BASE64_URLSAFE_CHARS)
    allowed_ratio = allowed_count / len(compact)

    # base64 length modulo 4가 맞을수록 약간 가산.
    body = compact.rstrip("=")
    mod = len(body) % 4
    mod_score = 1.0 if mod in {0, 2, 3} else 0.5

    return round((allowed_ratio * 0.8) + (mod_score * 0.2), 4)


def url_decode(text: str) -> str:
    previous = text
    current = urllib.parse.unquote(previous)
    # 이중 URL encoding 가능성 때문에 최대 2회만 반복.
    for _ in range(1):
        if current == previous:
            break
        previous = current
        current = urllib.parse.unquote(previous)
    return current


def strip_trailing_noise(text: str) -> str:
    """
    base64 본문 뒤에 붙은 trailing garbage를 제거한다.

    - padding 뒤에 문자가 붙은 경우: ABCD==0 -> ABCD==
    - padding이 없으면 뒤쪽 non-base64 문자만 제거한다.
    - trailing '0'처럼 base64 alphabet에 속한 문자는 여기서 제거하지 않는다.
      그런 케이스는 trim_trailing_base64_chars 옵션에서 처리한다.
    """
    compact = text.strip()

    # padding 뒤에 문자가 붙은 경우: ...=xxx 또는 ...==xxx
    match = re.match(r"^([A-Za-z0-9+/_-]+={1,2})(.+)$", compact)
    if match:
        return match.group(1)

    # padding이 없는 경우에는 뒤쪽 non-base64 문자만 제거.
    while compact and compact[-1] not in BASE64_CHARS and compact[-1] not in BASE64_URLSAFE_CHARS:
        compact = compact[:-1]

    return compact


def strip_invalid_base64_chars(text: str) -> str:
    """
    base64/base64url alphabet 외 문자를 제거한다.
    중간에 섞인 구분자, 따옴표, 세미콜론 등을 제거하는 용도.
    """
    return "".join(ch for ch in text if ch in BASE64_CHARS or ch in BASE64_URLSAFE_CHARS)


def repair_base64_padding(text: str) -> str:
    compact = text.strip()
    compact = compact.rstrip("=")
    missing = (-len(compact)) % 4
    return compact + ("=" * missing)


def trim_trailing_base64_chars(text: str, max_trim: int = 3) -> List[Tuple[str, int]]:
    """
    끝 문자가 base64 alphabet에 포함되어도 noise일 수 있는 경우를 처리한다.

    예:
    - cGluZyAtYyAxMCAxLjEuMS4x0  -> 마지막 1글자 '0' 제거
    - 그 후 padding repair를 적용하면 정상 base64 decode 가능할 수 있다.

    max_trim은 작은 값으로 제한해야 한다. 너무 크게 자르면 정상 payload를 훼손한다.
    """
    compact = text.strip()
    variants: List[Tuple[str, int]] = []

    if max_trim <= 0:
        return variants

    for trim_count in range(1, max_trim + 1):
        if len(compact) <= trim_count:
            break
        trimmed = compact[:-trim_count]
        if trimmed:
            variants.append((trimmed, trim_count))

    return variants


def try_base64_decode(text: str) -> Optional[bytes]:
    compact = text.strip()
    if not compact:
        return None

    try:
        if "-" in compact or "_" in compact:
            return base64.urlsafe_b64decode(compact)
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    printable = 0
    for b in data:
        if b in {9, 10, 13} or 32 <= b <= 126:
            printable += 1
    return printable / len(data)


def decode_preview(text: str, limit: int = 160) -> Tuple[Optional[str], Optional[float]]:
    raw = try_base64_decode(text)
    if raw is None:
        return None, None

    ratio = printable_ratio(raw)
    try:
        decoded = raw.decode("utf-8", errors="replace")
    except Exception:
        decoded = repr(raw)

    if len(decoded) > limit:
        decoded = decoded[:limit] + "..."

    return decoded, round(ratio, 4)


# -----------------------------------------------------------------------------
# Variant generation
# -----------------------------------------------------------------------------


def add_variant(
    variants: List[Dict[str, Any]],
    *,
    normalized_raw: str,
    steps: List[str],
    original_raw: str,
) -> None:
    preview, ratio = decode_preview(normalized_raw)
    variants.append(
        {
            "normalized_raw": normalized_raw,
            "normalization_steps": steps,
            "changed": normalized_raw != original_raw,
            "base64_decode_possible": preview is not None,
            "decoded_preview": preview,
            "printable_ratio": ratio,
            "score_hint": base64ish_score(normalized_raw),
        }
    )


def add_variant_pair_with_padding(
    variants: List[Dict[str, Any]],
    *,
    candidate: str,
    steps: List[str],
    original_raw: str,
    repair_padding: bool,
) -> None:
    add_variant(
        variants,
        normalized_raw=candidate,
        steps=steps,
        original_raw=original_raw,
    )
    if repair_padding:
        padded = repair_base64_padding(candidate)
        add_variant(
            variants,
            normalized_raw=padded,
            steps=[*steps, "repair_base64_padding"],
            original_raw=original_raw,
        )


def generate_variants(raw: str, options: Dict[str, Any]) -> List[Dict[str, Any]]:
    variants: List[Dict[str, Any]] = []
    min_len = int(options.get("min_base64_length", 8))

    if not raw or not looks_like_base64ish(raw, min_len=min_len):
        return []

    repair_padding = bool(options.get("repair_base64_padding"))

    base = raw
    add_variant(variants, normalized_raw=base, steps=["original"], original_raw=raw)

    if options.get("strip_whitespace"):
        candidate = strip_whitespace(base)
        add_variant(variants, normalized_raw=candidate, steps=["strip_whitespace"], original_raw=raw)
        base = candidate

    if options.get("url_decode_before_base64"):
        candidate = url_decode(base)
        add_variant_pair_with_padding(
            variants,
            candidate=candidate,
            steps=["url_decode_before_base64"],
            original_raw=raw,
            repair_padding=repair_padding,
        )

        if options.get("strip_whitespace"):
            candidate2 = strip_whitespace(candidate)
            add_variant_pair_with_padding(
                variants,
                candidate=candidate2,
                steps=["url_decode_before_base64", "strip_whitespace"],
                original_raw=raw,
                repair_padding=repair_padding,
            )

    working_inputs = [v["normalized_raw"] for v in variants]

    if options.get("strip_trailing_noise"):
        for current in list(working_inputs):
            candidate = strip_trailing_noise(current)
            add_variant_pair_with_padding(
                variants,
                candidate=candidate,
                steps=["strip_trailing_noise"],
                original_raw=raw,
                repair_padding=repair_padding,
            )

    working_inputs = [v["normalized_raw"] for v in variants]

    if options.get("strip_invalid_base64_chars"):
        for current in list(working_inputs):
            candidate = strip_invalid_base64_chars(current)
            add_variant_pair_with_padding(
                variants,
                candidate=candidate,
                steps=["strip_invalid_base64_chars"],
                original_raw=raw,
                repair_padding=repair_padding,
            )

    working_inputs = [v["normalized_raw"] for v in variants]

    if options.get("trim_trailing_base64_chars"):
        max_trim = int(options.get("max_trailing_trim", 3))
        for current in list(working_inputs):
            for candidate, trim_count in trim_trailing_base64_chars(current, max_trim=max_trim):
                add_variant_pair_with_padding(
                    variants,
                    candidate=candidate,
                    steps=[f"trim_trailing_base64_chars:{trim_count}"],
                    original_raw=raw,
                    repair_padding=repair_padding,
                )

    # repair_base64_padding 단독 variant도 생성한다.
    if repair_padding:
        working_inputs = [v["normalized_raw"] for v in variants]
        for current in list(working_inputs):
            candidate = repair_base64_padding(current)
            add_variant(
                variants,
                normalized_raw=candidate,
                steps=["repair_base64_padding"],
                original_raw=raw,
            )

    if options.get("deduplicate"):
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for variant in variants:
            key = variant["normalized_raw"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(variant)
        variants = deduped

    return variants


# -----------------------------------------------------------------------------
# Candidate extraction
# -----------------------------------------------------------------------------


def extract_raw_from_candidate(candidate: Dict[str, Any]) -> Optional[str]:
    for key in RAW_KEYS:
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_candidates(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    strategy JSON / decoded JSON 양쪽 구조를 느슨하게 지원한다.
    """
    extracted: List[Dict[str, Any]] = []

    for field in CANDIDATE_FIELDS:
        value = obj.get(field)
        if not isinstance(value, list):
            continue

        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                continue

            raw = extract_raw_from_candidate(item)
            if not raw:
                continue

            extracted.append(
                {
                    "source_field": field,
                    "source_index": idx,
                    "candidate_type": item.get("candidate_type") or item.get("type") or "unknown",
                    "position": item.get("position"),
                    "source": item.get("source"),
                    "failure_type": item.get("failure_type") or item.get("error") or item.get("reason"),
                    "raw": raw,
                    "original_candidate": item,
                }
            )

    # llm_review_prompt만 있고 preview가 없는 경우를 대비해 최소 fallback.
    if not extracted:
        prompt = obj.get("llm_review_prompt")
        if isinstance(prompt, str):
            tokens = re.findall(r"[A-Za-z0-9+/_=-]{12,}", prompt)
            for idx, token in enumerate(tokens):
                if looks_like_base64ish(token):
                    extracted.append(
                        {
                            "source_field": "llm_review_prompt_regex",
                            "source_index": idx,
                            "candidate_type": "base64ish",
                            "position": None,
                            "source": None,
                            "failure_type": "regex_extracted_from_prompt",
                            "raw": token,
                            "original_candidate": None,
                        }
                    )

    return extracted


# -----------------------------------------------------------------------------
# Output builder
# -----------------------------------------------------------------------------


def build_normalized_output(
    *,
    source_file: Path,
    obj: Dict[str, Any],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    candidates = extract_candidates(obj)
    normalized_candidates: List[Dict[str, Any]] = []

    for source_idx, candidate in enumerate(candidates):
        raw = candidate["raw"]
        variants = generate_variants(raw, options)

        for variant_idx, variant in enumerate(variants):
            normalized_candidates.append(
                {
                    "source_candidate_index": source_idx,
                    "variant_index": variant_idx,
                    "source_field": candidate["source_field"],
                    "source_index": candidate["source_index"],
                    "candidate_type": candidate["candidate_type"],
                    "position": candidate.get("position"),
                    "source": candidate.get("source"),
                    "failure_type": candidate.get("failure_type"),
                    "original_raw": raw,
                    **variant,
                }
            )

    successful = [c for c in normalized_candidates if c.get("base64_decode_possible")]

    return {
        "ok": True,
        "tool": "noise_cleanup_tool",
        "mode": "normalization_only",
        "source_file": str(source_file),
        "source_input": obj.get("input"),
        "source_decoded": obj.get("source_decoded"),
        "options": options,
        "candidate_count": len(candidates),
        "normalized_candidate_count": len(normalized_candidates),
        "base64_decodable_candidate_count": len(successful),
        "candidates": candidates,
        "normalized_candidates": normalized_candidates,
        "best_candidates": sorted(
            successful,
            key=lambda x: (
                float(x.get("printable_ratio") or 0),
                float(x.get("score_hint") or 0),
                len(str(x.get("decoded_preview") or "")),
            ),
            reverse=True,
        )[:5],
    }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="strategy JSON or decoded JSON path")
    parser.add_argument("--output", required=True, help="output normalized candidate JSON path")
    parser.add_argument("--options-json", default="", help="recommended_options JSON string from llm_agent")

    parser.add_argument("--url-decode-before-base64", action="store_true")
    parser.add_argument("--no-strip-whitespace", action="store_true")
    parser.add_argument("--strip-trailing-noise", action="store_true")
    parser.add_argument("--strip-invalid-base64-chars", action="store_true")
    parser.add_argument("--repair-base64-padding", action="store_true")
    parser.add_argument("--trim-trailing-base64-chars", action="store_true")
    parser.add_argument("--max-trailing-trim", type=int, default=None)
    parser.add_argument("--no-deduplicate", action="store_true")
    parser.add_argument("--min-base64-length", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        options = merge_options(args)
        obj = load_json(input_path)
        result = build_normalized_output(
            source_file=input_path,
            obj=obj,
            options=options,
        )
        write_json(output_path, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        error_obj = {
            "ok": False,
            "tool": "noise_cleanup_tool",
            "source_file": str(input_path),
            "output_file": str(output_path),
            "error": str(e),
        }
        try:
            write_json(output_path, error_obj)
        except Exception:
            pass
        print(json.dumps(error_obj, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
