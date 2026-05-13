#!/usr/bin/env python3
"""
llm_config_generate.py

rag_pipeline.py의 runtime LLM 선택 흐름을 config 생성용으로 분리한 스크립트.

흐름
1. Provider 선택
2. API Key 입력 또는 환경변수에서 로드
3. 모델 목록 조회
4. 모델 번호 선택 또는 기본값 선택
5. config/llm_config.json 저장

실행
    py .\llm_config_generate.py

목록 확인
    py .\llm_config_generate.py --list

Active profile 변경
    py .\llm_config_generate.py --set-active PROFILE_NAME
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import requests
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "llm_config.json"

PROVIDER_NAME = ""
MODEL_NAME = ""
API_KEY = ""
BASE_URL = ""


OPENAI_DEFAULT_MODEL = "gpt-4.1-mini"
GEMINI_DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"


def ask_value(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def ask_secret(prompt: str) -> str:
    return getpass.getpass(f"{prompt}: ").strip()


def choose_provider() -> str:
    while True:
        print("사용할 LLM 제공자를 선택하세요.")
        print("1. OpenAI")
        print("2. Gemini")
        choice = input("번호 입력 [1/2]: ").strip()

        if choice == "1":
            return "openai"
        if choice == "2":
            return "gemini"

        print("잘못된 입력입니다. 1 또는 2를 입력하세요.")
        print()


def list_openai_models(api_key: str, base_url: str = "") -> List[str]:
    if base_url:
        temp_client = OpenAI(api_key=api_key, base_url=base_url)
    else:
        temp_client = OpenAI(api_key=api_key)

    models = temp_client.models.list()
    model_ids = sorted([m.id for m in models.data])
    return sorted(set(model_ids))


def list_gemini_models(api_key: str) -> List[str]:
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    resp = requests.get(url, params={"key": api_key}, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    models = data.get("models", [])

    model_names: List[str] = []
    for model in models:
        name = model.get("name", "")
        if name.startswith("models/"):
            name = name.split("/", 1)[1]
        if name:
            model_names.append(name)

    return sorted(set(model_names))


def choose_model_from_list(model_names: List[str], title: str, default_model: str = "") -> str:
    if not model_names:
        raise ValueError(f"{title} 목록이 비어 있습니다.")

    print()
    print(f"=== {title} 목록 ===")

    default_idx = None
    for idx, name in enumerate(model_names, start=1):
        marker = ""
        if default_model and name == default_model:
            marker = "  <= default"
            default_idx = idx
        print(f"{idx}. {name}{marker}")

    if default_idx is None and default_model:
        print(f"0. 기본값 직접 사용: {default_model}")

    while True:
        if default_idx is not None:
            choice = input(f"{title} 모델 번호 선택 [default: {default_idx}]: ").strip()
        elif default_model:
            choice = input(f"{title} 모델 번호 선택 [0=default: {default_model}]: ").strip()
        else:
            choice = input(f"{title} 모델 번호 선택 [1-{len(model_names)}]: ").strip()

        if choice == "":
            if default_idx is not None:
                return model_names[default_idx - 1]
            if default_model:
                return default_model
            print("기본값이 없습니다. 번호를 입력하세요.")
            continue

        if not choice.isdigit():
            print("숫자를 입력하세요.")
            continue

        idx = int(choice)

        if idx == 0 and default_model:
            return default_model

        if 1 <= idx <= len(model_names):
            return model_names[idx - 1]

        print("범위를 벗어났습니다.")


def resolve_runtime_config(default_model: str = "") -> None:
    """
    rag_pipeline.py의 provider/API key/model 선택 흐름을 config 생성용으로 사용한다.
    """
    global PROVIDER_NAME, MODEL_NAME, API_KEY, BASE_URL

    PROVIDER_NAME = choose_provider()

    if PROVIDER_NAME == "openai":
        API_KEY = os.getenv("OPENAI_API_KEY", "").strip() or ask_secret("OPENAI_API_KEY 입력")
        BASE_URL = ask_value("OPENAI_BASE_URL 입력 (없으면 엔터)", "")

        use_list = ask_value("OpenAI 모델 목록을 불러와서 선택할까요? (y/n)", "y").lower()
        if use_list == "y":
            try:
                models = list_openai_models(API_KEY, BASE_URL)
                MODEL_NAME = choose_model_from_list(
                    models,
                    "OpenAI",
                    default_model or OPENAI_DEFAULT_MODEL,
                )
            except Exception as e:
                print(f"[WARN] OpenAI 모델 목록 조회 실패: {e}")
                MODEL_NAME = ask_value(
                    "OpenAI MODEL_NAME 직접 입력",
                    default_model or OPENAI_DEFAULT_MODEL,
                )
        else:
            MODEL_NAME = ask_value(
                "OpenAI MODEL_NAME 직접 입력",
                default_model or OPENAI_DEFAULT_MODEL,
            )

    elif PROVIDER_NAME == "gemini":
        API_KEY = os.getenv("GEMINI_API_KEY", "").strip() or ask_secret("GEMINI_API_KEY 입력")
        BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

        use_list = ask_value("Gemini 모델 목록을 불러와서 선택할까요? (y/n)", "y").lower()
        if use_list == "y":
            try:
                models = list_gemini_models(API_KEY)
                MODEL_NAME = choose_model_from_list(
                    models,
                    "Gemini",
                    default_model or GEMINI_DEFAULT_MODEL,
                )
            except Exception as e:
                print(f"[WARN] Gemini 모델 목록 조회 실패: {e}")
                MODEL_NAME = ask_value(
                    "Gemini MODEL_NAME 직접 입력",
                    default_model or GEMINI_DEFAULT_MODEL,
                )
        else:
            MODEL_NAME = ask_value(
                "Gemini MODEL_NAME 직접 입력",
                default_model or GEMINI_DEFAULT_MODEL,
            )


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        return {
            "active_profile": "",
            "profiles": {},
        }

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("config JSON 최상위는 object여야 합니다.")

    data.setdefault("active_profile", "")
    data.setdefault("profiles", {})
    return data


def save_config(config_path: Path, config: Dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def slugify(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "_", text.strip())
    value = value.replace(".", "_").replace("-", "_")
    value = re.sub(r"_+", "_", value)
    return value.strip("_").lower() or "model"


def default_profile_name(provider: str, model: str) -> str:
    return f"{provider}_{slugify(model)}"


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def build_profile() -> Dict[str, Any]:
    if PROVIDER_NAME == "openai":
        api_key_env = "OPENAI_API_KEY"
        api_style = "openai_chat_completions"
    elif PROVIDER_NAME == "gemini":
        api_key_env = "GEMINI_API_KEY"
        api_style = "openai_chat_completions"
    else:
        api_key_env = ""
        api_style = "openai_chat_completions"

    return {
        "provider": PROVIDER_NAME,
        "model": MODEL_NAME,
        "base_url": BASE_URL,
        "api_key": API_KEY,
        "api_key_env": api_key_env,
        "api_style": api_style,
        "temperature": 0.0,
        "max_tokens": 800,
        "timeout_sec": 60,
        "max_retries": 2,
    }


def print_profiles(config: Dict[str, Any], reveal_key: bool = False) -> None:
    profiles = config.get("profiles", {})
    active = config.get("active_profile", "")

    if not profiles:
        print("[INFO] 저장된 profile이 없습니다.")
        return

    print(f"active_profile: {active}")
    for name, profile in profiles.items():
        shown = dict(profile)
        if not reveal_key:
            shown["api_key"] = mask_secret(str(shown.get("api_key", "")))
        marker = "*" if name == active else "-"
        print()
        print(f"{marker} {name}")
        print(json.dumps(shown, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH), help="config 파일 경로")
    parser.add_argument("--default_model", type=str, default="", help="목록 조회 실패 시 기본 모델명")
    parser.add_argument("--profile", type=str, default="", help="저장할 profile 이름")
    parser.add_argument("--list", action="store_true", help="저장된 profile 목록 출력")
    parser.add_argument("--reveal-key", action="store_true", help="--list 시 API Key 원문 출력")
    parser.add_argument("--set-active", type=str, default="", help="active_profile 변경")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)

    if args.list:
        print_profiles(config, reveal_key=args.reveal_key)
        return

    if args.set_active:
        if args.set_active not in config.get("profiles", {}):
            raise ValueError(f"존재하지 않는 profile입니다: {args.set_active}")
        config["active_profile"] = args.set_active
        save_config(config_path, config)
        print(f"[OK] active_profile 변경 완료: {args.set_active}")
        return

    resolve_runtime_config(default_model=args.default_model)

    print()
    print("=== Runtime Config ===")
    print(f"PROVIDER: {PROVIDER_NAME}")
    print(f"MODEL   : {MODEL_NAME}")
    print(f"BASE_URL: {BASE_URL or '(default)'}")
    print(f"API_KEY : {mask_secret(API_KEY)}")

    profile_name = args.profile or ask_value(
        "저장할 profile 이름",
        default_profile_name(PROVIDER_NAME, MODEL_NAME),
    )

    profile = build_profile()
    config.setdefault("profiles", {})[profile_name] = profile
    config["active_profile"] = profile_name

    save_config(config_path, config)

    shown = dict(profile)
    shown["api_key"] = mask_secret(str(shown.get("api_key", "")))

    print()
    print("[OK] LLM config 저장 완료")
    print(f"path   : {config_path}")
    print(f"profile: {profile_name}")
    print(json.dumps(shown, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
