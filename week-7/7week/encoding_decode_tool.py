import argparse
import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BASIC_AUTH_RE = re.compile(
    r"Authorization:\s*Basic\s+([A-Za-z0-9+/=]+)",
    re.IGNORECASE,
)

BASIC_VALUE_RE = re.compile(
    r"^Basic\s+([A-Za-z0-9+/=]+)$",
    re.IGNORECASE,
)

BASE64_PATH_RE = re.compile(
    r"/Base64/([A-Za-z0-9+/=]+)",
    re.IGNORECASE,
)

URL_ESCAPE_RE = re.compile(r"%[0-9A-Fa-f]{2}")
LOG4SHELL_OBFUSCATION_HINT_RE = re.compile(r"\$\{(?:lower|upper):|\$\{::-.", re.IGNORECASE)
BASE64ISH_RE = re.compile(r"\b[A-Za-z0-9+/]{16,}={0,2}\b")


def _safe_b64decode(value: str) -> Optional[str]:
    if not value:
        return None

    candidate = value.strip()

    missing_padding = len(candidate) % 4
    if missing_padding:
        candidate += "=" * (4 - missing_padding)

    try:
        decoded_bytes = base64.b64decode(candidate, validate=False)
        decoded_text = decoded_bytes.decode("utf-8", errors="replace")
    except Exception:
        return None

    printable_ratio = sum(ch.isprintable() or ch in "\r\n\t" for ch in decoded_text) / max(
        len(decoded_text), 1
    )
    if printable_ratio < 0.85:
        return None

    return decoded_text


def _normalize_log4shell_obfuscation(text: str) -> str:
    if not text:
        return text

    normalized = text

    patterns = [
        (re.compile(r"\$\{lower:([^}])\}", re.IGNORECASE), lambda m: m.group(1).lower()),
        (re.compile(r"\$\{upper:([^}])\}", re.IGNORECASE), lambda m: m.group(1).lower()),
        (re.compile(r"\$\{::-(.)\}"), lambda m: m.group(1)),
    ]

    changed = True
    while changed:
        changed = False
        before = normalized

        for pattern, repl in patterns:
            normalized = pattern.sub(repl, normalized)

        if normalized != before:
            changed = True

    return normalized


def _extract_nested_base64(text: str) -> List[Dict[str, Any]]:
    nested: List[Dict[str, Any]] = []

    for match in BASE64_PATH_RE.finditer(text):
        raw = match.group(1)
        decoded = _safe_b64decode(raw)

        nested.append(
            {
                "candidate_type": "base64",
                "position": "nested.base64_path",
                "raw": raw,
                "decoded_preview": decoded,
                "decode_status": "success" if decoded else "failed",
                "span": {
                    "start": match.start(1),
                    "end": match.end(1),
                },
            }
        )

    return nested


def _collect_candidate_texts(candidate: Dict[str, Any]) -> List[Tuple[str, str]]:
    texts: List[Tuple[str, str]] = []

    for key in ["raw", "decoded_preview", "normalized_payload"]:
        value = candidate.get(key)
        if isinstance(value, str) and value:
            texts.append((key, value))

    for idx, nested in enumerate(candidate.get("nested_candidates", []) or []):
        for key in ["raw", "decoded_preview"]:
            value = nested.get(key)
            if isinstance(value, str) and value:
                texts.append((f"nested[{idx}].{key}", value))

    return texts


def _looks_like_redecodable_base64(text: str) -> bool:
    for match in BASE64ISH_RE.finditer(text):
        token = match.group(0)
        if len(token) < 16:
            continue

        decoded = _safe_b64decode(token)
        if decoded:
            return True

    return False


def _detect_residue_signals(candidate: Dict[str, Any]) -> List[str]:
    signals: List[str] = []

    decoded_preview = candidate.get("decoded_preview") or ""
    normalized_payload = candidate.get("normalized_payload") or ""
    nested_candidates = candidate.get("nested_candidates", []) or []

    for _, text in _collect_candidate_texts(candidate):
        if URL_ESCAPE_RE.search(text):
            signals.append("url_escape_remaining")
            break

    if not normalized_payload:
        if isinstance(decoded_preview, str) and LOG4SHELL_OBFUSCATION_HINT_RE.search(decoded_preview):
            signals.append("log4shell_obfuscation_remaining")

    base64_path_visible = False
    for key, text in _collect_candidate_texts(candidate):
        if key.startswith("nested["):
            continue
        if "/Base64/" in text or "/base64/" in text.lower():
            base64_path_visible = True
            break

    if base64_path_visible:
        if not nested_candidates:
            signals.append("nested_base64_remaining")
        elif any(n.get("decode_status") != "success" for n in nested_candidates):
            signals.append("nested_base64_remaining")

    if any(n.get("decode_status") == "failed" for n in nested_candidates):
        signals.append("nested_candidate_failed")

    recheck_targets = []
    if isinstance(decoded_preview, str) and decoded_preview:
        recheck_targets.append(decoded_preview)
    if isinstance(normalized_payload, str) and normalized_payload:
        recheck_targets.append(normalized_payload)

    for text in recheck_targets:
        if _looks_like_redecodable_base64(text):
            signals.append("base64_like_remaining")
            break

    return sorted(set(signals))


