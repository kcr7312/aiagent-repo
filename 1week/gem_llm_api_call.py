from getpass import getpass
from google import genai
from pathlib import Path
import json
import time
import re
from typing import Any, Dict, List, Tuple


VERSION = "v1.0.2"

BASE_DIR = Path(__file__).resolve().parent
MESSAGES_PATH = BASE_DIR / "customer_messages_12.txt"
DATASET_PATH = BASE_DIR / "dataset.jsonl"
OUTPUT_V1_PATH = BASE_DIR / "output_v1.json"
OUTPUT_V2_PATH = BASE_DIR / "output_v2.json"
REPORT_PATH = BASE_DIR / "report_summary.txt"

ALLOWED_INTENTS = {"order_change", "shipping_issue", "payment_issue", "refund_exchange", "other"}
ALLOWED_URGENCY = {"low", "medium", "high"}
ALLOWED_ROUTE_TO = {"order_ops", "shipping_ops", "billing_ops", "returns_ops", "human_support"}
REQUIRED_FIELDS = {"intent", "urgency", "needs_clarification", "route_to"}

REQUEST_INTERVAL_SECONDS = 120
MAX_RATE_LIMIT_RETRIES = 10
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 120
PROMPT_SET_PAUSE_SECONDS = 120

PROMPT_V1 = """
You are a support triage assistant.

Return only valid JSON with exactly these fields:
- intent: one of [order_change, shipping_issue, payment_issue, refund_exchange, other]
- urgency: one of [low, medium, high]
- needs_clarification: boolean
- route_to: one of [order_ops, shipping_ops, billing_ops, returns_ops, human_support]

Do not include any explanation. Output JSON only.
""".strip()

PROMPT_V2 = """
You are a support ticket classification assistant.

Classify each customer message into exactly one JSON object.
Return only valid JSON.

Required schema:
{
  "intent": "order_change | shipping_issue | payment_issue | refund_exchange | other",
  "urgency": "low | medium | high",
  "needs_clarification": true or false,
  "route_to": "order_ops | shipping_ops | billing_ops | returns_ops | human_support"
}

Rules:
- Output exactly the 4 fields above. No extra fields.
- needs_clarification is true only when the request is too ambiguous to route confidently.
- Choose the single best label even if multiple issues are mentioned.
- For payment charge/failure/duplicate charge issues, prefer payment_issue and billing_ops.
- For delivery status / delivered-but-not-received issues, prefer shipping_issue and shipping_ops.
- For exchange/refund procedure questions, prefer refund_exchange and returns_ops.
- For changing order details such as address, color, or options before shipment, prefer order_change and order_ops.
- No markdown, no code fences, no explanation.
""".strip()


def load_messages(txt_path: Path) -> List[str]:
    if not txt_path.exists():
        raise FileNotFoundError(f"Messages file not found: {txt_path}")

    raw = txt_path.read_text(encoding="utf-8").strip()
    blocks = [block.strip() for block in raw.split("\n\n") if block.strip()]
    messages: List[str] = []

    for block in blocks:
        if ". " in block:
            _, message = block.split(". ", 1)
            messages.append(message.strip())
        else:
            messages.append(block.strip())

    return messages


