from services.gemini_service import GeminiService
import json
import os
from datetime import datetime

def main():
    service = GeminiService()

    # JSON 파일 경로 (현재 파일 기준 상대 경로)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "json", "customer.json")

    # customer.json에서 고객 문의 리스트 로드
    with open(json_path, "r", encoding="utf-8") as f:
        customers = json.load(f)

    # 결과 저장용 디렉터리 (날짜-현재시간 기준)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    result_dir = os.path.join(base_dir, "json", "result", run_id)
    os.makedirs(result_dir, exist_ok=True)

    # 모델 설정 저장
    model_config_path = os.path.join(result_dir, "model-config.json")
    with open(model_config_path, "w", encoding="utf-8") as f:
        json.dump(service.get_config(), f, ensure_ascii=False, indent=2)

    # 분석 결과를 담을 리스트
    analysis_results = []
    usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "elapsed_ms": 0.0,
    }
    requests_with_usage = 0

    print("🚀 고객 문의 분석 에이전트 가동...\n")

    for customer in customers:
        text = customer["customer_message"]
        print(f"📩 고객 문의 ({customer['id']}): {text}")

        # 분석 실행
        result, response_metadata = service.analyze_inquiry_with_usage(text)

        # 결과 출력 (Pydantic 객체이므로 점(.)으로 접근 가능)
        print(f"📊 분석 결과:")
        print(f"  - 의도(Intent): {result.intent}")
        print(f"  - 긴급도(Urgency): {result.urgency}")
        print(f"  - 담당부서(Route): {result.route_to}")
        print(f"  - 추가확인필요: {result.needs_clarification}")
        print(f"  - 입력 토큰: {response_metadata['prompt_tokens']}")
        print(f"  - 출력 토큰: {response_metadata['completion_tokens']}")
        print(f"  - 총 토큰: {response_metadata['total_tokens']}")
        print(f"  - 응답 시간(ms): {response_metadata['elapsed_ms']}")
        print("-" * 50)

        usage_fields = (
            response_metadata["prompt_tokens"],
            response_metadata["completion_tokens"],
            response_metadata["total_tokens"],
        )
        if any(value is not None for value in usage_fields):
            requests_with_usage += 1
            usage_totals["prompt_tokens"] += response_metadata["prompt_tokens"] or 0
            usage_totals["completion_tokens"] += response_metadata["completion_tokens"] or 0
            usage_totals["total_tokens"] += response_metadata["total_tokens"] or 0
        usage_totals["elapsed_ms"] += response_metadata["elapsed_ms"] or 0

        # 파일 저장용 결과 구조
        analysis_results.append(
            {
                "id": customer["id"],
                "customer_message": text,
                "analysis": result.model_dump(),
                "response_metadata": response_metadata,
            }
        )

    # 모든 문의에 대한 분석 결과 저장
    analysis_path = os.path.join(result_dir, "analysis-results.json")
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis_results, f, ensure_ascii=False, indent=2)

    usage_summary = {
        "model": service.model_name,
        "request_count": len(customers),
        "requests_with_usage": requests_with_usage,
        "requests_without_usage": len(customers) - requests_with_usage,
        "totals": usage_totals,
        "averages_per_request": {
            "prompt_tokens": round(usage_totals["prompt_tokens"] / requests_with_usage, 2) if requests_with_usage else 0,
            "completion_tokens": round(usage_totals["completion_tokens"] / requests_with_usage, 2) if requests_with_usage else 0,
            "total_tokens": round(usage_totals["total_tokens"] / requests_with_usage, 2) if requests_with_usage else 0,
            "elapsed_ms": round(usage_totals["elapsed_ms"] / len(customers), 2) if customers else 0,
        },
    }

    usage_summary_path = os.path.join(result_dir, "usage-summary.json")
    with open(usage_summary_path, "w", encoding="utf-8") as f:
        json.dump(usage_summary, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()