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

    print("🚀 고객 문의 분석 에이전트 가동...\n")

    for customer in customers:
        text = customer["customer_message"]
        print(f"📩 고객 문의 ({customer['id']}): {text}")

        # 분석 실행
        result = service.analyze_inquiry(text)

        # 결과 출력 (Pydantic 객체이므로 점(.)으로 접근 가능)
        print(f"📊 분석 결과:")
        print(f"  - 의도(Intent): {result.intent}")
        print(f"  - 긴급도(Urgency): {result.urgency}")
        print(f"  - 담당부서(Route): {result.route_to}")
        print(f"  - 추가확인필요: {result.needs_clarification}")
        print("-" * 50)

        # 파일 저장용 결과 구조
        analysis_results.append(
            {
                "id": customer["id"],
                "customer_message": text,
                "analysis": result.model_dump(),
            }
        )

    # 모든 문의에 대한 분석 결과 저장
    analysis_path = os.path.join(result_dir, "analysis-results.json")
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()