def load_expected_outputs(dataset_path: Path) -> List[Dict[str, Any]]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

    expected: List[Dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            expected.append(row["expected_output"])
    return expected


def parse_json_response(text: str) -> Dict[str, Any]:
    return json.loads(text.strip())


def validate_prediction(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    if not isinstance(data, dict):
        return False, ["Output is not a JSON object"]

    actual_fields = set(data.keys())
    if actual_fields != REQUIRED_FIELDS:
        missing = REQUIRED_FIELDS - actual_fields
        extra = actual_fields - REQUIRED_FIELDS
        if missing:
            errors.append(f"Missing fields: {sorted(missing)}")
        if extra:
            errors.append(f"Extra fields: {sorted(extra)}")

    intent = data.get("intent")
    urgency = data.get("urgency")
    needs_clarification = data.get("needs_clarification")
    route_to = data.get("route_to")

    if intent not in ALLOWED_INTENTS:
        errors.append(f"Invalid intent: {intent}")
    if urgency not in ALLOWED_URGENCY:
        errors.append(f"Invalid urgency: {urgency}")
    if not isinstance(needs_clarification, bool):
        errors.append(f"needs_clarification must be boolean: {needs_clarification}")
    if route_to not in ALLOWED_ROUTE_TO:
        errors.append(f"Invalid route_to: {route_to}")

    return len(errors) == 0, errors


def is_rate_limit_error(error_message: str) -> bool:
    error_upper = error_message.upper()
    return (
        "429" in error_message
        or "RESOURCE_EXHAUSTED" in error_upper
        or "RATE LIMIT" in error_upper
        or "QUOTA" in error_upper
    )


def extract_retry_delay_seconds(error_message: str) -> int | None:
    patterns = [
        r'retryDelay\"\s*:\s*\"?(\d+)s\"?',
        r'retryDelay\s*[:=]\s*\"?(\d+)s\"?',
        r'(\d+)s',
    ]

    for pattern in patterns:
        match = re.search(pattern, error_message)
        if match:
            try:
                seconds = int(match.group(1))
                if seconds > 0:
                    return seconds
            except ValueError:
                pass
    return None


def generate_with_retry(
    client: genai.Client,
    model: str,
    temperature: float,
    max_output_tokens: int,
    system_prompt: str,
    user_prompt: str,
) -> str:
    last_error = None

    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config={
                    "system_instruction": system_prompt,
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens,
                    "response_mime_type": "application/json",
                },
            )
            return response.text
        except Exception as e:
            last_error = e
            error_message = str(e)

            if attempt < MAX_RATE_LIMIT_RETRIES and is_rate_limit_error(error_message):
                suggested_wait = extract_retry_delay_seconds(error_message)
                wait_seconds = max(DEFAULT_RATE_LIMIT_WAIT_SECONDS, suggested_wait or 0)
                print(
                    f"[rate-limit] retry {attempt + 1}/{MAX_RATE_LIMIT_RETRIES} "
                    f"waiting {wait_seconds}s before retry..."
                )
                time.sleep(wait_seconds)
                continue

            raise last_error

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unknown error during generate_with_retry")


def run_prompt_set(
    client: genai.Client,
    model: str,
    temperature: float,
    max_output_tokens: int,
    system_prompt: str,
    prompt_name: str,
    messages: List[str],
    expected_outputs: List[Dict[str, Any]],
    output_path: Path,
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    parsing_success = 0
    exact_match_count = 0
    failures: List[Dict[str, Any]] = []

    for idx, message in enumerate(messages, start=1):
        print(f"[{prompt_name}] processing {idx}/{len(messages)}")
        user_prompt = f'Customer message: "{message}"'
        raw_text = ""
        parsed: Dict[str, Any] | None = None
        valid = False
        validation_errors: List[str] = []
        match = False
        error_message = None

        try:
            raw_text = generate_with_retry(
                client=client,
                model=model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            parsed = parse_json_response(raw_text)
            valid, validation_errors = validate_prediction(parsed)

            if valid:
                parsing_success += 1
                expected = expected_outputs[idx - 1]
                match = parsed == expected
                if match:
                    exact_match_count += 1
            else:
                error_message = "; ".join(validation_errors)
        except Exception as e:
            error_message = str(e)

        result = {
            "index": idx,
            "customer_message": message,
            "raw_output": raw_text,
            "parsed_output": parsed,
            "valid_json_schema": valid,
            "validation_errors": validation_errors,
            "expected_output": expected_outputs[idx - 1],
            "exact_match": match,
            "error": error_message,
            "prompt_version": prompt_name,
        }
        results.append(result)

        if (not valid) or (not match):
            failures.append(
                {
                    "index": idx,
                    "customer_message": message,
                    "parsed_output": parsed,
                    "expected_output": expected_outputs[idx - 1],
                    "validation_errors": validation_errors,
                    "error": error_message,
                    "exact_match": match,
                }
            )

        output_snapshot = {
            "version": VERSION,
            "prompt_version": prompt_name,
            "model": model,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "request_interval_seconds": REQUEST_INTERVAL_SECONDS,
            "max_rate_limit_retries": MAX_RATE_LIMIT_RETRIES,
            "default_rate_limit_wait_seconds": DEFAULT_RATE_LIMIT_WAIT_SECONDS,
            "total_messages": len(messages),
            "processed_messages": len(results),
            "parsing_success_count": parsing_success,
            "parsing_success_rate": round(parsing_success / len(results), 4) if results else 0.0,
            "exact_match_count": exact_match_count,
            "exact_match_rate": round(exact_match_count / len(results), 4) if results else 0.0,
            "failure_cases": failures[:3],
            "results": results,
        }
        output_path.write_text(json.dumps(output_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

        if idx < len(messages):
            print(f"[{prompt_name}] sleeping {REQUEST_INTERVAL_SECONDS}s...")
            time.sleep(REQUEST_INTERVAL_SECONDS)

    summary = {
        "version": VERSION,
        "prompt_version": prompt_name,
        "model": model,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "request_interval_seconds": REQUEST_INTERVAL_SECONDS,
        "max_rate_limit_retries": MAX_RATE_LIMIT_RETRIES,
        "default_rate_limit_wait_seconds": DEFAULT_RATE_LIMIT_WAIT_SECONDS,
        "total_messages": len(messages),
        "parsing_success_count": parsing_success,
        "parsing_success_rate": round(parsing_success / len(messages), 4) if messages else 0.0,
        "exact_match_count": exact_match_count,
        "exact_match_rate": round(exact_match_count / len(messages), 4) if messages else 0.0,
        "failure_cases": failures[:3],
        "results": results,
    }

    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def write_report(summary_v1: Dict[str, Any], summary_v2: Dict[str, Any], report_path: Path) -> None:
    lines = []
    lines.append(f"[Prompt Experiment Summary - {VERSION}]\n")

    for summary in (summary_v1, summary_v2):
        lines.append(f"{summary['prompt_version']}")
        lines.append(f"- total_messages: {summary['total_messages']}")
        lines.append(f"- parsing_success_count: {summary['parsing_success_count']}")
        lines.append(f"- parsing_success_rate: {summary['parsing_success_rate']}")
        lines.append(f"- exact_match_count: {summary['exact_match_count']}")
        lines.append(f"- exact_match_rate: {summary['exact_match_rate']}")
        lines.append(f"- request_interval_seconds: {summary['request_interval_seconds']}")
        lines.append(f"- max_rate_limit_retries: {summary['max_rate_limit_retries']}")
        lines.append(f"- default_rate_limit_wait_seconds: {summary['default_rate_limit_wait_seconds']}")
        lines.append("- representative_failures:")

        if summary["failure_cases"]:
            for case in summary["failure_cases"]:
                lines.append(f"  * index {case['index']}: {case['customer_message']}")
                lines.append(f"    expected: {json.dumps(case['expected_output'], ensure_ascii=False)}")
                lines.append(f"    predicted: {json.dumps(case['parsed_output'], ensure_ascii=False)}")
                if case["validation_errors"]:
                    lines.append(f"    validation_errors: {case['validation_errors']}")
                if case["error"]:
                    lines.append(f"    error: {case['error']}")
        else:
            lines.append("  * none")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    api_key = getpass("Gemini API Key: ")
    client = genai.Client(api_key=api_key)

    model = "gemini-2.5-flash"
    temperature = 0.2
    max_output_tokens = 500

    messages = load_messages(MESSAGES_PATH)
    expected_outputs = load_expected_outputs(DATASET_PATH)

    if len(messages) != len(expected_outputs):
        raise ValueError(
            f"Message count and expected output count do not match: {len(messages)} vs {len(expected_outputs)}"
        )

    print(f"=== START {VERSION} ===")
    print(f"model: {model}")
    print(f"messages: {len(messages)}")
    print(f"interval: {REQUEST_INTERVAL_SECONDS}s")
    print(f"max_rate_limit_retries: {MAX_RATE_LIMIT_RETRIES}")
    print(f"default_rate_limit_wait_seconds: {DEFAULT_RATE_LIMIT_WAIT_SECONDS}s")

    summary_v1 = run_prompt_set(
        client=client,
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        system_prompt=PROMPT_V1,
        prompt_name="v1",
        messages=messages,
        expected_outputs=expected_outputs,
        output_path=OUTPUT_V1_PATH,
    )

    print(f"=== pause {PROMPT_SET_PAUSE_SECONDS}s before v2 ===")
    time.sleep(PROMPT_SET_PAUSE_SECONDS)

    summary_v2 = run_prompt_set(
        client=client,
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        system_prompt=PROMPT_V2,
        prompt_name="v2",
        messages=messages,
        expected_outputs=expected_outputs,
        output_path=OUTPUT_V2_PATH,
    )

    write_report(summary_v1, summary_v2, REPORT_PATH)

    print("=== DONE ===")
    print(f"messages file: {MESSAGES_PATH}")
    print(f"dataset file: {DATASET_PATH}")
    print(f"v1 output: {OUTPUT_V1_PATH}")
    print(f"v2 output: {OUTPUT_V2_PATH}")
    print(f"report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
