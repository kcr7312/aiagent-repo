# 9주차 실습 과제: LLM Cost Optimization

## 배경

8주차에는 Agent 실행 과정을 trace로 남겼습니다.

이번 주에는 그 trace를 보고 LLM 비용이 어디서 발생하는지 찾은 뒤, 작은 최적화 하나를 실제로 적용합니다.

비용 최적화는 단순히 싼 모델을 고르는 일이 아닙니다. Agent가 어떤 history를 붙이는지, tool을 몇 개 노출하는지, retrieval context를 얼마나 넣는지, 실패했을 때 몇 번 재시도하는지에 따라 비용이 달라집니다.

이번 과제의 핵심은 자기 애플리케이션의 실행 흐름을 이해하고, 그 안에서 줄일 수 있는 부분을 근거 있게 고르는 데 있습니다.

## 과제 목표

아래 흐름으로 자신의 Agent 비용 구조를 분석하고 개선합니다.

```text
baseline trace
-> 비용 병목
-> 작은 최적화 1개
-> before / after 비교
-> 다음 최적화 계획
```

최적화 방법은 자유롭게 선택합니다.

블로그에서 다룬 tokenization, prompt caching, context pruning, model routing, batch 처리, self-hosted 전환 판단을 참고해도 됩니다.

- 참고 블로그: https://blog.aibox.today/llm-cost-optimization-ai-agent/

자신의 애플리케이션 구조를 보고 history 관리, tool 노출 범위, retrieval 결과 수, retry 횟수, step budget 등을 직접 줄여도 됩니다.

최적화가 실패해도 제출할 수 있습니다. 오히려 권장합니다. 비용은 줄었지만 Agent 동작이 깨졌다면, 어떤 기준이 깨졌는지와 왜 되돌려야 하는지를 숨기지 말고 정리합니다.

## 제출 방식

### 1. 개인 프로젝트 repository 업데이트

8주차에 observability를 추가한 개인 Agent repository를 업데이트합니다.

필수 포함:

- baseline trace 또는 log
- 비용 병목 분석
- 적용한 최적화 1개
- before / after 비교
- 정상 케이스 1개와 실패 또는 예외 케이스 1개 비교
- 측정 가능한 항목이 거의 없다면 더 작은 모델로 바꿔 기존 Agent 동작 기준이 유지되는지 비교
- README 업데이트

선택 포함:

- token 사용량 자동 수집
- 모델별 token / cost 비교
- prompt caching 가능성 분석
- latency 비교
- 최적화 후 동작 변화 분석
- 추가 최적화 후보 정리

### 2. ai-agent-repo에 PR 제출

본 `ai-agent-repo`에는 아래 경로로 요약 README를 제출합니다.

```text
week-9/{github-id}/README.md
```

이 파일에는 구현 코드를 넣지 않습니다. 개인 repository 링크와 최적화 분석 결과만 정리합니다.

## 제출 기한

PR은 늦어도 금요일 18:00 전까지 올립니다.

이후에도 제출할 수 있지만, 주말 리뷰는 금요일 저녁 전까지 올라온 PR을 기준으로 진행합니다. 최적화가 완성되지 않았더라도 baseline trace, 병목 분석, 시도한 최적화, 막힌 지점을 README에 정리해서 제출합니다.

## 구현 범위

### 필수

- 8주차 trace 또는 log 중 baseline으로 삼을 정상 케이스 1개와 실패 또는 예외 케이스 1개 선택
- baseline에서 LLM 호출 횟수, token, latency, tool call, retrieval context, retry 중 확인 가능한 항목 정리
- 비용이 커지는 원인 1개 이상 분석
- 작은 최적화 1개 이상 적용
- before / after 비교
- 가능하면 LLM 호출 횟수, input token, output token, latency를 모두 비교
- 최적화 후 기존 Agent 동작 기준이 유지되는지 확인
- 다음에 시도할 최적화 계획 작성

### 선택

- 모델별 tokenization 차이 비교
- prompt caching 적용 가능성 확인
- context pruning 또는 history trimming
- tool description 또는 tool 노출 범위 축소
- retrieval top-k 또는 chunk 수 조정
- tool result 요약 또는 필드 제한
- retry 횟수 또는 max step 제한
- model routing
- batch 처리 가능 작업 분리
- self-hosted LLM 전환 판단 기준 정리

## 분석 기준

| 단계 | 확인할 질문 |
|------|-------------|
| Baseline trace | 정상 케이스와 실패 또는 예외 케이스 중 어떤 실행을 기준으로 삼았는가 |
| 비용 병목 | token, tool call, retry, retrieval, history 중 무엇이 비용을 키웠는가 |
| 최적화 선택 | 왜 이 최적화를 먼저 적용했는가 |
| Before / After | LLM 호출 횟수, input token, output token, latency가 어떻게 바뀌었는가 |
| 동작 유지 | 6~8주차에서 정의한 성공 기준과 Agent 실행 흐름이 유지되는가 |
| 다음 계획 | 이번에 못 한 최적화는 무엇이고, 왜 다음 순서인가 |

