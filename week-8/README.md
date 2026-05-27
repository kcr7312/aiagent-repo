# 8주차 AI Agent Observability

## 프로젝트 링크

- Repository: https://github.com/kcr7312/aiagent-repo
- 7주차 제출 README: https://github.com/kcr7312/aiagent-repo/tree/main/week-7
- 8주차 작업 위치: https://github.com/kcr7312/aiagent-repo/tree/main/week-8

---

## 구현한 Observability

이번 주차에서는 7주차에 구현한 패킷 디코딩 workflow agent에 실행 추적 기능을 보강하였다.

본 프로젝트의 agent는 일반적인 자유 대화형 agent가 아니라, `strategy_precheck.py`가 생성한 `*.pending.json` 큐 파일을 기준으로 다음 action을 라우팅하는 **packet decoding workflow agent**이다.

따라서 최종 답변은 자연어 응답이 아니라 아래 항목으로 정의하였다.

- `file_status`
- `completion_status`
- `decision`
- `reason`
- `output strategy file`
- `llm_review_output`

### 사용한 방식

- JSONL 기반 event log
- run 단위 로그 파일
- 전체 누적 로그 파일

### Trace 저장 위치

```text
log/llm_agent_events.jsonl
log/llm_agent_run_<run_id>.jsonl
data/llm_reviews/*_llm_review.json
data/strategy/*_strategy.<pending|done|failed>.json
```

### 기록하는 항목

| 구분 | 기록 항목 |
|---|---|
| Request / Run | `run_id`, `ts`, `strategy_path`, `pending_count`, `route_counts` |
| Model | `llm_profile`, `llm_provider`, `llm_model`, `llm_api_style` |
| Agent Step | `agent_start`, `classify_pending`, `process_llm_review_start`, `llm_response_received`, `llm_decision`, `action_result`, `process_llm_review_done`, `agent_finish` |
| Tool | `recommended_tool`, `recommended_options`, `command`, `returncode`, `stdout_preview`, `stderr_preview` |
| Output | `decision`, `completion_status`, `file_status`, `required_next_action`, `next_tool` |
| Error | `process_file_error`, `error`, `stderr_preview`, API error message |
| Latency | `duration_ms`, `llm_duration_ms`, `action_duration_ms` |
| Safety | API key/token 원문 미저장, config path 및 provider/model 정보만 기록 |

---

## Agent 실행 흐름

### Agent 이름

```text
packet_decode_strategy_agent
```

### 주요 스크립트

| 스크립트 | 역할 |
|---|---|
| `strategy_precheck.py` | decoded 결과를 보고 `pending/done/failed` strategy 파일 생성 |
| `llm_agent.py` | pending strategy를 읽고 LLM review 및 tool routing 수행 |
| `noise_cleanup_tool.py` | base64-like failed candidate의 trailing noise / padding / invalid char 정리 |
| `retry_encoding.py` | `normalized_candidates`를 대상으로 재디코딩 수행 |
| `url_decode_tool.py` | URL/percent-encoded 후보 복원용 확장 tool |

### 종료 조건

| 종료 조건 | 설명 |
|---|---|
| `stop` | decoded candidate가 충분하고 추가 검증 대상 없음 |
| `stop_with_exclusion` | visible payload는 디코딩되었으나 TLS 등 제외 stream은 복호화 재료가 없어 종료 |
| `retry_same_tool` | 기존 decoding 계열을 더 tolerant하게 재시도해야 함 |
| `call_other_tool` | 다른 decoding family의 tool이 필요함 |
| `failed` | LLM API error, invalid JSON, tool failure 등으로 처리 실패 |

---

## 실행 방법

### 1. strategy 생성

```powershell
py .\strategy_precheck.py
```

### 2. dry run

```powershell
py .\llm_agent.py --dry-run
```

### 3. 일반 실행

```powershell
py .\llm_agent.py
```

### 4. 순차 tool 호출 실행

```powershell
py .\llm_agent.py --auto-continue --continue-delay-sec 1.0
```

`--auto-continue` 옵션은 preprocessing tool이 성공하고 `required_next_action == run_encoding_decode_tool`인 경우, 같은 run 안에서 일정 시간 대기 후 `retry_encoding.py`까지 즉시 호출하도록 하기 위해 추가하였다.

---

## 정상 케이스 Trace

### Trace 파일

```text
log/llm_agent_run_20260527_141502.jsonl
```

### 입력

```text
data/strategy/01_sample_packet_ldap-basic-auth-ev1_strategy.pending.json
```

해당 strategy는 decoded candidate가 존재하지만 failed artifact가 함께 남아 있어 LLM review 대상으로 분류되었다.

### 실행 요약

