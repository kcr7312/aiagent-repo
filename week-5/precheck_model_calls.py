from __future__ import annotations

import getpass
import os
from typing import List

import requests
from openai import OpenAI
import anthropic


def ask_value(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def ask_secret_from_env(env_name: str, prompt: str) -> str:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        use_env = ask_value(f"{env_name} 환경변수를 사용하시겠습니까? (y/n)", "y").lower()
        if use_env == "y":
            return env_value
    return getpass.getpass(f"{prompt}: ").strip()


def choose_provider() -> str:
    while True:
        print("\n확인할 provider를 선택하세요.")
        print("1. OpenAI")
        print("2. Anthropic")
        print("3. Cohere")
        print("4. Gemini")
        print("5. 종료")
        choice = input("번호 입력 [1/2/3/4/5]: ").strip()

        if choice == "1":
            return "openai"
        if choice == "2":
            return "anthropic"
        if choice == "3":
            return "cohere"
        if choice == "4":
            return "gemini"
        if choice == "5":
            return "exit"

        print("잘못된 입력입니다. 1~5 중 하나를 입력하세요.")


def choose_model_from_list(model_names: List[str], title: str) -> str:
    if not model_names:
        raise ValueError(f"{title} 모델 목록이 비어 있습니다.")

    print(f"\n=== {title} 모델 목록 ===")
    for idx, name in enumerate(model_names, start=1):
        print(f"{idx}. {name}")

    while True:
        choice = input(f"{title} 모델 번호 선택 [1-{len(model_names)}]: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(model_names):
                return model_names[idx - 1]
        print("유효한 번호를 입력하세요.")


def list_openai_models(api_key: str, base_url: str = "") -> List[str]:
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    models = client.models.list()
    return sorted(set(m.id for m in models.data))


def list_anthropic_models(api_key: str) -> List[str]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    resp = requests.get("https://api.anthropic.com/v1/models", headers=headers, timeout=30)
    resp.raise_for_status()

    data = resp.json().get("data", [])
    model_ids: List[str] = []
    for item in data:
        model_id = item.get("id")
        if model_id:
            model_ids.append(model_id)

    return sorted(set(model_ids))


def print_anthropic_models_verbose(api_key: str) -> None:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    resp = requests.get("https://api.anthropic.com/v1/models", headers=headers, timeout=30)
    resp.raise_for_status()

    data = resp.json().get("data", [])
    print("\n=== Anthropic 모델 상세 목록 ===")
    for idx, item in enumerate(data, start=1):
        model_id = item.get("id", "")
        display_name = item.get("display_name", "")
        created_at = item.get("created_at", "")
        type_ = item.get("type", "")
        print(f"{idx}. id={model_id}")
        if display_name:
            print(f"   display_name={display_name}")
        if type_:
            print(f"   type={type_}")
        if created_at:
            print(f"   created_at={created_at}")


def list_gemini_models(api_key: str) -> List[str]:
    resp = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key},
        timeout=30,
    )
    resp.raise_for_status()

    models = resp.json().get("models", [])
    model_names: List[str] = []
    for model in models:
        name = model.get("name", "")
        if name.startswith("models/"):
            name = name.split("/", 1)[1]
        if name:
            model_names.append(name)

    return sorted(set(model_names))


def print_gemini_models_verbose(api_key: str) -> None:
    resp = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key},
        timeout=30,
    )
    resp.raise_for_status()

    models = resp.json().get("models", [])
    print("\n=== Gemini 모델 상세 목록 ===")
    for idx, model in enumerate(models, start=1):
        name = model.get("name", "")
        if name.startswith("models/"):
            name = name.split("/", 1)[1]
        display_name = model.get("displayName", "")
        description = model.get("description", "")
        print(f"{idx}. id={name}")
        if display_name:
            print(f"   display_name={display_name}")
        if description:
            print(f"   description={description[:120]}")


def check_openai() -> None:
    print("\n=== OpenAI 호출 점검 ===")
    api_key = ask_secret_from_env("OPENAI_API_KEY", "OPENAI_API_KEY 입력")
    base_url = ask_value("OPENAI_BASE_URL 입력 (없으면 엔터)", "")
    list_models = ask_value("모델 목록을 불러오겠습니까? (y/n)", "y").lower()

    model_name = ""
    try:
        if list_models == "y":
            models = list_openai_models(api_key, base_url)
            model_name = choose_model_from_list(models, "OpenAI")
        else:
            model_name = ask_value("모델명 직접 입력", "gpt-4.1-mini")
    except Exception as e:
        print(f"[WARN] 모델 목록 조회 실패: {e}")
        model_name = ask_value("모델명 직접 입력", "gpt-4.1-mini")

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    print(f"\n[INFO] 선택 모델: {model_name}")
    print("[INFO] 테스트 호출을 시작합니다...")

    try:
        resp = client.chat.completions.create(
            model=model_name,
            temperature=0.0,
            messages=[
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": "한 문장으로 'OpenAI 호출 테스트 성공'이라고 답하세요."},
            ],
            max_tokens=50,
        )
        content = resp.choices[0].message.content or ""
        print("\n[SUCCESS] OpenAI 호출 성공")
        print(f"모델: {model_name}")
        print(f"응답: {content}")
    except Exception as e:
        print("\n[FAIL] OpenAI 호출 실패")
        print(f"모델: {model_name}")
        print(f"에러: {e}")


