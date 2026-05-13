#!/usr/bin/env python3
r"""
llm_agent.py

7주차 패킷 디코딩 workflow용 LLM 리뷰/오케스트레이션 에이전트.

핵심 규칙
- .pending.json은 큐 파일이다.
- llm_agent.py는 모든 data/strategy/*.pending.json을 본다.
- 단, 모든 pending을 LLM에 넣지는 않는다.
- pending 내부 상태를 보고 다음 액션을 라우팅한다.

Pending routing
1. needs_llm_review == true
   - LLM 리뷰 수행
   - stop / stop_with_exclusion이면 .done.json 전환
   - retry_same_tool이면 noise_cleanup_tool.py 호출
   - noise cleanup 결과를 원본 pending에 병합
   - 원본 .pending.json 유지
   - required_next_action = run_encoding_decode_tool

2. needs_llm_review == false
   required_next_action == run_encoding_decode_tool
   - LLM 재호출하지 않음
   - retry_encoding.py 호출
   - retry_encoding.py가 성공 시 .done.json 전환

3. 기타 pending
   - unknown_pending으로 기록하고 건드리지 않음

중요 보정 로직
- LLM이 trailing '0' 같은 base64-valid noise 옵션을 빼먹을 수 있다.
- retry_same_tool + noise_cleanup_tool 상황에서는 enrich_retry_options()가
  deterministic하게 trim_trailing_base64_chars / max_trailing_trim 옵션을 보강한다.

실행
    py .\llm_agent.py

Dry run
    py .\llm_agent.py --dry-run

Tool spec 확인
    py .\llm_agent.py --print-tool-specs
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


ALLOWED_DECISIONS = {
    "stop",
    "stop_with_exclusion",
    "retry_same_tool",
    "call_other_tool",
}

DEFAULT_CONFIG_PATH = Path(r".\config\llm_config.json")
DEFAULT_STRATEGY_DIR = Path(r".\data\strategy")
DEFAULT_LLM_REVIEWS_DIR = Path(r".\data\llm_reviews")
DEFAULT_LOG_DIR = Path(r".\log")

BASE_DIR = Path(__file__).resolve().parent
NOISE_CLEANUP_TOOL_PATH = BASE_DIR / "llm_agents" / "noise_cleanup_tool.py"
RETRY_ENCODING_TOOL_PATH = BASE_DIR / "llm_agents" / "retry_encoding.py"


# -----------------------------------------------------------------------------
# Tool specs exposed to LLM
# -----------------------------------------------------------------------------

TOOL_SPECS: Dict[str, Dict[str, Any]] = {
    "noise_cleanup_tool": {
        "logical_role": "preprocess_for_retry_same_tool",
        "script_path": "llm_agents/noise_cleanup_tool.py",
        "description": (
            "Normalize noisy encoding candidates before retrying the same decoding family. "
            "This tool does not make the final decode decision. It generates normalized_candidates "
            "for retry_encoding.py."
        ),
        "use_for_decisions": ["retry_same_tool"],
        "when_to_use": [
            "A failed candidate appears mostly base64-like but contains removable trailing noise.",
            "A failed candidate has invalid suffix characters after padding, such as '==0' or '==;'.",
            "A failed candidate has broken or missing base64 padding.",
            "A candidate may be URL-encoded before base64 decoding, such as containing %3D instead of '='.",
            "A failed candidate has punctuation, delimiters, or transport artifacts mixed into an otherwise base64-like string.",
            "A failed candidate has a trailing character that is technically valid base64, but likely noise, such as a trailing '0'.",
        ],
        "when_not_to_use": [
            "The only unresolved items are encrypted TLS streams and there are no failed or residue candidates.",
            "The candidate is too short, not encoding-like, or clearly irrelevant.",
            "The decoded result is already sufficient and failed candidates are clear duplicate artifacts.",
            "The next step requires a different analysis family such as TLS metadata extraction rather than normalization.",
        ],
        "supported_options": {
            "url_decode_before_base64": {
                "type": "bool",
                "default": False,
                "description": "Apply URL decoding before base64 normalization. Use for percent-encoded candidates such as %3D or %2F.",
            },
            "strip_whitespace": {
                "type": "bool",
                "default": True,
                "description": "Remove whitespace before normalization. Usually safe for encoded payload candidates.",
            },
            "strip_trailing_noise": {
                "type": "bool",
                "default": False,
                "description": "Remove suffix noise after base64 padding or non-base64 trailing garbage. Use for cases like ABCD==0.",
            },
            "strip_invalid_base64_chars": {
                "type": "bool",
                "default": False,
                "description": "Remove characters outside base64/base64url alphabets. Use when separators, quotes, punctuation, or delimiters are embedded.",
            },
            "repair_base64_padding": {
                "type": "bool",
                "default": False,
                "description": "Repair missing base64 padding by appending '=' as needed.",
            },
            "trim_trailing_base64_chars": {
                "type": "bool",
                "default": False,
                "description": (
                    "If base64 decoding still fails, generate variants by trimming 1..N trailing base64 alphabet characters. "
                    "Use when the suffix is likely noise even though it is technically a valid base64 character, such as a trailing '0'."
                ),
            },
            "max_trailing_trim": {
                "type": "int",
                "default": 3,
                "description": (
                    "Maximum number of trailing base64 alphabet characters to trim when trim_trailing_base64_chars is enabled. "
                    "Use a small value such as 3 to avoid cutting real payload data too aggressively."
                ),
            },
            "deduplicate": {
                "type": "bool",
                "default": True,
                "description": "Remove duplicate normalized variants from output.",
            },
            "min_base64_length": {
                "type": "int",
                "default": 8,
                "description": "Minimum candidate length before base64-like normalization is attempted.",
            },
        },
        "expected_output": (
            "A JSON object containing normalized_candidates, base64_decodable_candidate_count, and best_candidates. "
            "llm_agent.py merges this output back into the original pending file."
        ),
    },
    "retry_encoding": {
        "logical_role": "retry_decoder_for_normalized_candidates",
        "script_path": "retry_encoding.py",
        "description": (
            "Re-decode normalized_candidates already embedded in a strategy pending file. "
            "This is called by llm_agent.py when required_next_action is run_encoding_decode_tool."
        ),
        "use_for_decisions": ["internal_router_only"],
        "when_to_use": [
            "A pending strategy file has required_next_action == run_encoding_decode_tool.",
            "noise_cleanup_tool has already produced normalized_candidates.",
        ],
        "when_not_to_use": [
            "The pending file still needs LLM review.",
            "No normalized_candidates are present.",
        ],
        "supported_options": {},
        "expected_output": "The strategy pending file is converted to .done.json when retry decode succeeds.",
    },
}


def build_tool_prompt_block() -> str:
    blocks: List[str] = []
    for tool_name, spec in TOOL_SPECS.items():
        lines: List[str] = []
        lines.append(f"Tool: {tool_name}")
        lines.append(f"Logical role: {spec['logical_role']}")
        lines.append(f"Script path: {spec['script_path']}")
        lines.append(f"Description: {spec['description']}")
        lines.append(f"Valid for decisions: {', '.join(spec['use_for_decisions'])}")
        lines.append("When to use:")
        for item in spec["when_to_use"]:
            lines.append(f"- {item}")
        lines.append("When not to use:")
        for item in spec["when_not_to_use"]:
            lines.append(f"- {item}")
        if spec.get("supported_options"):
            lines.append("Supported recommended_options:")
            for option_name, option_spec in spec["supported_options"].items():
                lines.append(
                    f"- {option_name} ({option_spec['type']}, default={option_spec['default']}): "
                    f"{option_spec['description']}"
                )
        lines.append(f"Expected output: {spec['expected_output']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def allowed_options_for_tool(tool_name: Optional[str]) -> set[str]:
    if not tool_name or tool_name not in TOOL_SPECS:
        return set()
    return set(TOOL_SPECS[tool_name].get("supported_options", {}).keys())


def sanitize_recommended_options(
    recommended_tool: Optional[str],
    options: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if options is None or not isinstance(options, dict):
        return None
    allowed = allowed_options_for_tool(recommended_tool)
    if not allowed:
        return options
    return {key: value for key, value in options.items() if key in allowed}


TOOL_PROMPT_BLOCK = build_tool_prompt_block()

LLM_REVIEW_SYSTEM_PROMPT = f"""
You are a packet decoding review agent and workflow orchestrator.