| Step | Type | Name | 주요 입력 | 결과 |
|---:|---|---|---|---|
| 1 | agent | `agent_start` | strategy dir, config path, model profile | run 시작 |
| 2 | router | `classify_pending` | `*.pending.json` | route = `llm_review` |
| 3 | agent | `process_llm_review_start` | strategy path | LLM review 시작 |
| 4 | model | `llm_response_received` | `llm_review_prompt` | LLM 응답 수신, `llm_duration_ms` 기록 |
| 5 | decision | `llm_decision` | decoded/failed/residue preview | `decision = retry_same_tool` |
| 6 | tool_call | `noise_cleanup_tool` | `recommended_options` | tool 실행 성공 |
| 7 | observation | `action_result` | noise cleanup result | normalized candidate 생성 |
| 8 | state_update | `process_llm_review_done` | action result | `pending` 유지, `next_tool = retry_encoding` |
| 9 | agent | `agent_finish` | 전체 결과 | processed_files = 3, duration 기록 |

### LLM 판단

```json
{
  "decision": "retry_same_tool",
  "completion_status": "decoded_with_failed_artifacts",
  "recommended_tool": "noise_cleanup_tool"
}
```

### Tool 실행 결과

```json
{
  "action": "retry_same_tool",
  "executed": true,
  "status": "tool_executed",
  "preprocess_tool": "noise_cleanup_tool",
  "next_tool": "retry_encoding"
}
```

### 최종 상태

```text
file_status = pending
required_next_action = run_encoding_decode_tool
next_tool = retry_encoding
```

### 해석

정상 케이스에서 agent는 failed candidate를 단순 artifact로 종료하지 않고, LLM decision에 따라 `noise_cleanup_tool`을 호출하였다. Tool 실행 결과는 strategy 파일에 병합되었고, 다음 단계로 `retry_encoding.py`가 지정되었다. 따라서 tool name, arguments, result, next action이 모두 trace에 남았다.

---

## 종료 판단 케이스 Trace

같은 run 안에서 나머지 케이스들은 `stop_with_exclusion`으로 종료되었다.

### 실행 요약

| Step | Type | Name | 주요 입력 | 결과 |
|---:|---|---|---|---|
| 1 | router | `classify_pending` | pending strategy | route = `llm_review` |
| 2 | model | `llm_response_received` | decoded/excluded stream preview | LLM 응답 수신 |
| 3 | decision | `llm_decision` | visible payload + excluded stream | `stop_with_exclusion` |
| 4 | state_update | `process_llm_review_done` | LLM decision | `.done.json` 전환 |

### 최종 상태

```text
decision = stop_with_exclusion
completion_status = partial_excluded
file_status = done
```

### 해석

visible HTTP payload는 이미 디코딩되었고, 남은 stream은 TLS encrypted stream으로 분류되었다. TLS payload decoding에는 session key, key log material, endpoint session material 등 별도의 복호화 재료가 필요하므로 agent는 추가 tool 호출 없이 `stop_with_exclusion`으로 종료하였다.

---

## 실패 또는 예외 케이스 Trace

### Trace 파일

```text
log/llm_agent_run_20260527_141308.jsonl
```

### 입력

```text
data/strategy/*.pending.json
```

### 실행 요약

| Step | Type | Name | 주요 입력 | 결과 |
|---:|---|---|---|---|
| 1 | agent | `agent_start` | config, strategy dir | run 시작 |
| 2 | router | `classify_pending` | pending strategy | route = `llm_review` |
| 3 | agent | `process_llm_review_start` | strategy path | LLM 호출 준비 |
| 4 | error | `process_file_error` | LLM request | model unavailable / API error |
| 5 | state_update | failed strategy 생성 | error message | `.failed.json` 전환 |
| 6 | agent | `agent_finish` | results summary | 실패 결과 요약 |

### 실패 처리

해당 run에서는 LLM API 요청 단계에서 모델 사용 불가 오류가 발생하였다. Agent는 예외를 그대로 무시하지 않고 `process_file_error` 이벤트를 기록했으며, 해당 strategy를 `.failed.json`으로 전환하였다.

### 실패 원인

```text
LLM model unavailable / API request failed
```

### 해석

실패 trace는 tool 실행 이전 단계에서 발생한 오류이지만, week-8 과제 관점에서는 예외 케이스로 의미가 있다. Agent가 LLM 호출 실패를 감지하고, error message와 failed output을 남겼기 때문이다. 이 trace는 향후 regression dataset 또는 config/model validation 개선 대상으로 활용할 수 있다.

---

## Trace 분석

### 예상한 흐름

```text
pending strategy
→ LLM review
→ decision 생성
→ 필요한 경우 tool 호출
→ action_result 기록
→ strategy 상태 갱신
→ agent_finish에서 run summary 기록
```

### 실제 흐름

정상 케이스에서는 예상대로 `llm_decision → action_result → process_llm_review_done` 순서로 진행되었다. `retry_same_tool` 결정 이후 `noise_cleanup_tool`이 호출되었고, `required_next_action = run_encoding_decode_tool`이 strategy에 기록되었다.

실패 케이스에서는 LLM 호출 단계에서 API/model error가 발생했고, `process_file_error` 이벤트와 `.failed.json`이 생성되었다.