def check_anthropic() -> None:
    print("\n=== Anthropic 호출 점검 ===")
    api_key = ask_secret_from_env("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY 입력")

    list_mode = ask_value("Anthropic 모델 목록을 불러오겠습니까? (y/n)", "y").lower()
    model_name = ""

    try:
        if list_mode == "y":
            verbose = ask_value("상세 정보도 같이 볼까요? (y/n)", "n").lower()
            if verbose == "y":
                print_anthropic_models_verbose(api_key)
            models = list_anthropic_models(api_key)
            model_name = choose_model_from_list(models, "Anthropic")
        else:
            model_name = ask_value("Anthropic 모델명 직접 입력", "")
            if not model_name:
                raise ValueError("모델명을 직접 입력해야 합니다.")
    except Exception as e:
        print(f"[WARN] Anthropic 모델 목록 조회 실패: {e}")
        model_name = ask_value("Anthropic 모델명 직접 입력", "")
        if not model_name:
            print("[FAIL] 모델명이 없어 Anthropic 테스트를 중단합니다.")
            return

    client = anthropic.Anthropic(api_key=api_key)

    print(f"\n[INFO] 선택 모델: {model_name}")
    print("[INFO] 테스트 호출을 시작합니다...")

    try:
        resp = client.messages.create(
            model=model_name,
            max_tokens=64,
            temperature=0.0,
            messages=[
                {"role": "user", "content": "한 문장으로 'Anthropic 호출 테스트 성공'이라고 답하세요."}
            ],
        )
        text_parts = []
        for block in resp.content:
            if getattr(block, "type", "") == "text":
                text_parts.append(block.text)
        content = "\n".join(text_parts).strip()

        print("\n[SUCCESS] Anthropic 호출 성공")
        print(f"모델: {model_name}")
        print(f"응답: {content}")
    except Exception as e:
        print("\n[FAIL] Anthropic 호출 실패")
        print(f"모델: {model_name}")
        print(f"에러: {e}")


def check_cohere() -> None:
    print("\n=== Cohere 호출 점검 ===")
    api_key = ask_secret_from_env("COHERE_API_KEY", "COHERE_API_KEY 입력")

    print("[INFO] API 키 유효성만 간단히 확인합니다...")

    try:
        resp = requests.post(
            "https://api.cohere.com/v1/check-api-key",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        print(f"HTTP 상태코드: {resp.status_code}")
        print(f"응답 본문: {resp.text}")
        if resp.ok:
            print("\n[SUCCESS] Cohere API 키 확인 성공")
        else:
            print("\n[FAIL] Cohere API 키 확인 실패")
    except Exception as e:
        print("\n[FAIL] Cohere 요청 실패")
        print(f"에러: {e}")


def check_gemini() -> None:
    print("\n=== Gemini 호출 점검 ===")
    api_key = ask_secret_from_env("GEMINI_API_KEY", "GEMINI_API_KEY 입력")

    list_mode = ask_value("Gemini 모델 목록을 불러오겠습니까? (y/n)", "y").lower()
    model_name = ""

    try:
        if list_mode == "y":
            verbose = ask_value("상세 정보도 같이 볼까요? (y/n)", "n").lower()
            if verbose == "y":
                print_gemini_models_verbose(api_key)
            models = list_gemini_models(api_key)
            model_name = choose_model_from_list(models, "Gemini")
        else:
            model_name = ask_value("Gemini 모델명 직접 입력", "gemini-2.5-flash")
    except Exception as e:
        print(f"[WARN] Gemini 모델 목록 조회 실패: {e}")
        model_name = ask_value("Gemini 모델명 직접 입력", "gemini-2.5-flash")

    print(f"\n[INFO] 선택 모델: {model_name}")
    print("[INFO] 테스트 호출을 시작합니다...")

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": "한 문장으로 'Gemini 호출 테스트 성공'이라고 답하세요."}
                    ]
                }
            ]
        }
        resp = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        content = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            texts = [part.get("text", "") for part in parts if "text" in part]
            content = "\n".join(t for t in texts if t).strip()

        print("\n[SUCCESS] Gemini 호출 성공")
        print(f"모델: {model_name}")
        print(f"응답: {content}")
    except Exception as e:
        print("\n[FAIL] Gemini 호출 실패")
        print(f"모델: {model_name}")
        print(f"에러: {e}")


def main() -> None:
    print("간단 모델 호출 점검 도구")
    print("목적: API 키/모델명/실제 호출 가능 여부만 빠르게 확인")

    while True:
        provider = choose_provider()

        if provider == "exit":
            print("종료합니다.")
            break
        if provider == "openai":
            check_openai()
        elif provider == "anthropic":
            check_anthropic()
        elif provider == "cohere":
            check_cohere()
        elif provider == "gemini":
            check_gemini()

        print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
