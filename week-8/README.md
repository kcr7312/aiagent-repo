# 8주차 실습 과제: AI Agent Observability

## 배경

7주차에는 각자 AI Agent를 구현했습니다.

이번 주에는 Agent가 어떤 입력을 받았고, 어떤 prompt와 context로 model을 호출했으며, 어떤 tool 실행을 거쳐 최종 답변을 만들었는지 남겨봅니다.

핵심은 정교한 평가 시스템을 만드는 것이 아닙니다. 먼저 실행 과정을 다시 따라갈 수 있게 기록하는 것입니다.

```text
Evaluation은 결과를 판정하는 일입니다.
Observability는 그 결과가 만들어진 과정을 재현 가능하게 남기는 일입니다.
```

최종 답변만 저장하면 Agent가 왜 그런 답을 했는지 알기 어렵습니다. Trace가 있으면 어떤 tool을 호출했는지, 어떤 인자를 넘겼는지, tool 결과를 어떻게 사용했는지, 어디서 시간이 많이 걸렸는지 확인할 수 있습니다.

## 과제 목표

7주차에 구현한 Agent에 Observability를 추가합니다.

최소 목표는 다음 질문에 답할 수 있는 실행 기록을 남기는 것입니다.

1. 사용자가 어떤 요청을 보냈는가
2. Agent가 어떤 순서로 tool을 호출했는가
3. 각 tool에 어떤 인자가 전달됐는가
4. 각 tool은 어떤 결과 또는 에러를 반환했는가
5. 최종 답변은 무엇인가
6. 실행은 왜 종료됐는가
7. 전체 실행 시간과 step별 실행 시간은 어느 정도인가

관리형 도구를 써도 되고, JSON 로그 파일로 직접 남겨도 됩니다.

## 제출 방식

### 1. 개인 프로젝트 repository 업데이트

7주차에 만든 개인 Agent repository에 Observability 기능을 추가합니다.

필수 포함:

- Agent 실행 기록 저장
- trace 또는 log 예시 2개 이상
- 정상 케이스 1개
- 실패 또는 예외 케이스 1개
- README 업데이트

선택 포함:

- LangSmith, Langfuse, Phoenix 같은 tracing 도구 연동
- dashboard screenshot
- token 사용량 기록
- cost 추정
- 간단한 evaluator

### 2. ai-agent-repo에 PR 제출

본 `ai-agent-repo`에는 아래 경로로 요약 README를 제출합니다.

```text
week-8/{github-id}/README.md
```

이 파일에는 구현 코드를 넣지 않습니다. 개인 repository 링크와 trace 분석 결과를 정리합니다.

## 제출 기한

PR은 늦어도 금요일 18:00 전까지 올립니다.

이후에 올려도 되지만, 금요일 저녁 전까지 올린 PR을 기준으로 주말 리뷰를 진행합니다. 구현이 완성되지 않았더라도 현재까지 남긴 trace와 막힌 지점을 README에 정리해서 제출합니다.

## 구현 범위

### 필수

- 7주차 Agent 실행 가능 상태 유지
- 요청 1건을 하나의 trace 또는 run으로 묶어 기록
- Agent step별 기록 저장
- tool call의 이름, 인자, 결과, 에러 기록
- 최종 답변과 종료 이유 기록
- 정상 케이스와 실패 케이스 trace 각각 1개 이상 제출
- 민감정보를 그대로 남기지 않도록 masking 또는 제외 규칙 작성

### 선택

- LangSmith / Langfuse / Phoenix 연동
- OpenTelemetry 기반 span 기록
- token, latency, cost 집계
- tool 실패율 또는 step count 집계
- 실패 trace를 regression dataset 후보로 정리
- correctness, groundedness 같은 품질 평가 추가

## Trace에 남길 항목

처음부터 모든 항목을 남길 필요는 없습니다. 최소한 아래 항목을 권장합니다.

| 영역 | 기록 항목 |
|------|-----------|
| Request | user input, session id, timestamp |
| Prompt | system prompt 또는 prompt version |
| Model | provider, model name |
| Latency | total latency, step latency |
| Tool | tool name, arguments, result, error |
| Agent Step | step number, action, observation |
| Output | final answer, stop reason |
| Safety | masked fields, excluded fields |

민감정보가 포함될 수 있는 값은 원문을 그대로 저장하지 않습니다.

예시:

```text
user_id -> masked_user_id
order_id -> masked_order_id
address -> 저장하지 않음
payment_info -> 저장하지 않음
```

## Trace 예시

아래는 형식 예시입니다. 꼭 이 JSON 구조를 그대로 따를 필요는 없습니다.

```json
{
  "trace_id": "refund_agent_run_001",
  "user_input": "지난주에 산 무선 이어폰 환불 가능한가요?",
  "started_at": "2026-05-08T10:00:00Z",
  "steps": [
    {
      "step": 1,
      "type": "tool_call",
      "tool": "order_lookup",
      "arguments": {
        "masked_user_id": "u_***"
      },
      "result": {
        "product_id": "p_earbud_01",
        "purchased_days_ago": 8,
        "opened": true
      },
      "latency_ms": 120
    },
    {
      "step": 2,
      "type": "tool_call",
      "tool": "refund_policy_search",
      "arguments": {
        "query": "위생 관련 전자제품 개봉 후 환불"
      },
      "result": {
        "document_id": "refund_policy_03",
        "summary": "위생 관련 제품은 개봉 후 환불이 제한될 수 있습니다."
      },
      "latency_ms": 340
    }
  ],
  "final_answer": "개봉된 무선 이어폰은 환불이 제한될 수 있어 추가 확인이 필요합니다.",
  "stop_reason": "final_answer",
  "total_latency_ms": 2100
}
```