## 측정 가이드

처음부터 정교한 비용 대시보드를 만들 필요는 없습니다.

가능한 방식으로 아래 항목을 확인합니다.

- SDK 응답의 `usage` 필드에서 input token과 output token 확인
- LangSmith, Langfuse, Phoenix 같은 tracing 도구에서 token, latency, run count 확인
- 직접 로그로 LLM 호출 횟수와 시작/종료 시간 기록
- token을 직접 얻기 어렵다면 tokenizer나 provider 콘솔로 대표 prompt를 수동 측정
- 그래도 측정 가능한 항목이 거의 없다면, 더 작은 모델로 바꿔 기존 Agent 동작 기준이 유지되는지 비교

## 최적화 예시

아래는 예시입니다. 반드시 이 중에서 고를 필요는 없습니다.

| 최적화 | 적용 예시 | 확인할 것 |
|--------|-----------|-----------|
| History trimming | 전체 대화 이력 대신 최근 N턴 또는 요약만 전달 | input token 감소, 맥락 손실 여부 |
| Context pruning | retrieval 결과 수나 chunk 길이 축소 | 답변 근거 유지 여부 |
| Tool 노출 축소 | 현재 요청에 필요한 tool만 LLM에 제공 | tool schema token 감소, tool 선택 실패 여부 |
| Tool result 축소 | tool 응답에서 필요한 필드만 observation으로 전달 | observation token 감소, 판단 정보 누락 여부 |
| Retry 제한 | 실패 시 재시도 횟수 또는 max step 제한 | 불필요한 반복 호출 감소, 실패 처리 품질 |
| Model routing | 단순 요청은 작은 모델, 복잡한 요청은 큰 모델 사용 | 품질 유지, 비용 감소 |
| Prompt caching 검토 | 반복되는 system prompt, 정책, tool schema를 안정된 prefix로 배치 | cache hit 가능성 |
| Batch 처리 | 즉시 응답이 필요 없는 요약·평가 작업 분리 | 처리 시간 허용 여부, 비용 감소 |

## ai-agent-repo 제출 README 템플릿

아래 템플릿을 `week-9/{github-id}/README.md`에 작성합니다.

~~~md
# 9주차 LLM Cost Optimization

## 프로젝트 링크

- Repository:
- 8주차 제출 README:

## Baseline Trace

분석 대상으로 삼은 정상 케이스:

```text
...
```

분석 대상으로 삼은 실패 또는 예외 케이스:

```text
...
```

현재 구조:

- Agent 이름:
- 주요 Tool:
- 사용 모델:
- LLM 호출 횟수:
- latency 또는 전체 실행 시간:
- 확인 가능한 token 사용량:

## 비용 병목 분석

비용이 커진 원인:

- ...

근거:

- ...

## 적용한 최적화

선택한 최적화:

- ...

선택 이유:

- ...

변경 내용:

- ...

## Before / After 비교

| 항목 | Before | After | 변화 |
|------|--------|-------|------|
| LLM 호출 횟수 | | | |
| Input token | | | |
| Output token | | | |
| Latency 또는 전체 실행 시간 | | | |
| Tool 호출 횟수 | | | |
| Retrieval context 수 | | | |

LLM 호출 횟수, input token, output token, latency 또는 전체 실행 시간은 가능하면 모두 측정합니다.

측정하지 못한 항목은 `측정 불가`로 표시하고 이유를 적습니다. 측정 가능한 항목이 거의 없다면, 더 작은 모델로 바꿔 동일한 요청에서 기존 Agent 동작 기준이 유지되는지 비교합니다.

## 동작 유지 확인

6~8주차에서 사용한 성공 기준 중 이번 비교에 사용할 항목:

- ...

최적화 전후에 동일하게 유지된 동작:

- ...

달라진 동작:

- ...

문제가 된다면 되돌릴 변경:

- ...

## 다음 최적화 계획

다음에 시도할 최적화:

- ...

이유:

- ...
~~~

## 자가 점검 체크리스트

제출 전에 아래 항목을 확인합니다.

1. 8주차 trace 또는 log를 근거로 baseline을 정했는가
2. 정상 케이스 1개와 실패 또는 예외 케이스 1개를 모두 비교했는가
3. 비용 병목을 추측이 아니라 실행 기록으로 설명했는가
4. 작은 최적화 1개 이상을 실제로 적용했는가
5. LLM 호출 횟수, input token, output token, latency를 가능한 범위에서 비교했는가
6. 비용 감소 후에도 기존 Agent 성공 기준과 실행 흐름이 유지되는지 확인했는가
7. 측정 가능한 항목이 거의 없다면 더 작은 모델 비교라도 수행했는가
8. 다음 최적화 계획이 현재 병목과 연결되는가