Your task is NOT to write broad malware commentary.
Your task is to review the decoded packet analysis result and decide whether
additional decoding verification is needed.

Important workflow rule:
- Do not terminate the workflow until a final result is reached.
- If additional tool processing is required, keep the case in pending state.
- Only stop or stop_with_exclusion are final decisions.
- retry_same_tool and call_other_tool are not final decisions. They must route the case to the next tool step.

You must choose exactly one decision:
- stop
- stop_with_exclusion
- retry_same_tool
- call_other_tool

Decision policy:

1. Use retry_same_tool when the current result contains failed candidates that
   may be recoverable by applying a more tolerant version of the same decoding
   method.

   Prefer retry_same_tool when failed candidates show signs such as:
   - removable trailing noise
   - invalid suffix characters
   - broken or missing base64 padding
   - URL-encoded base64 values
   - partial chunks
   - mostly-valid base64 with a small number of invalid characters
   - failed candidate still contains suspicious residue after partial decoding
   - a trailing character is technically valid base64 but likely noise, such as trailing '0'

   Do NOT classify a failed candidate as a harmless artifact merely because
   another decoded candidate already exists. If the failed candidate may encode
   a distinct payload, recommend retry_same_tool.

   For noisy base64 retry, prefer recommended_tool = noise_cleanup_tool.
   Include only supported options for noise_cleanup_tool.
   For base64 trailing noise, normally include:
   - strip_trailing_noise = true
   - strip_invalid_base64_chars = true
   - repair_base64_padding = true
   - trim_trailing_base64_chars = true
   - max_trailing_trim = 3

2. Use call_other_tool when the next useful step requires a different decoding
   or analysis family, not just retrying the same tool.

3. Use stop_with_exclusion when the visible payload has been decoded and the
   only unresolved items are explicitly excluded streams, especially encrypted
   TLS streams, with no failed candidates and no residue candidates.

   In that case, explain that payload decryption requires TLS session keys,
   key log material, endpoint session material, or another valid decryption
   source. Do not claim that metadata analysis is impossible; only payload
   decoding is blocked.

4. Use stop when the decoded result is sufficient and there are no meaningful
   failed candidates, residue candidates, or excluded streams requiring further
   decoding.

5. Be conservative about terminating noisy encoding failures.
   If a candidate is almost decodable, retry or recommend another tool rather
   than ending the workflow.

Available tools and supported options:

{TOOL_PROMPT_BLOCK}

Important output rules:
- Return JSON only. Do not wrap the response in markdown.
- recommended_tool must be one of the available tools when decision is retry_same_tool or call_other_tool.
- recommended_options must only use supported option names for the selected recommended_tool.