def _make_candidate(
    *,
    segment_no: Optional[int],
    position: str,
    source: str,
    raw: str,
    decoded_preview: Optional[str],
    normalized_payload: Optional[str],
    nested_candidates: List[Dict[str, Any]],
    decode_status: str,
    span: Optional[Dict[str, int]],
) -> Dict[str, Any]:
    candidate = {
        "segment_no": segment_no,
        "candidate_type": "base64" if source.startswith("http.authorization") else "derived_or_nested",
        "position": position,
        "source": source,
        "raw": raw,
        "decoded_preview": decoded_preview,
        "normalized_payload": normalized_payload,
        "nested_candidates": nested_candidates,
        "decode_status": decode_status,
        "span": span,
    }
    candidate["residue_signals"] = _detect_residue_signals(candidate)
    return candidate


def _extract_from_authorization_header(
    payload: str,
    position: str,
    segment_no: Optional[int],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for match in BASIC_AUTH_RE.finditer(payload):
        raw = match.group(1)
        decoded = _safe_b64decode(raw)
        normalized = _normalize_log4shell_obfuscation(decoded or "")
        nested_candidates = _extract_nested_base64(normalized or decoded or "")

        candidates.append(
            _make_candidate(
                segment_no=segment_no,
                position=position,
                source="http.authorization.basic",
                raw=raw,
                decoded_preview=decoded,
                normalized_payload=normalized if normalized and normalized != decoded else None,
                nested_candidates=nested_candidates,
                decode_status="success" if decoded else "failed",
                span={"start": match.start(1), "end": match.end(1)},
            )
        )

    value_match = BASIC_VALUE_RE.match(payload.strip())
    if value_match:
        raw = value_match.group(1)
        decoded = _safe_b64decode(raw)
        normalized = _normalize_log4shell_obfuscation(decoded or "")
        nested_candidates = _extract_nested_base64(normalized or decoded or "")

        candidates.append(
            _make_candidate(
                segment_no=segment_no,
                position=position,
                source="http.authorization.basic.value",
                raw=raw,
                decoded_preview=decoded,
                normalized_payload=normalized if normalized and normalized != decoded else None,
                nested_candidates=nested_candidates,
                decode_status="success" if decoded else "failed",
                span=None,
            )
        )

    return candidates


def _extract_from_log4shell_obfuscation(
    payload: str,
    position: str,
    segment_no: Optional[int],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    if "${" not in payload:
        return candidates

    if not LOG4SHELL_OBFUSCATION_HINT_RE.search(payload):
        return candidates

    normalized = _normalize_log4shell_obfuscation(payload)
    if normalized == payload:
        return candidates

    nested_candidates = _extract_nested_base64(normalized)

    candidate = {
        "segment_no": segment_no,
        "candidate_type": "log4shell_obfuscation",
        "position": position,
        "source": "application_layer_content",
        "raw": payload,
        "decoded_preview": None,
        "normalized_payload": normalized,
        "nested_candidates": nested_candidates,
        "decode_status": "normalized",
        "span": None,
    }
    candidate["residue_signals"] = _detect_residue_signals(candidate)

    candidates.append(candidate)
    return candidates


def _extract_from_base64_path(
    payload: str,
    position: str,
    segment_no: Optional[int],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for nested in _extract_nested_base64(payload):
        candidate = {
            "segment_no": segment_no,
            "candidate_type": nested.get("candidate_type"),
            "position": nested.get("position"),
            "source": f"{position}.base64_path",
            "raw": nested.get("raw"),
            "decoded_preview": nested.get("decoded_preview"),
            "normalized_payload": None,
            "nested_candidates": [],
            "decode_status": nested.get("decode_status"),
            "span": nested.get("span"),
        }
        candidate["residue_signals"] = _detect_residue_signals(candidate)
        candidates.append(candidate)

    return candidates


def _extract_candidates_from_payload(
    payload: str,
    position: str,
    segment_no: Optional[int],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    candidates.extend(_extract_from_authorization_header(payload, position, segment_no))
    candidates.extend(_extract_from_log4shell_obfuscation(payload, position, segment_no))
    candidates.extend(_extract_from_base64_path(payload, position, segment_no))

    return candidates


def _load_streams(segments_path: str) -> List[Dict[str, Any]]:
    path = Path(segments_path)

    if not path.exists():
        raise FileNotFoundError(f"segments file not found: {segments_path}")

    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)

    if isinstance(obj, dict) and "streams" in obj:
        return obj["streams"]

    if isinstance(obj, list):
        return obj

    raise ValueError("Invalid segments.json format. Expected {'streams': [...]} or list.")


def _dedup_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []

    for c in candidates:
        key = (
            c.get("stream_key"),
            c.get("raw"),
            c.get("decoded_preview"),
            c.get("normalized_payload"),
            c.get("decode_status"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(c)

    return out


def encoding_decode_tool(
    segments_path: Optional[str] = None,
    streams: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    try:
        if streams is None:
            if segments_path is None:
                raise ValueError("segments_path or streams must be provided")
            streams = _load_streams(segments_path)

        decoded_candidates: List[Dict[str, Any]] = []
        failed_candidates: List[Dict[str, Any]] = []
        residue_candidates: List[Dict[str, Any]] = []
        excluded_streams: List[Dict[str, Any]] = []

        checked_segments = 0

        for stream in streams:
            stream_key = stream.get("stream_key")
            protocol = stream.get("protocol")
            encrypted = stream.get("encrypted", False)
            segments = stream.get("segments", [])

            if encrypted is True:
                excluded_streams.append(
                    {
                        "stream_key": stream_key,
                        "protocol": protocol,
                        "reason": "encrypted_stream_excluded",
                    }
                )

            for segment in segments:
                checked_segments += 1

                segment_no = segment.get("no")
                position = segment.get("position", "unknown")
                payload = segment.get("payload", "")

                if not isinstance(payload, str):
                    continue
                if encrypted is True:
                    continue
                if not payload:
                    continue

                candidates = _extract_candidates_from_payload(
                    payload=payload,
                    position=position,
                    segment_no=segment_no,
                )

                for candidate in candidates:
                    candidate["stream_key"] = stream_key
                    candidate["protocol"] = protocol

                    if candidate.get("decode_status") in {"success", "normalized"}:
                        decoded_candidates.append(candidate)
                        if candidate.get("residue_signals"):
                            residue_candidates.append(candidate)
                    else:
                        failed_candidates.append(candidate)

        decoded_candidates = _dedup_candidates(decoded_candidates)
        failed_candidates = _dedup_candidates(failed_candidates)
        residue_candidates = _dedup_candidates(residue_candidates)

        if decoded_candidates and residue_candidates:
            status = "decode_success_with_residue"
        elif decoded_candidates:
            status = "decode_success"
        elif failed_candidates:
            status = "decode_failed"
        elif excluded_streams:
            status = "excluded_only"
        else:
            status = "no_encoding_candidate"

        return {
            "ok": True,
            "data": {
                "status": status,
                "decoded_candidates": decoded_candidates,
                "failed_candidates": failed_candidates,
                "residue_candidates": residue_candidates,
                "excluded_streams": excluded_streams,
                "checked_streams": len(streams),
                "checked_segments": checked_segments,
            },
            "error": None,
        }

    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": "ENCODING_DECODE_TOOL_ERROR",
                "message": str(e),
            },
        }


def iter_segment_files(input_dir: Path) -> List[Path]:
    targets: List[Path] = []

    for path in sorted(input_dir.glob("*_segments.json")):
        name_lower = path.name.lower()

        if "decoded" in name_lower:
            continue
        if "strategy" in name_lower:
            continue
        if "residue" in name_lower:
            continue

        targets.append(path)

    return targets


def build_output_path(input_path: Path, output_dir: Path) -> Path:
    stem = input_path.stem
    if stem.endswith("_segments"):
        stem = stem[:-9]
    return output_dir / f"{stem}_decoded.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        default=r".\data\segments",
        help="Directory containing *_segments.json files (default: .\\data\\segments)",
    )
    parser.add_argument(
        "--output-dir",
        default=r".\data\decoded",
        help="Directory for *_decoded.json outputs (default: .\\data\\decoded)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists():
        print(json.dumps({
            "ok": False,
            "error": {
                "code": "ENCODING_DECODE_TOOL_ERROR",
                "message": f"input directory not found: {str(input_dir)}",
            }
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    target_files = iter_segment_files(input_dir)

    if not target_files:
        print(json.dumps({
            "ok": True,
            "message": "No *_segments.json files found.",
            "processed_files": 0,
        }, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    summary = []

    for input_file in target_files:
        result = encoding_decode_tool(segments_path=str(input_file))
        output_file = build_output_path(input_file, output_dir)

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        data = result.get("data") or {}

        summary.append(
            {
                "input": str(input_file),
                "output": str(output_file),
                "ok": result.get("ok"),
                "status": data.get("status"),
                "decoded_candidates": len(data.get("decoded_candidates", []) or []),
                "failed_candidates": len(data.get("failed_candidates", []) or []),
                "residue_candidates": len(data.get("residue_candidates", []) or []),
                "excluded_streams": len(data.get("excluded_streams", []) or []),
            }
        )

    print(json.dumps({
        "ok": True,
        "processed_files": len(summary),
        "results": summary,
    }, ensure_ascii=False, indent=2))