## 실행 로그 분석

제출 README에는 trace를 붙이는 것에서 끝내지 말고 짧게 분석합니다.

확인할 질문:

- 예상한 tool 호출 흐름은 무엇이었는가
- 실제로 어떤 tool이 어떤 순서로 호출됐는가
- 누락된 tool이 있었는가
- tool argument가 충분히 구체적이었는가
- tool 실패 시 fallback 또는 종료가 동작했는가
- 불필요한 반복 호출이 있었는가
- latency가 큰 step은 어디였는가
- 최종 답변이 tool 결과를 벗어나지 않았는가

## 고도화: Evaluation

정확성 평가는 이번 주 필수 요구사항이 아닙니다.

다만 trace가 남으면 다음 평가를 붙일 수 있습니다.

| 평가 항목 | 의미 |
|-----------|------|
| Final answer correctness | 최종 답변이 맞는가 |
| Groundedness | 최종 답변이 tool result 또는 retrieved context에 근거하는가 |
| Tool completeness | 필요한 tool을 빠짐없이 호출했는가 |
| Tool order | tool 호출 순서가 적절한가 |
| Argument quality | tool 인자가 충분히 구체적인가 |
| Regression | 이전에 실패한 케이스가 다시 통과하는가 |

고도화를 하고 싶은 경우에만 실패 trace를 dataset으로 모으고, prompt나 tool description 수정 전후를 비교합니다.

## ai-agent-repo 제출 README 템플릿

아래 템플릿을 `week-8/{github-id}/README.md`에 작성합니다.

~~~md
# 8주차 AI Agent Observability

## 프로젝트 링크

- Repository:
- 7주차 제출 README:

## 구현한 Observability

- 사용한 방식: JSON log / LangSmith / Langfuse / Phoenix / 기타
- trace 저장 위치:
- 기록하는 항목:

## Agent 실행 흐름

- Agent 이름:
- 주요 Tool:
- 종료 조건:

## 정상 케이스 Trace

입력:

```text
...
```

실행 요약:

| Step | Type | Name | 주요 입력 | 결과 |
|------|------|------|-----------|------|
| 1 | tool_call | ... | ... | ... |

최종 답변:

```text
...
```

## 실패 또는 예외 케이스 Trace

입력:

```text
...
```

실행 요약:

| Step | Type | Name | 주요 입력 | 결과 |
|------|------|------|-----------|------|
| 1 | tool_call | ... | ... | ... |

실패 처리:

- ...

## Trace 분석

- 예상한 흐름:
- 실제 흐름:
- 잘 동작한 부분:
- 문제 또는 개선할 부분:

## Metrics

| 항목 | 값 | 설명 |
|------|----|------|
| total latency | ... | ... |
| step count | ... | ... |
| tool error count | ... | ... |

## 민감정보 처리

- 저장하지 않은 정보:
- masking한 정보:
- trace 공유 시 주의할 점:

## 고도화 평가

선택 사항입니다. 구현하지 않았으면 비워두거나 "미구현"으로 적습니다.

| 평가 항목 | 구현 여부 | 결과 |
|-----------|-----------|------|
| correctness | 미구현/구현 | ... |
| groundedness | 미구현/구현 | ... |
| tool completeness | 미구현/구현 | ... |

## 배운 점

- ...
~~~

## 주의사항

- API key, `.env`, 개인 token은 절대 commit하지 않습니다.
- 사용자 개인정보, 주문번호, 주소, 결제 정보는 trace에 그대로 남기지 않습니다.
- system prompt와 retrieved context를 저장할 때는 공개 가능한 정보인지 확인합니다.
- 실제 결제, 환불, 이메일 발송, 삭제 같은 side effect가 있는 tool은 mock으로 대체합니다.
- 실패 trace를 공유할 때는 민감정보를 제거합니다.

## 자가 점검 체크리스트

제출 전에 확인합니다.

1. 개인 repository 링크가 있는가
2. 7주차 제출물 또는 구현 README 링크가 있는가
3. 정상 케이스 trace가 있는가
4. 실패 또는 예외 케이스 trace가 있는가
5. tool name, arguments, result, error가 기록되는가
6. final answer와 stop reason이 기록되는가
7. latency 또는 step count 중 하나 이상을 기록했는가
8. 민감정보 masking 또는 제외 규칙을 적었는가
9. trace를 보고 실행 흐름을 분석했는가

## 참고 자료

- [AI Agent LLM Observability Preview](https://blog.aibox.today/ai-agent-llm-observability/)
- [LangSmith Observability](https://docs.langchain.com/langsmith/observability)
- [OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-python/tracing/)
- [Langfuse Observability](https://langfuse.com/docs/observability/overview)
- [Phoenix Tracing](https://arize.com/docs/phoenix/get-started/get-started-tracing)