Required JSON fields:
{{
  "decision": "stop | stop_with_exclusion | retry_same_tool | call_other_tool",
  "completion_status": "string",
  "requires_additional_verification": true | false,
  "reason": "short reason",
  "recommended_tool": "string or null",
  "recommended_options": "object or null"
}}
""".strip()


# -----------------------------------------------------------------------------
# Logging helpers
# -----------------------------------------------------------------------------


def now_ts() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_filename_ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def write_agent_log(
    *,
    log_dir: Path,
    event: str,
    payload: Dict[str, Any],
    run_id: str,
) -> None:
    log_obj = {
        "ts": now_ts(),
        "run_id": run_id,
        "event": event,
        **payload,
    }
    append_jsonl(log_dir / "llm_agent_events.jsonl", log_obj)
    append_jsonl(log_dir / f"llm_agent_run_{run_id}.jsonl", log_obj)


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
# LLM config loading
# -----------------------------------------------------------------------------


def _resolve_api_key(config: Dict[str, Any]) -> str:
    api_key = str(config.get("api_key") or "").strip()
    if api_key:
        return api_key
    api_key_env = str(config.get("api_key_env") or "").strip()
    if api_key_env:
        env_value = os.getenv(api_key_env, "").strip()
        if env_value:
            return env_value
    raise ValueError("Missing API key. Set api_key in config or provide api_key_env environment variable.")


def load_llm_config(path: Path, profile_name: Optional[str] = None) -> Dict[str, Any]:
    raw = load_json(path)
    if "profiles" in raw:
        profiles = raw.get("profiles")
        if not isinstance(profiles, dict) or not profiles:
            raise ValueError("Config has 'profiles', but profiles is empty or invalid.")
        selected_profile = profile_name or raw.get("active_profile")
        if not selected_profile:
            raise ValueError("active_profile is missing. Use --profile or set active_profile in config.")
        if selected_profile not in profiles:
            available = sorted(profiles.keys())
            raise ValueError(f"Profile not found: {selected_profile}. Available profiles: {available}")
        profile = profiles[selected_profile]
        if not isinstance(profile, dict):
            raise ValueError(f"Profile must be object: {selected_profile}")
        config = dict(profile)
        config["profile_name"] = selected_profile
    else:
        config = dict(raw)
        config.setdefault("profile_name", "flat_config")

    required = ["model", "base_url"]
    missing = [k for k in required if not str(config.get(k) or "").strip()]
    if missing:
        raise ValueError(f"Missing required config fields: {missing}")

    config["api_key"] = _resolve_api_key(config)
    config.setdefault("provider", "openai_compatible")
    config.setdefault("api_style", "openai_chat_completions")
    config.setdefault("temperature", 0.0)
    config.setdefault("max_tokens", 800)
    config.setdefault("timeout_sec", config.get("timeout", 120))
    config.setdefault("max_retries", 2)
    config.setdefault("max_iterations", 3)
    config["temperature"] = float(config.get("temperature", 0.0))
    config["max_tokens"] = int(config.get("max_tokens", 800))
    config["timeout_sec"] = int(config.get("timeout_sec", 120))
    config["max_retries"] = int(config.get("max_retries", 2))
    config["max_iterations"] = int(config.get("max_iterations", 3))
    return config


# -----------------------------------------------------------------------------
# Pending routing helpers
# -----------------------------------------------------------------------------


def iter_all_pending_files(strategy_dir: Path) -> List[Path]:
    return sorted(strategy_dir.glob("*.pending.json"))


def classify_pending_obj(obj: Dict[str, Any]) -> str:
    if obj.get("needs_llm_review") is True:
        return "llm_review"
    if obj.get("required_next_action") == "run_encoding_decode_tool":
        return "retry_encoding"
    if obj.get("required_next_action") == "run_recommended_tool":
        return "recommended_tool"
    return "unknown_pending"


def classify_pending_file(path: Path) -> str:
    try:
        obj = load_json(path)
    except Exception:
        return "invalid_json"
    return classify_pending_obj(obj)


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


def noise_cleanup_result_path(strategy_path: Path) -> Path:
    name = strategy_path.name
    name = name.replace("_strategy.pending.json", "")
    name = name.replace(".pending.json", "")
    name = name.replace(".done.json", "")
    name = name.replace(".failed.json", "")
    return strategy_path.with_name(f"{name}_noise_cleanup.result.json")


# -----------------------------------------------------------------------------
# LLM calls
# -----------------------------------------------------------------------------


def _post_json_with_retry(
    *,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout_sec: int,
    max_retries: int,
) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
            resp.raise_for_status()
            obj = resp.json()
            if not isinstance(obj, dict):
                raise ValueError("LLM response JSON root is not object.")
            return obj
        except Exception as e:
            last_error = e
            if attempt >= max_retries:
                break
            time.sleep(min(2 ** attempt, 5))
    raise RuntimeError(f"LLM request failed after retries: {last_error}")


def _call_openai_chat_completions(prompt: str, config: Dict[str, Any]) -> str:
    url = config["base_url"].rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": LLM_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": config.get("temperature", 0.0),
        "max_tokens": config.get("max_tokens", 800),
    }
    obj = _post_json_with_retry(
        url=url,
        headers=headers,
        payload=payload,
        timeout_sec=int(config.get("timeout_sec", 120)),
        max_retries=int(config.get("max_retries", 2)),
    )
    choices = obj.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text
    return json.dumps(obj, ensure_ascii=False)


def _call_openai_responses(prompt: str, config: Dict[str, Any]) -> str:
    url = config["base_url"].rstrip("/") + "/responses"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "input": [
            {"role": "system", "content": LLM_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": config.get("temperature", 0.0),
        "max_output_tokens": config.get("max_tokens", 800),
    }
    obj = _post_json_with_retry(
        url=url,
        headers=headers,
        payload=payload,
        timeout_sec=int(config.get("timeout_sec", 120)),
        max_retries=int(config.get("max_retries", 2)),
    )
    if isinstance(obj.get("output_text"), str):
        return obj["output_text"]
    output = obj.get("output", [])
    chunks: List[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                text = c.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    if chunks:
        return "".join(chunks)
    return json.dumps(obj, ensure_ascii=False)


def call_llm_once(*, prompt: str, config: Dict[str, Any]) -> str:
    api_style = str(config.get("api_style") or "openai_chat_completions")
    if api_style == "openai_chat_completions":
        return _call_openai_chat_completions(prompt, config)
    if api_style == "openai_responses":
        return _call_openai_responses(prompt, config)
    raise ValueError(f"Unsupported api_style: {api_style}")


# -----------------------------------------------------------------------------
# LLM response parsing / validation / enrichment
# -----------------------------------------------------------------------------


def extract_json_block(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("LLM JSON response root must be object.")
        return obj
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        obj = json.loads(candidate)
        if not isinstance(obj, dict):
            raise ValueError("LLM JSON response root must be object.")
        return obj
    raise ValueError("LLM response does not contain valid JSON object.")


def validate_llm_decision(obj: Dict[str, Any]) -> Dict[str, Any]:
    decision = obj.get("decision")
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"Invalid decision from LLM: {decision}")
    recommended_tool = obj.get("recommended_tool")
    if recommended_tool is not None and not isinstance(recommended_tool, str):
        raise ValueError("recommended_tool must be string or null")
    recommended_options = obj.get("recommended_options")
    if recommended_options is not None and not isinstance(recommended_options, dict):
        raise ValueError("recommended_options must be dict or null")
    sanitized_options = sanitize_recommended_options(recommended_tool, recommended_options)
    return {
        "decision": decision,
        "completion_status": obj.get("completion_status"),
        "requires_additional_verification": obj.get("requires_additional_verification"),
        "reason": obj.get("reason"),
        "recommended_tool": recommended_tool,
        "recommended_options": sanitized_options,
        "raw_recommended_options": recommended_options,
    }


def _json_text(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


def _has_base64_like_trailing_noise(strategy_obj: Dict[str, Any], llm_result: Dict[str, Any]) -> bool:
    haystack = _json_text(
        {
            "reason": llm_result.get("reason"),
            "recommended_options": llm_result.get("recommended_options"),
            "failed_candidates_preview": strategy_obj.get("failed_candidates_preview"),
            "failed_candidates": strategy_obj.get("failed_candidates"),
            "residue_candidates_preview": strategy_obj.get("residue_candidates_preview"),
            "residue_candidates": strategy_obj.get("residue_candidates"),
            "llm_review_prompt": strategy_obj.get("llm_review_prompt"),
        }
    )
    lower = haystack.lower()

    if "trailing" in lower and "noise" in lower:
        return True
    if "invalid suffix" in lower:
        return True
    if "padding" in lower and "failed" in lower:
        return True
    if "cGluZyAtYyAxMCAxLjEuMS4x0" in haystack:
        return True

    tokens = set(re.findall(r"[A-Za-z0-9+/_=-]{12,}", haystack))
    for token in tokens:
        compact = re.sub(r"\s+", "", token).rstrip("=")
        if len(compact) >= 12 and len(compact) % 4 == 1:
            return True

    return False


def enrich_retry_options(
    *,
    llm_result: Dict[str, Any],
    strategy_obj: Dict[str, Any],
) -> None:
    if llm_result.get("decision") != "retry_same_tool":
        return

    recommended_tool = llm_result.get("recommended_tool") or "noise_cleanup_tool"
    if recommended_tool not in {"noise_cleanup_tool", "encoding_decode_tool"}:
        return

    options = dict(llm_result.get("recommended_options") or {})

    if _has_base64_like_trailing_noise(strategy_obj, llm_result):
        options.setdefault("strip_trailing_noise", True)
        options.setdefault("strip_invalid_base64_chars", True)
        options.setdefault("repair_base64_padding", True)
        options.setdefault("trim_trailing_base64_chars", True)
        options.setdefault("max_trailing_trim", 3)

    llm_result["recommended_tool"] = "noise_cleanup_tool"
    llm_result["recommended_options"] = sanitize_recommended_options("noise_cleanup_tool", options)


# -----------------------------------------------------------------------------
# Tool execution
# -----------------------------------------------------------------------------


def execute_noise_cleanup_tool(
    *,
    strategy_path: Path,
    recommended_options: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    output_path = noise_cleanup_result_path(strategy_path)
    options = recommended_options or {}

    if not NOISE_CLEANUP_TOOL_PATH.exists():
        return {
            "action": "noise_cleanup",
            "executed": False,
            "tool": "noise_cleanup_tool",
            "tool_path": str(NOISE_CLEANUP_TOOL_PATH),
            "output_file": str(output_path),
            "error": "noise_cleanup_tool.py not found",
        }

    cmd = [
        sys.executable,
        str(NOISE_CLEANUP_TOOL_PATH),
        "--input",
        str(strategy_path),
        "--output",
        str(output_path),
        "--options-json",
        json.dumps(options, ensure_ascii=False),
    ]

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    result: Dict[str, Any] = {
        "action": "noise_cleanup",
        "executed": completed.returncode == 0,
        "tool": "noise_cleanup_tool",
        "tool_path": str(NOISE_CLEANUP_TOOL_PATH),
        "command": cmd,
        "output_file": str(output_path),
        "options": options,
        "returncode": completed.returncode,
        "stdout_preview": completed.stdout[-2000:] if completed.stdout else "",
        "stderr_preview": completed.stderr[-2000:] if completed.stderr else "",
    }

    if output_path.exists():
        try:
            output_obj = load_json(output_path)
            result["ok"] = output_obj.get("ok")
            result["candidate_count"] = output_obj.get("candidate_count")
            result["normalized_candidate_count"] = output_obj.get("normalized_candidate_count")
            result["base64_decodable_candidate_count"] = output_obj.get("base64_decodable_candidate_count")
            result["normalized_candidates"] = output_obj.get("normalized_candidates", [])
            result["best_candidates"] = output_obj.get("best_candidates", [])[:5]
        except Exception as e:
            result["output_read_error"] = str(e)

    if completed.returncode != 0:
        result["error"] = "noise_cleanup_tool failed"

    return result


def execute_retry_encoding_tool(*, strategy_path: Path) -> Dict[str, Any]:
    if not RETRY_ENCODING_TOOL_PATH.exists():
        return {
            "action": "retry_encoding",
            "executed": False,
            "tool": "retry_encoding",
            "tool_path": str(RETRY_ENCODING_TOOL_PATH),
            "error": "retry_encoding.py not found",
        }

    cmd = [
        sys.executable,
        str(RETRY_ENCODING_TOOL_PATH),
        "--strategy-file",
        str(strategy_path),
    ]

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    parsed_stdout: Optional[Dict[str, Any]] = None
    if completed.stdout:
        try:
            parsed = json.loads(completed.stdout)
            if isinstance(parsed, dict):
                parsed_stdout = parsed
        except Exception:
            parsed_stdout = None

    return {
        "action": "retry_encoding",
        "executed": completed.returncode == 0,
        "tool": "retry_encoding",
        "tool_path": str(RETRY_ENCODING_TOOL_PATH),
        "command": cmd,
        "returncode": completed.returncode,
        "stdout_preview": completed.stdout[-3000:] if completed.stdout else "",
        "stderr_preview": completed.stderr[-3000:] if completed.stderr else "",
        "parsed_stdout": parsed_stdout,
        "error": None if completed.returncode == 0 else "retry_encoding failed",
    }


def build_action_result(
    *,
    llm_result: Dict[str, Any],
    strategy_path: Path,
) -> Optional[Dict[str, Any]]:
    decision = llm_result["decision"]

    if decision == "retry_same_tool":
        recommended_tool = llm_result.get("recommended_tool") or "noise_cleanup_tool"
        recommended_options = llm_result.get("recommended_options")
        cleanup_result = execute_noise_cleanup_tool(
            strategy_path=strategy_path,
            recommended_options=recommended_options,
        )
        return {
            "action": "retry_same_tool",
            "executed": cleanup_result.get("executed", False),
            "status": "tool_executed" if cleanup_result.get("executed") else "tool_failed",
            "reason": "Noise cleanup preprocessing executed and merged into the original pending file for the next batch step.",
            "recommended_tool": recommended_tool,
            "recommended_options": recommended_options,
            "raw_recommended_options": llm_result.get("raw_recommended_options"),
            "preprocess_tool": "noise_cleanup_tool",
            "preprocess_result_file": cleanup_result.get("output_file"),
            "cleanup_result": cleanup_result,
            "next_tool": "retry_encoding",
            "next_input": "self",
            "next_step": "Next llm_agent batch should route this pending file to retry_encoding.py.",
            "source_strategy": str(strategy_path),
        }

    if decision == "call_other_tool":
        recommended_tool = llm_result.get("recommended_tool")
        return {
            "action": "call_other_tool",
            "executed": False,
            "status": "planned_only",
            "reason": "Other-tool orchestration is not implemented yet. Workflow remains pending for the recommended tool.",
            "recommended_tool": recommended_tool,
            "recommended_options": llm_result.get("recommended_options"),
            "raw_recommended_options": llm_result.get("raw_recommended_options"),
            "tool_spec_known": recommended_tool in TOOL_SPECS if recommended_tool else False,
            "tool_script_path": TOOL_SPECS.get(recommended_tool, {}).get("script_path") if recommended_tool else None,
            "source_strategy": str(strategy_path),
        }

    return None


# -----------------------------------------------------------------------------
# Output object builders
# -----------------------------------------------------------------------------


def build_llm_review_output(
    *,
    strategy_path: Path,
    strategy_obj: Dict[str, Any],
    llm_raw_text: str,
    llm_result: Dict[str, Any],
    llm_config: Dict[str, Any],
    action_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "input_strategy": str(strategy_path),
        "source_decoded": strategy_obj.get("input"),
        "llm_profile": llm_config.get("profile_name"),
        "llm_provider": llm_config.get("provider"),
        "llm_model": llm_config.get("model"),
        "llm_api_style": llm_config.get("api_style"),
        "llm_decision": llm_result["decision"],
        "llm_completion_status": llm_result.get("completion_status"),
        "requires_additional_verification": llm_result.get("requires_additional_verification"),
        "reason": llm_result.get("reason"),
        "recommended_tool": llm_result.get("recommended_tool"),
        "recommended_options": llm_result.get("recommended_options"),
        "raw_recommended_options": llm_result.get("raw_recommended_options"),
        "raw_llm_response": llm_raw_text,
        "action_result": action_result,
        "error": None,
    }


def update_strategy_payload_final_done(
    strategy_obj: Dict[str, Any],
    llm_result: Dict[str, Any],
    llm_review_output_file: str,
    action_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    new_obj = dict(strategy_obj)
    new_obj["decision"] = llm_result["decision"]
    new_obj["completion_status"] = llm_result.get("completion_status") or strategy_obj.get("completion_status")
    new_obj["needs_llm_review"] = False
    new_obj["required_next_action"] = None
    new_obj["llm_review_result"] = {
        "decision": llm_result["decision"],
        "completion_status": llm_result.get("completion_status"),
        "requires_additional_verification": llm_result.get("requires_additional_verification"),
        "reason": llm_result.get("reason"),
        "recommended_tool": llm_result.get("recommended_tool"),
        "recommended_options": llm_result.get("recommended_options"),
        "raw_recommended_options": llm_result.get("raw_recommended_options"),
        "action_result": action_result,
        "llm_review_output_file": llm_review_output_file,
    }
    return new_obj


def update_strategy_payload_pending_next_action(
    strategy_obj: Dict[str, Any],
    llm_result: Dict[str, Any],
    llm_review_output_file: str,
    action_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    new_obj = dict(strategy_obj)
    new_obj["decision"] = llm_result["decision"]
    new_obj["completion_status"] = llm_result.get("completion_status") or "normalized_pending"
    new_obj["needs_llm_review"] = False

    if llm_result["decision"] == "retry_same_tool":
        cleanup_result = action_result.get("cleanup_result", {}) if isinstance(action_result, dict) else {}
        normalized_candidates = cleanup_result.get("normalized_candidates", [])
        best_candidates = cleanup_result.get("best_candidates", [])

        new_obj["required_next_action"] = "run_encoding_decode_tool"
        new_obj["next_tool"] = "retry_encoding"
        new_obj["next_tool_input"] = "self"
        new_obj["preprocess_tool"] = "noise_cleanup_tool"
        new_obj["preprocess_result_file"] = cleanup_result.get("output_file")
        new_obj["noise_cleanup_result"] = {
            "executed": cleanup_result.get("executed"),
            "ok": cleanup_result.get("ok"),
            "candidate_count": cleanup_result.get("candidate_count"),
            "normalized_candidate_count": cleanup_result.get("normalized_candidate_count"),
            "base64_decodable_candidate_count": cleanup_result.get("base64_decodable_candidate_count"),
            "options": cleanup_result.get("options"),
            "output_file": cleanup_result.get("output_file"),
            "error": cleanup_result.get("error"),
        }
        new_obj["normalized_candidates"] = normalized_candidates
        new_obj["best_normalized_candidates"] = best_candidates

    elif llm_result["decision"] == "call_other_tool":
        new_obj["required_next_action"] = "run_recommended_tool"
        new_obj["next_tool"] = llm_result.get("recommended_tool")
        new_obj["next_tool_input"] = "self"

    new_obj["llm_review_result"] = {
        "decision": llm_result["decision"],
        "completion_status": llm_result.get("completion_status"),
        "requires_additional_verification": llm_result.get("requires_additional_verification"),
        "reason": llm_result.get("reason"),
        "recommended_tool": llm_result.get("recommended_tool"),
        "recommended_options": llm_result.get("recommended_options"),
        "raw_recommended_options": llm_result.get("raw_recommended_options"),
        "action_result": action_result,
        "llm_review_output_file": llm_review_output_file,
    }
    return new_obj


def update_strategy_payload_failed(strategy_obj: Dict[str, Any], error_message: str) -> Dict[str, Any]:
    new_obj = dict(strategy_obj)
    new_obj["needs_llm_review"] = True
    new_obj["llm_review_error"] = error_message
    return new_obj


# -----------------------------------------------------------------------------
# Processing: LLM review branch
# -----------------------------------------------------------------------------


def process_llm_review_pending(
    *,
    strategy_path: Path,
    llm_reviews_dir: Path,
    llm_config: Dict[str, Any],
    log_dir: Path,
    run_id: str,
) -> Dict[str, Any]:
    write_agent_log(
        log_dir=log_dir,
        run_id=run_id,
        event="process_llm_review_start",
        payload={"strategy_path": str(strategy_path)},
    )

    strategy_obj = load_json(strategy_path)
    prompt = strategy_obj.get("llm_review_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("llm_review_prompt is missing or empty.")

    llm_raw = call_llm_once(prompt=prompt, config=llm_config)
    write_agent_log(
        log_dir=log_dir,
        run_id=run_id,
        event="llm_response_received",
        payload={"strategy_path": str(strategy_path), "raw_response_preview": llm_raw[:1000]},
    )

    parsed = extract_json_block(llm_raw)
    llm_result = validate_llm_decision(parsed)
    enrich_retry_options(llm_result=llm_result, strategy_obj=strategy_obj)

    write_agent_log(
        log_dir=log_dir,
        run_id=run_id,
        event="llm_decision",
        payload={
            "strategy_path": str(strategy_path),
            "decision": llm_result.get("decision"),
            "completion_status": llm_result.get("completion_status"),
            "recommended_tool": llm_result.get("recommended_tool"),
            "recommended_options": llm_result.get("recommended_options"),
            "raw_recommended_options": llm_result.get("raw_recommended_options"),
        },
    )

    action_result = build_action_result(llm_result=llm_result, strategy_path=strategy_path)
    write_agent_log(
        log_dir=log_dir,
        run_id=run_id,
        event="action_result",
        payload={"strategy_path": str(strategy_path), "action_result": action_result},
    )

    review_output_path = llm_reviews_dir / f"{strategy_path.stem.replace('.pending', '')}_llm_review.json"
    review_obj = build_llm_review_output(
        strategy_path=strategy_path,
        strategy_obj=strategy_obj,
        llm_raw_text=llm_raw,
        llm_result=llm_result,
        llm_config=llm_config,
        action_result=action_result,
    )
    write_json(review_output_path, review_obj)

    if llm_result["decision"] in {"stop", "stop_with_exclusion"}:
        updated_strategy = update_strategy_payload_final_done(
            strategy_obj=strategy_obj,
            llm_result=llm_result,
            llm_review_output_file=str(review_output_path),
            action_result=action_result,
        )
        output_strategy_path = replace_status_suffix(strategy_path, "done")
        write_json(output_strategy_path, updated_strategy)
        if output_strategy_path != strategy_path and strategy_path.exists():
            strategy_path.unlink()
        final_file_status = "done"
    else:
        updated_strategy = update_strategy_payload_pending_next_action(
            strategy_obj=strategy_obj,
            llm_result=llm_result,
            llm_review_output_file=str(review_output_path),
            action_result=action_result,
        )
        output_strategy_path = strategy_path
        write_json(output_strategy_path, updated_strategy)
        final_file_status = "pending"

    result = {
        "input": str(strategy_path),
        "output": str(output_strategy_path),
        "route": "llm_review",
        "file_status": final_file_status,
        "llm_review_output": str(review_output_path),
        "decision": llm_result["decision"],
        "completion_status": llm_result.get("completion_status"),
        "recommended_tool": llm_result.get("recommended_tool"),
        "recommended_options": llm_result.get("recommended_options"),
        "required_next_action": updated_strategy.get("required_next_action"),
        "next_tool": updated_strategy.get("next_tool"),
        "next_tool_input": updated_strategy.get("next_tool_input"),
        "action_executed": action_result.get("executed") if isinstance(action_result, dict) else None,
    }

    write_agent_log(log_dir=log_dir, run_id=run_id, event="process_llm_review_done", payload=result)
    return result


# -----------------------------------------------------------------------------
# Processing: retry encoding branch
# -----------------------------------------------------------------------------


def process_retry_encoding_pending(
    *,
    strategy_path: Path,
    log_dir: Path,
    run_id: str,
) -> Dict[str, Any]:
    write_agent_log(
        log_dir=log_dir,
        run_id=run_id,
        event="process_retry_encoding_start",
        payload={"strategy_path": str(strategy_path)},
    )

    action_result = execute_retry_encoding_tool(strategy_path=strategy_path)

    write_agent_log(
        log_dir=log_dir,
        run_id=run_id,
        event="retry_encoding_result",
        payload={"strategy_path": str(strategy_path), "action_result": action_result},
    )

    parsed_stdout = action_result.get("parsed_stdout") or {}
    results = parsed_stdout.get("results") if isinstance(parsed_stdout, dict) else None
    first_result = results[0] if isinstance(results, list) and results else {}

    result = {
        "input": str(strategy_path),
        "route": "retry_encoding",
        "action_executed": action_result.get("executed"),
        "retry_returncode": action_result.get("returncode"),
        "retry_status": first_result.get("status"),
        "output": first_result.get("output"),
        "file_status": first_result.get("file_status"),
        "selected_count": first_result.get("selected_count"),
        "error": action_result.get("error"),
    }

    write_agent_log(log_dir=log_dir, run_id=run_id, event="process_retry_encoding_done", payload=result)
    return result


# -----------------------------------------------------------------------------
# Processing router
# -----------------------------------------------------------------------------


def process_pending_file(
    *,
    strategy_path: Path,
    llm_reviews_dir: Path,
    llm_config: Dict[str, Any],
    log_dir: Path,
    run_id: str,
) -> Dict[str, Any]:
    route = classify_pending_file(strategy_path)

    write_agent_log(
        log_dir=log_dir,
        run_id=run_id,
        event="classify_pending",
        payload={"strategy_path": str(strategy_path), "route": route},
    )

    if route == "llm_review":
        return process_llm_review_pending(
            strategy_path=strategy_path,
            llm_reviews_dir=llm_reviews_dir,
            llm_config=llm_config,
            log_dir=log_dir,
            run_id=run_id,
        )

    if route == "retry_encoding":
        return process_retry_encoding_pending(
            strategy_path=strategy_path,
            log_dir=log_dir,
            run_id=run_id,
        )

    return {
        "input": str(strategy_path),
        "route": route,
        "file_status": "pending",
        "processed": False,
        "reason": "No executable route for this pending file.",
    }


def process_one_with_error_handling(
    *,
    strategy_path: Path,
    llm_reviews_dir: Path,
    llm_config: Dict[str, Any],
    log_dir: Path,
    run_id: str,
) -> Dict[str, Any]:
    try:
        return process_pending_file(
            strategy_path=strategy_path,
            llm_reviews_dir=llm_reviews_dir,
            llm_config=llm_config,
            log_dir=log_dir,
            run_id=run_id,
        )
    except Exception as e:
        write_agent_log(
            log_dir=log_dir,
            run_id=run_id,
            event="process_file_error",
            payload={"strategy_path": str(strategy_path), "error": str(e)},
        )
        try:
            strategy_obj = load_json(strategy_path)
            failed_path = replace_status_suffix(strategy_path, "failed")
            updated = update_strategy_payload_failed(strategy_obj, str(e))
            write_json(failed_path, updated)
            if failed_path != strategy_path and strategy_path.exists():
                strategy_path.unlink()
            return {
                "input": str(strategy_path),
                "output": str(failed_path),
                "file_status": "failed",
                "decision": None,
                "completion_status": None,
                "error": str(e),
            }
        except Exception as nested:
            return {
                "input": str(strategy_path),
                "output": None,
                "file_status": None,
                "decision": None,
                "completion_status": None,
                "error": str(e),
                "error_during_failure_write": str(nested),
            }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-dir", default=str(DEFAULT_STRATEGY_DIR))
    parser.add_argument("--llm-reviews-dir", default=str(DEFAULT_LLM_REVIEWS_DIR))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--profile", default="")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-tool-specs", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = safe_filename_ts()
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    if args.print_tool_specs:
        print(TOOL_PROMPT_BLOCK)
        write_agent_log(log_dir=log_dir, run_id=run_id, event="print_tool_specs", payload={"available_tools": sorted(TOOL_SPECS.keys())})
        raise SystemExit(0)

    strategy_dir = Path(args.strategy_dir)
    llm_reviews_dir = Path(args.llm_reviews_dir)
    config_path = Path(args.config)
    profile_name = args.profile.strip() or None

    write_agent_log(
        log_dir=log_dir,
        run_id=run_id,
        event="agent_start",
        payload={
            "strategy_dir": str(strategy_dir),
            "llm_reviews_dir": str(llm_reviews_dir),
            "config_path": str(config_path),
            "profile": profile_name,
            "noise_cleanup_tool_path": str(NOISE_CLEANUP_TOOL_PATH),
            "retry_encoding_tool_path": str(RETRY_ENCODING_TOOL_PATH),
        },
    )

    if not strategy_dir.exists():
        error_obj = {"ok": False, "error": {"code": "LLM_AGENT_ERROR", "message": f"strategy directory not found: {str(strategy_dir)}"}}
        write_agent_log(log_dir=log_dir, run_id=run_id, event="agent_error", payload=error_obj)
        print(json.dumps(error_obj, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    if not config_path.exists():
        error_obj = {"ok": False, "error": {"code": "LLM_AGENT_ERROR", "message": f"config file not found: {str(config_path)}"}}
        write_agent_log(log_dir=log_dir, run_id=run_id, event="agent_error", payload=error_obj)
        print(json.dumps(error_obj, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    try:
        llm_config = load_llm_config(config_path, profile_name=profile_name)
    except Exception as e:
        error_obj = {"ok": False, "error": {"code": "LLM_CONFIG_ERROR", "message": str(e)}}
        write_agent_log(log_dir=log_dir, run_id=run_id, event="agent_error", payload=error_obj)
        print(json.dumps(error_obj, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    pending_files = iter_all_pending_files(strategy_dir)
    route_counts: Dict[str, int] = {}
    routes: Dict[str, List[str]] = {}
    for path in pending_files:
        route = classify_pending_file(path)
        route_counts[route] = route_counts.get(route, 0) + 1
        routes.setdefault(route, []).append(str(path))

    if args.dry_run:
        dry_obj = {
            "ok": True,
            "dry_run": True,
            "llm_profile": llm_config.get("profile_name"),
            "llm_provider": llm_config.get("provider"),
            "llm_model": llm_config.get("model"),
            "llm_api_style": llm_config.get("api_style"),
            "pending_files": [str(p) for p in pending_files],
            "pending_count": len(pending_files),
            "route_counts": route_counts,
            "routes": routes,
            "available_tools": sorted(TOOL_SPECS.keys()),
            "noise_cleanup_tool_path": str(NOISE_CLEANUP_TOOL_PATH),
            "retry_encoding_tool_path": str(RETRY_ENCODING_TOOL_PATH),
        }
        write_agent_log(log_dir=log_dir, run_id=run_id, event="dry_run", payload=dry_obj)
        print(json.dumps(dry_obj, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    llm_reviews_dir.mkdir(parents=True, exist_ok=True)

    if not pending_files:
        result_obj = {
            "ok": True,
            "message": "No *.pending.json files found.",
            "processed_files": 0,
            "pending_count": 0,
            "route_counts": {},
            "llm_profile": llm_config.get("profile_name"),
            "llm_provider": llm_config.get("provider"),
            "llm_model": llm_config.get("model"),
            "available_tools": sorted(TOOL_SPECS.keys()),
        }
        write_agent_log(log_dir=log_dir, run_id=run_id, event="agent_finish", payload=result_obj)
        print(json.dumps(result_obj, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    summary = []
    for strategy_path in pending_files:
        summary.append(
            process_one_with_error_handling(
                strategy_path=strategy_path,
                llm_reviews_dir=llm_reviews_dir,
                llm_config=llm_config,
                log_dir=log_dir,
                run_id=run_id,
            )
        )

    result_obj = {
        "ok": True,
        "processed_files": len(summary),
        "pending_count": len(pending_files),
        "route_counts": route_counts,
        "llm_profile": llm_config.get("profile_name"),
        "llm_provider": llm_config.get("provider"),
        "llm_model": llm_config.get("model"),
        "available_tools": sorted(TOOL_SPECS.keys()),
        "log_dir": str(log_dir),
        "run_id": run_id,
        "results": summary,
    }
    write_agent_log(log_dir=log_dir, run_id=run_id, event="agent_finish", payload=result_obj)
    print(json.dumps(result_obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
