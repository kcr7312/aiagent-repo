import json
from pathlib import Path


def load_results(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def calc_metrics(results: list[dict]) -> dict:
    total = len(results)
    parse_success = sum(1 for r in results if r.get("parse_success", False))
    exact_match = sum(1 for r in results if r.get("exact_match", False))

    return {
        "total": total,
        "parse_success": parse_success,
        "parse_success_rate": (parse_success / total * 100) if total else 0.0,
        "exact_match": exact_match,
        "exact_match_rate": (exact_match / total * 100) if total else 0.0,
    }


def infer_failure_reason(case: dict) -> str:
    if not case.get("parse_success", False):
        err = (case.get("error") or "").lower()

        if "json" in err:
            return "JSON 형식 오류 또는 출력 잘림으로 파싱 실패"
        if "validation" in err:
            return "스키마 검증 실패"
        return f"파싱 예외 발생: {case.get('error')}"

    expected = case.get("expected_output") or {}
    predicted = case.get("predicted_output") or {}

    diffs = []
    for field in ["intent", "urgency", "needs_clarification", "route_to"]:
        if expected.get(field) != predicted.get(field):
            diffs.append(field)

    return f"{', '.join(diffs)} 필드 불일치"


def build_report(label: str, results: list[dict]) -> str:
    metrics = calc_metrics(results)

    report = []
    report.append(f"[{label}]")
    report.append(f"- 전체 건수: {metrics['total']}")
    report.append(
        f"- JSON 파싱 성공률: {metrics['parse_success']}/{metrics['total']} "
        f"({metrics['parse_success_rate']:.1f}%)"
    )
    report.append(
        f"- exact match 개수: {metrics['exact_match']}/{metrics['total']} "
        f"({metrics['exact_match_rate']:.1f}%)"
    )

    failures = [r for r in results if not r.get("exact_match", False)]
    report.append("- 대표 실패 3건:")

    if not failures:
        report.append("  모든 케이스 성공")
        report.append("  최적화: max_output_tokens 감소로 비용 절감 가능")
        return "\n".join(report)

    for i, case in enumerate(failures[:3], start=1):
        report.append(f"  {i}) {case['id']}")
        report.append(f"     message: {case['customer_message']}")
        report.append(f"     expected: {case['expected_output']}")
        report.append(f"     predicted: {case['predicted_output']}")
        if case.get("error"):
            report.append(f"     error: {case['error']}")
        report.append(f"     원인: {infer_failure_reason(case)}")

    return "\n".join(report)


def build_comparison(v1_results, v2_results) -> str:
    v1 = calc_metrics(v1_results)
    v2 = calc_metrics(v2_results)

    report = []
    report.append("\n[비교 요약]")
    report.append(
        f"- 파싱 성공률: v1 {v1['parse_success_rate']:.1f}% → v2 {v2['parse_success_rate']:.1f}%"
    )
    report.append(
        f"- exact match: v1 {v1['exact_match']} → v2 {v2['exact_match']}"
    )

    return "\n".join(report)


def main():
    v1_path = "results_v1.json"
    v2_path = "results_v2.json"

    v1_results = load_results(v1_path)
    v2_results = load_results(v2_path)

    report_v1 = build_report("v1", v1_results)
    report_v2 = build_report("v2", v2_results)
    report_cmp = build_comparison(v1_results, v2_results)

    full_report = "\n\n".join([report_v1, report_v2, report_cmp])

    # 콘솔 출력
    print(full_report)

    # txt 저장
    with open("report.txt", "w", encoding="utf-8") as f:
        f.write(full_report)

    print("\nreport.txt 저장 완료")


if __name__ == "__main__":
    main()