### 잘 동작한 부분

- run 단위로 `llm_agent_run_<run_id>.jsonl`이 생성됨
- 전체 누적 로그 `llm_agent_events.jsonl`이 생성됨
- LLM decision과 recommended tool이 분리되어 기록됨
- tool 실행 결과가 `action_result`에 포함됨
- `duration_ms`, `llm_duration_ms`, `action_duration_ms`가 기록됨
- 실패 시 `process_file_error`와 failed strategy가 생성됨
- API key 원문이 로그에 저장되지 않음

### 문제 또는 개선할 부분

- 정상 trace에서 `--auto-continue`를 사용하지 않은 run은 `noise_cleanup_tool → retry_encoding.py`가 같은 run 안에서 이어지지 않는다.
- Gemini model name이 변경되거나 unavailable 상태가 되면 LLM 호출 단계에서 실패할 수 있다.
- 향후에는 active model 검증 또는 fallback profile 기능을 추가할 수 있다.
- token 사용량과 cost 추정은 아직 구현하지 않았다.

---

## Metrics

### 정상 trace 기준

| 항목 | 값 | 설명 |
|---|---:|---|
| run id | `20260527_141502` | 정상 trace run |
| processed files | 3 | pending strategy 3개 처리 |
| route count | `llm_review: 3` | 3개 모두 LLM review 대상 |
| tool call count | 1+ | `noise_cleanup_tool` 실행 |
| LLM decision types | `retry_same_tool`, `stop_with_exclusion` | retry 케이스와 종료 케이스 모두 존재 |
| total latency | 약 16초 | `agent_finish.duration_ms` 기준 |
| step latency | 기록됨 | `llm_duration_ms`, `action_duration_ms` |
| tool error count | 0 | 정상 run 기준 |

### 실패 trace 기준

| 항목 | 값 | 설명 |
|---|---:|---|
| run id | `20260527_141308` | 실패 trace run |
| error type | LLM API/model error | model unavailable |
| failure event | `process_file_error` | 파일 단위 처리 실패 |
| fallback output | `.failed.json` | 실패 strategy 파일 생성 |
| reusable as regression case | 가능 | 모델/config 검증 케이스로 활용 가능 |

---

## 민감정보 처리

### 저장하지 않은 정보

- API key 원문
- Authorization header 원문
- token 원문
- `.env` 파일 내용
- 개인 인증 정보

### 저장한 정보

- config path
- provider name
- model name
- profile name
- tool name
- tool options
- stdout/stderr preview
- strategy file path

### trace 공유 시 주의할 점

- 공개 repository에 API key, `.env`, 개인 token은 commit하지 않는다.
- 실제 고객 패킷 또는 민감 payload가 포함될 수 있는 경우 raw payload 전체 대신 preview/hash 중심으로 저장한다.
- `raw_llm_response`와 `stdout_preview`에 민감정보가 포함되지 않았는지 확인 후 공유한다.
- 실제 운영 데이터가 아닌 실습용 sample packet과 mock/filtered payload 중심으로 trace를 공유한다.

---

## 고도화 평가

| 평가 항목 | 구현 여부 | 결과 |
|---|---|---|
| correctness | 미구현 | 이번 주 필수 범위 아님 |
| groundedness | 부분 구현 | 최종 상태가 tool result와 strategy state에 근거함 |
| tool completeness | 부분 구현 | 필요한 tool과 next action이 trace에 남음 |
| tool order | 부분 구현 | event 순서로 복원 가능 |
| argument quality | 부분 구현 | `recommended_options`와 command가 저장됨 |
| regression | 미구현 | 실패 trace를 향후 regression dataset으로 활용 가능 |

---

## 배운 점

- 최종 결과만 저장하면 agent가 왜 해당 판단을 했는지 추적하기 어렵다.
- JSONL event stream 방식만으로도 agent observability 요구사항 대부분을 충족할 수 있다.
- 본 프로젝트처럼 file-based workflow agent에서는 natural language final answer보다 `file_status`, `decision`, `completion_status`, `required_next_action`이 더 중요한 최종 산출물이다.
- 실패 trace는 단순한 오류 로그가 아니라 model/config/tool fallback을 개선하기 위한 regression 후보가 될 수 있다.
- tool latency 자체보다 LLM decision, state transition, next action 추적이 더 중요했다.

---

## 자가 점검 체크리스트

| 항목 | 상태 |
|---|---|
| 개인 repository 링크 포함 | 완료 |
| 7주차 제출물 링크 포함 | 완료 |
| 정상 케이스 trace 포함 | 완료 |
| 실패 또는 예외 케이스 trace 포함 | 완료 |
| tool name 기록 | 완료 |
| tool arguments 기록 | 완료 |
| tool result/error 기록 | 완료 |
| final answer / stop reason 기록 | 완료 |
| latency 또는 step count 기록 | 완료 |
| 민감정보 처리 규칙 작성 | 완료 |
| trace 분석 작성 | 완료 |
