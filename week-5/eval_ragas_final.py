from __future__ import annotations

import getpass
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests

from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    AnswerCorrectness,
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    ResponseRelevancy,
)

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from openai import OpenAI
import anthropic

from rag_pipeline_week5 import (
    INDEX_DIR,
    load_vectorstore,
    resolve_runtime_config,
    run_rag,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_PATH = BASE_DIR / "data" / "golden_dataset_v2.jsonl"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs_ragas"


# =============================================================================
# 입력 유틸
# =============================================================================
def ask_value(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def ask_int(prompt: str, default: int) -> int:
    while True:
        raw = ask_value(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            print("정수를 입력하세요.")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    default_str = "y" if default else "n"
    while True:
        value = ask_value(f"{prompt} (y/n)", default_str).lower()
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("y 또는 n 을 입력하세요.")


def ask_secret_from_env(env_name: str, prompt: str) -> str:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        use_env = ask_yes_no(f"{env_name} 환경변수를 사용하시겠습니까?", True)
        if use_env:
            os.environ[env_name] = env_value
            return env_value
    value = getpass.getpass(f"{prompt}: ").strip()
    if value:
        os.environ[env_name] = value
    return value


def choose_from_menu(title: str, options: List[str], default_index: int = 0) -> str:
    print(f"\n=== {title} ===")
    for idx, option in enumerate(options, start=1):
        mark = " (default)" if idx - 1 == default_index else ""
        print(f"{idx}. {option}{mark}")

    while True:
        raw = ask_value("번호 입력", str(default_index + 1))
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print("유효한 번호를 입력하세요.")


def choose_model_from_list(model_names: List[str], title: str, default_name: str = "") -> str:
    if not model_names:
        raise ValueError(f"{title} 모델 목록이 비어 있습니다.")

    default_index = 0
    for i, name in enumerate(model_names):
        if default_name and name == default_name:
            default_index = i
            break

    print(f"\n=== {title} 모델 목록 ===")
    for idx, name in enumerate(model_names, start=1):
        mark = " (default)" if idx - 1 == default_index else ""
        print(f"{idx}. {name}{mark}")

    while True:
        raw = ask_value(f"{title} 모델 번호 선택", str(default_index + 1))
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(model_names):
                return model_names[idx - 1]
        print("유효한 번호를 입력하세요.")


# =============================================================================
# 파일/데이터 유틸
# =============================================================================
def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"데이터셋 파일을 찾을 수 없습니다: {path}")

    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSONL 파싱 실패: line={line_no}, error={e}") from e
            if not isinstance(obj, dict):
                raise ValueError(f"JSONL line {line_no} 는 object 형태여야 합니다.")
            rows.append(obj)
    return rows


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def ensure_required_fields(rows: List[Dict[str, Any]]) -> None:
    required = {"question", "ground_truth", "ground_truth_contexts"}
    for idx, row in enumerate(rows, start=1):
        missing = [k for k in required if k not in row]
        if missing:
            raise ValueError(f"dataset row {idx} 에 필수 필드가 없습니다: {missing}")
        if not isinstance(row["ground_truth_contexts"], list):
            raise ValueError(f"dataset row {idx} 의 ground_truth_contexts 는 list 여야 합니다.")


# =============================================================================
# 모델 목록 조회 / 검증
# =============================================================================
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


def validate_openai_chat_call(api_key: str, model_name: str, base_url: str = "") -> None:
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    client.chat.completions.create(
        model=model_name,
        temperature=0.0,
        messages=[
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": "짧게 테스트 성공이라고 답하세요."},
        ],
        max_tokens=20,
    )


def validate_anthropic_call(api_key: str, model_name: str) -> None:
    client = anthropic.Anthropic(api_key=api_key)
    client.messages.create(
        model=model_name,
        max_tokens=32,
        temperature=0.0,
        messages=[{"role": "user", "content": "짧게 테스트 성공이라고 답하세요."}],
    )


def validate_gemini_call(api_key: str, model_name: str) -> None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {"contents": [{"parts": [{"text": "짧게 테스트 성공이라고 답하세요."}]}]}
    resp = requests.post(url, params={"key": api_key}, json=payload, timeout=60)
    resp.raise_for_status()


def validate_openai_embedding_call(api_key: str, model_name: str) -> None:
    client = OpenAI(api_key=api_key)
    client.embeddings.create(model=model_name, input="embedding test")


def validate_cohere_api_key(api_key: str) -> None:
    resp = requests.post(
        "https://api.cohere.com/v1/check-api-key",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Cohere API key check failed: status={resp.status_code}, body={resp.text}")


# =============================================================================
# 모델 선택/검증
# =============================================================================
def configure_generation() -> Tuple[str, str, str]:
    provider = choose_from_menu("생성 provider 선택", ["openai", "gemini"], 1)
    default_model = "gemini-3.1-flash-lite-preview" if provider == "gemini" else "gpt-4.1-mini"
    base_url = ""

    while True:
        try:
            if provider == "openai":
                api_key = ask_secret_from_env("OPENAI_API_KEY", "OPENAI_API_KEY 입력")
                base_url = ask_value("OPENAI_BASE_URL 입력 (없으면 엔터)", "")
                use_list = ask_yes_no("OpenAI 생성 모델 목록을 불러오겠습니까?", True)

                if use_list:
                    models = list_openai_models(api_key, base_url)
                    model_name = choose_model_from_list(models, "OpenAI Generation", default_model)
                else:
                    model_name = ask_value("OpenAI 생성 모델명 입력", default_model)

                print(f"[INFO] OpenAI 생성 모델 검증 중: {model_name}")
                validate_openai_chat_call(api_key, model_name, base_url)
                print("[SUCCESS] OpenAI 생성 모델 호출 확인 완료")
                return provider, model_name, base_url

            if provider == "gemini":
                api_key = ask_secret_from_env("GEMINI_API_KEY", "GEMINI_API_KEY 입력")
                use_list = ask_yes_no("Gemini 생성 모델 목록을 불러오겠습니까?", True)

                if use_list:
                    models = list_gemini_models(api_key)
                    model_name = choose_model_from_list(models, "Gemini Generation", default_model)
                else:
                    model_name = ask_value("Gemini 생성 모델명 입력", default_model)

                print(f"[INFO] Gemini 생성 모델 검증 중: {model_name}")
                validate_gemini_call(api_key, model_name)
                print("[SUCCESS] Gemini 생성 모델 호출 확인 완료")
                return provider, model_name, ""

            raise ValueError(f"지원하지 않는 생성 provider 입니다: {provider}")
        except Exception as e:
            print(f"[FAIL] 생성 모델 검증 실패: {e}")
            retry = ask_yes_no("생성 모델을 다시 선택할까요?", True)
            if not retry:
                raise


def configure_evaluator() -> Tuple[str, str]:
    provider = choose_from_menu("평가 provider 선택", ["openai", "anthropic"], 1)
    default_model = "claude-sonnet-4-6" if provider == "anthropic" else "gpt-4.1-mini"

    while True:
        try:
            if provider == "openai":
                api_key = ask_secret_from_env("OPENAI_API_KEY", "OPENAI_API_KEY 입력")
                use_list = ask_yes_no("OpenAI 평가 모델 목록을 불러오겠습니까?", True)

                if use_list:
                    models = list_openai_models(api_key, "")
                    model_name = choose_model_from_list(models, "OpenAI Evaluator", default_model)
                else:
                    model_name = ask_value("OpenAI 평가 모델명 입력", default_model)

                print(f"[INFO] OpenAI 평가 모델 검증 중: {model_name}")
                validate_openai_chat_call(api_key, model_name, "")
                print("[SUCCESS] OpenAI 평가 모델 호출 확인 완료")
                return provider, model_name

            if provider == "anthropic":
                api_key = ask_secret_from_env("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY 입력")
                use_list = ask_yes_no("Anthropic 평가 모델 목록을 불러오겠습니까?", True)

                if use_list:
                    models = list_anthropic_models(api_key)
                    model_name = choose_model_from_list(models, "Anthropic Evaluator", default_model)
                else:
                    model_name = ask_value("Anthropic 평가 모델명 입력", default_model)

                print(f"[INFO] Anthropic 평가 모델 검증 중: {model_name}")
                validate_anthropic_call(api_key, model_name)
                print("[SUCCESS] Anthropic 평가 모델 호출 확인 완료")
                return provider, model_name

            raise ValueError(f"지원하지 않는 evaluator provider 입니다: {provider}")
        except Exception as e:
            print(f"[FAIL] 평가 모델 검증 실패: {e}")
            retry = ask_yes_no("평가 모델을 다시 선택할까요?", True)
            if not retry:
                raise


def configure_embedding() -> Tuple[str, str]:
    provider = choose_from_menu("임베딩 provider 선택", ["openai", "huggingface"], 1)
    default_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" if provider == "huggingface" else "text-embedding-3-small"

    while True:
        try:
            if provider == "openai":
                api_key = ask_secret_from_env("OPENAI_API_KEY", "OPENAI_API_KEY 입력")
                use_list = ask_yes_no("OpenAI 임베딩 모델 목록을 불러오겠습니까?", True)

                if use_list:
                    models = list_openai_models(api_key, "")
                    embedding_candidates = [m for m in models if "embedding" in m]
                    if not embedding_candidates:
                        embedding_candidates = models
                    model_name = choose_model_from_list(embedding_candidates, "OpenAI Embedding", default_model)
                else:
                    model_name = ask_value("OpenAI 임베딩 모델명 입력", default_model)

                print(f"[INFO] OpenAI 임베딩 모델 검증 중: {model_name}")
                validate_openai_embedding_call(api_key, model_name)
                print("[SUCCESS] OpenAI 임베딩 모델 호출 확인 완료")
                return provider, model_name

            model_name = ask_value("HuggingFace 임베딩 모델명 입력", default_model)
            print(f"[INFO] HuggingFace 임베딩 모델 사용: {model_name}")
            return "huggingface", model_name
        except Exception as e:
            print(f"[FAIL] 임베딩 모델 검증 실패: {e}")
            retry = ask_yes_no("임베딩 모델을 다시 선택할까요?", True)
            if not retry:
                raise


def maybe_validate_cohere(search_mode: str) -> None:
    if search_mode != "hybrid_rerank":
        return

    print("\n=== Cohere rerank 키 검증 ===")
    while True:
        try:
            api_key = ask_secret_from_env("COHERE_API_KEY", "COHERE_API_KEY 입력")
            print("[INFO] Cohere API key 검증 중...")
            validate_cohere_api_key(api_key)
            print("[SUCCESS] Cohere API key 확인 완료")
            return
        except Exception as e:
            print(f"[FAIL] Cohere 검증 실패: {e}")
            retry = ask_yes_no("Cohere 키를 다시 입력할까요?", True)
            if not retry:
                raise


# =============================================================================
# Ragas evaluator / embedding 래퍼
# =============================================================================
def build_evaluator_llm(provider: str, model_name: str, temperature: float = 0.0):
    provider = provider.strip().lower()
    if provider == "openai":
        llm = ChatOpenAI(model=model_name, temperature=temperature)
    elif provider == "anthropic":
        llm = ChatAnthropic(model=model_name, temperature=temperature)
    else:
        raise ValueError(f"지원하지 않는 evaluator provider 입니다: {provider}")
    return LangchainLLMWrapper(llm)


def build_evaluator_embeddings(provider: str, model_name: str):
    provider = provider.strip().lower()
    if provider == "openai":
        emb = OpenAIEmbeddings(model=model_name)
    elif provider in {"huggingface", "hf"}:
        emb = HuggingFaceEmbeddings(model_name=model_name)
    else:
        raise ValueError(f"지원하지 않는 embedding provider 입니다: {provider}")
    return LangchainEmbeddingsWrapper(emb)


def build_metrics(evaluator_llm: Any, evaluator_embeddings: Any) -> List[Any]:
    metrics = [
        LLMContextRecall(llm=evaluator_llm),
        LLMContextPrecisionWithReference(llm=evaluator_llm),
        Faithfulness(llm=evaluator_llm),
        ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
        AnswerCorrectness(llm=evaluator_llm, embeddings=evaluator_embeddings),
    ]
    return metrics


# =============================================================================
# 평가 실행 로직
# =============================================================================
def sanitize_score(value: Any) -> Any:
    try:
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    except Exception:
        return value


def build_sample_and_trace(
    row: Dict[str, Any],
    rag_result: Dict[str, Any],
    pipeline_name: str,
) -> Tuple[SingleTurnSample, Dict[str, Any]]:
    sample = SingleTurnSample(
        user_input=row["question"],
        response=rag_result["answer"],
        retrieved_contexts=rag_result["retrieved_contexts"],
        reference=row["ground_truth"],
        reference_contexts=row["ground_truth_contexts"],
    )

    trace = {
        "id": row.get("id"),
        "pair_id": row.get("pair_id"),
        "difficulty": row.get("difficulty", ""),
        "source_year": row.get("source_year", ""),
        "category": row.get("category", ""),
        "pipeline": pipeline_name,
        "question": row["question"],
        "ground_truth": row["ground_truth"],
        "ground_truth_contexts": row["ground_truth_contexts"],
        "response": rag_result["answer"],
        "retrieved_contexts": rag_result["retrieved_contexts"],
        "retrieved_docs": rag_result["retrieved_docs_serialized"],
        "search_mode": rag_result["search_mode"],
        "top_k": rag_result["top_k"],
        "use_year_filter": rag_result["use_year_filter"],
    }
    return sample, trace


def run_pipeline_dataset(
    dataset_rows: List[Dict[str, Any]],
    vectorstore: Any,
    pipeline_name: str,
    search_mode: str,
    top_k: int,
    use_year_filter: bool,
    limit: int = 0,
) -> Tuple[EvaluationDataset, List[Dict[str, Any]]]:
    samples: List[SingleTurnSample] = []
    traces: List[Dict[str, Any]] = []

    target_rows = dataset_rows[:limit] if limit and limit > 0 else dataset_rows
    total = len(target_rows)

    for idx, row in enumerate(target_rows, start=1):
        print(
            f"[{pipeline_name}] {idx}/{total} | id={row.get('id', f'q{idx:02d}')} | "
            f"year={row.get('source_year', '')} | question={row['question']}"
        )
        rag_result = run_rag(
            vectorstore=vectorstore,
            question=row["question"],
            search_mode=search_mode,
            top_k=top_k,
            use_year_filter=use_year_filter,
            generate=True,
            debug=False,
        )
        sample, trace = build_sample_and_trace(row, rag_result, pipeline_name)
        samples.append(sample)
        traces.append(trace)

    return EvaluationDataset(samples=samples), traces


def evaluate_pipeline(
    dataset: EvaluationDataset,
    traces: List[Dict[str, Any]],
    metrics: List[Any],
    evaluator_llm: Any,
    evaluator_embeddings: Any,
    output_dir: Path,
    pipeline_name: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        raise_exceptions=False,
        show_progress=True,
    )

    scores_df = result.to_pandas()
    meta_df = pd.DataFrame(traces)
    merged_df = pd.concat([meta_df.reset_index(drop=True), scores_df.reset_index(drop=True)], axis=1)

    csv_path = output_dir / f"{pipeline_name}_ragas_scores.csv"
    jsonl_path = output_dir / f"{pipeline_name}_ragas_scores.jsonl"
    merged_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    save_jsonl(jsonl_path, merged_df.to_dict(orient="records"))

    metric_columns = [
        col for col in scores_df.columns
        if col in {
            "context_recall",
            "llm_context_precision_with_reference",
            "faithfulness",
            "response_relevancy",
            "answer_correctness",
        }
    ]

    means = {
        col: sanitize_score(scores_df[col].mean())
        for col in metric_columns
        if col in scores_df.columns
    }

    summary = {
        "pipeline": pipeline_name,
        "total": len(merged_df),
        "metric_means": means,
        "csv_path": str(csv_path),
        "jsonl_path": str(jsonl_path),
    }
    save_json(output_dir / f"{pipeline_name}_summary.json", summary)
    return merged_df, summary


def build_comparison_summary(basic_summary: Dict[str, Any], advanced_summary: Dict[str, Any]) -> Dict[str, Any]:
    keys = sorted(set(basic_summary.get("metric_means", {}).keys()) | set(advanced_summary.get("metric_means", {}).keys()))
    comparison_rows = []
    for key in keys:
        b = basic_summary.get("metric_means", {}).get(key)
        a = advanced_summary.get("metric_means", {}).get(key)
        delta = None
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            delta = round(a - b, 6)
        comparison_rows.append({
            "metric": key,
            "basic": b,
            "advanced": a,
            "delta": delta,
        })

    return {
        "basic": basic_summary,
        "advanced": advanced_summary,
        "comparison": comparison_rows,
    }


# =============================================================================
# 실행 설정 입력
# =============================================================================
def gather_runtime_config() -> Dict[str, Any]:
    print("\n=== 실행 설정 입력 ===")
    dataset_path = ask_value("데이터셋 경로", str(DEFAULT_DATASET_PATH))
    output_dir = ask_value("출력 폴더", str(DEFAULT_OUTPUT_DIR))
    basic_search_mode = choose_from_menu("Basic 검색 방식", ["vector", "hybrid", "hybrid_rerank"], 0)
    advanced_search_mode = choose_from_menu("Advanced 검색 방식", ["vector", "hybrid", "hybrid_rerank"], 1)
    top_k = ask_int("top_k", 4)
    use_year_filter = ask_yes_no("연도 필터를 사용할까요?", True)
    limit = ask_int("파일럿 문항 수 제한 (0이면 전체)", 0)
    validate_only = ask_yes_no("모델 검증만 하고 종료할까요?", False)

    return {
        "dataset_path": dataset_path,
        "output_dir": output_dir,
        "basic_search_mode": basic_search_mode,
        "advanced_search_mode": advanced_search_mode,
        "top_k": top_k,
        "use_year_filter": use_year_filter,
        "limit": limit,
        "validate_only": validate_only,
    }


def main() -> None:
    cfg = gather_runtime_config()

    dataset_path = Path(cfg["dataset_path"])
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nDATASET_PATH : {dataset_path}")
    print(f"INDEX_DIR    : {INDEX_DIR}")
    print(f"OUTPUT_DIR   : {output_dir}")
    print(f"BASIC MODE   : {cfg['basic_search_mode']}")
    print(f"ADV MODE     : {cfg['advanced_search_mode']}")
    print(f"TOP_K        : {cfg['top_k']}")
    print(f"YEAR FILTER  : {cfg['use_year_filter']}")
    print(f"LIMIT        : {cfg['limit'] or '(all)'}")

    print("\n=== 1) 생성 모델 선택/검증 ===")
    gen_provider, gen_model, gen_base_url = configure_generation()

    print("\n=== 2) 평가 모델 선택/검증 ===")
    evaluator_provider, evaluator_model = configure_evaluator()

    print("\n=== 3) 임베딩 모델 선택/검증 ===")
    embedding_provider, embedding_model = configure_embedding()

    print("\n=== 4) rerank 필요 시 Cohere 검증 ===")
    maybe_validate_cohere(cfg["advanced_search_mode"])

    print("\n=== 선택/검증 완료 ===")
    print(f"GENERATOR : {gen_provider} / {gen_model}")
    print(f"EVALUATOR : {evaluator_provider} / {evaluator_model}")
    print(f"EMBEDDING : {embedding_provider} / {embedding_model}")

    if cfg["validate_only"]:
        print("\nvalidate_only가 켜져 있어 여기서 종료합니다.")
        return

    dataset_rows = load_jsonl(dataset_path)
    ensure_required_fields(dataset_rows)
    print(f"Loaded dataset rows: {len(dataset_rows)}")

    resolve_runtime_config(
        provider=gen_provider,
        model_name=gen_model,
        base_url=gen_base_url,
        interactive=False,
    )
    vectorstore = load_vectorstore(INDEX_DIR)

    evaluator_llm = build_evaluator_llm(
        provider=evaluator_provider,
        model_name=evaluator_model,
    )
    evaluator_embeddings = build_evaluator_embeddings(
        provider=embedding_provider,
        model_name=embedding_model,
    )

    metrics = build_metrics(
        evaluator_llm=evaluator_llm,
        evaluator_embeddings=evaluator_embeddings,
    )

    basic_dataset, basic_traces = run_pipeline_dataset(
        dataset_rows=dataset_rows,
        vectorstore=vectorstore,
        pipeline_name="basic",
        search_mode=cfg["basic_search_mode"],
        top_k=cfg["top_k"],
        use_year_filter=cfg["use_year_filter"],
        limit=cfg["limit"],
    )
    save_jsonl(output_dir / "basic_rag_run_traces.jsonl", basic_traces)

    advanced_dataset, advanced_traces = run_pipeline_dataset(
        dataset_rows=dataset_rows,
        vectorstore=vectorstore,
        pipeline_name="advanced",
        search_mode=cfg["advanced_search_mode"],
        top_k=cfg["top_k"],
        use_year_filter=cfg["use_year_filter"],
        limit=cfg["limit"],
    )
    save_jsonl(output_dir / "advanced_rag_run_traces.jsonl", advanced_traces)

    _, basic_summary = evaluate_pipeline(
        dataset=basic_dataset,
        traces=basic_traces,
        metrics=metrics,
        evaluator_llm=evaluator_llm,
        evaluator_embeddings=evaluator_embeddings,
        output_dir=output_dir,
        pipeline_name="basic",
    )
    _, advanced_summary = evaluate_pipeline(
        dataset=advanced_dataset,
        traces=advanced_traces,
        metrics=metrics,
        evaluator_llm=evaluator_llm,
        evaluator_embeddings=evaluator_embeddings,
        output_dir=output_dir,
        pipeline_name="advanced",
    )

    comparison = build_comparison_summary(basic_summary, advanced_summary)
    save_json(output_dir / "comparison_summary.json", comparison)

    print("\n=== Basic Metric Means ===")
    for k, v in basic_summary["metric_means"].items():
        print(f"{k}: {v}")

    print("\n=== Advanced Metric Means ===")
    for k, v in advanced_summary["metric_means"].items():
        print(f"{k}: {v}")

    print("\n=== Delta (Advanced - Basic) ===")
    for row in comparison["comparison"]:
        print(f"{row['metric']}: {row['delta']}")

    print("\nSaved files:")
    print(output_dir / "basic_rag_run_traces.jsonl")
    print(output_dir / "advanced_rag_run_traces.jsonl")
    print(output_dir / "basic_ragas_scores.csv")
    print(output_dir / "advanced_ragas_scores.csv")
    print(output_dir / "comparison_summary.json")


if __name__ == "__main__":
    main()
