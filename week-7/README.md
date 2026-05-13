# 7주차 실습 과제: AI Agent 구현 프로젝트

## 배경

6주차에는 AI Agent 설계서(`design.md`)를 작성했습니다.

7주차에는 그 설계로 실제 동작하는 AI Agent 프로젝트를 구현합니다. 이번 주의 핵심은 새 주제를 다시 고르는 게 아닙니다. 6주차 설계의 Tool 명세, 동작 명세, 종료 조건, 성공 판정 기준이 코드에서 실제로 확인되는지 봅니다.

구현 코드는 각자 별도 GitHub repository를 생성해 작성합니다. 프로젝트명은 자유롭게 정합니다.

본 `ai-agent-repo`는 멘티들이 결과를 정리해서 올리는 공간입니다. 이 repository에는 구현 코드를 직접 올리지 않고, 개인 프로젝트 repository 링크와 실행 결과를 정리한 README만 PR로 제출합니다.

## 과제 목표

6주차 설계서대로 최소 동작 가능한 AI Agent를 구현합니다.

구현한 Agent는 다음 조건을 만족해야 합니다.

1. 6주차 설계서의 문제 정의와 사용자 시나리오를 유지합니다.
2. Tool 2개 이상을 실제 함수, API, 또는 mock으로 구현합니다.
3. LLM이 Tool 사용 여부와 순서를 판단합니다.
4. Tool 결과를 observation으로 받아 다음 판단에 사용합니다.
5. 종료 조건이 있습니다.
6. Tool 실패 처리가 있습니다.
7. 6주차 성공 판정 기준 중 최소 3개를 실행 결과로 확인합니다.

## 제출 방식

### 1. 개인 프로젝트 repository 생성

각자 별도 GitHub repository를 생성합니다.

개인 repository에는 실제 구현 코드를 올립니다.

필수 포함:

- 실행 코드
- `README.md`
- 실행 방법
- 필요한 환경 변수 설명
- Tool 목록
- 예시 입력/출력
- 6주차 설계서 또는 설계 PR 링크

선택 포함:

- 실행 로그
- 로그 기반 동작 분석
- 간단한 UI
- 실제 API 연동

### 2. ai-agent-repo에 PR 제출

본 `ai-agent-repo`에는 아래 경로로 요약 README를 제출합니다.

```text
week-7/{github-id}/README.md
```

이 파일에는 구현 코드를 넣지 않습니다. 프로젝트 링크와 실행 결과 요약만 넣습니다.

## 제출 기한

PR은 늦어도 금요일 18:00 전까지 올립니다.

이후에 올려도 되지만, 금요일 저녁 전까지 올린 PR을 기준으로 주말 리뷰를 진행합니다. 구현이 완성되지 않았더라도 현재까지 동작하는 범위와 막힌 지점을 README에 정리해서 제출합니다.

## 개인 repository 권장 구조

언어와 프레임워크는 자유입니다. 다만 아래 구조를 권장합니다.

```text
agent-project/
  README.md
  src/ 또는 app/
    main
    agent_loop
    tools
    prompts
  examples/
    input_1
    input_2
```

사용 가능한 프레임워크 예시:

- LangGraph
- LangChain
- OpenAI Agents SDK
- 직접 구현

프레임워크 사용은 필수가 아닙니다.

## 구현 범위

### 필수

- 6주차 설계 기반 구현
- Tool 2개 이상
- Agent loop 또는 framework 기반 동등 구조
- 종료 조건
- Tool 실패 처리
- 예시 입력 2개 이상
- 실행 방법 문서화

### 선택

- 실제 API 연동
- LangGraph / LangChain / OpenAI Agents SDK 사용
- 간단한 memory
- HITL
- Web UI
- 실행 로그 저장 및 분석

## 구현 체크리스트

### 1. 6주차 설계서 연결

- 6주차 `design.md` 또는 PR 링크가 있는가
- 같은 문제를 구현하고 있는가
- 설계에서 바뀐 점이 있다면 이유를 적었는가

### 2. Tool 구현

- Tool이 2개 이상인가
- 각 Tool의 입력/출력 스키마가 명확한가
- 성공과 실패를 구조화된 값으로 반환하는가
- 실제 API가 없다면 mock임을 명시했는가

Tool 반환 예시:

```json
{
  "ok": true,
  "data": {
    "city": "Seoul",
    "condition": "rain"
  },
  "error": null
}
```

Tool 실패 예시:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "TIMEOUT",
    "message": "weather API timeout"
  }
}
```

### 3. Agent loop

Agent가 아래 흐름을 갖는지 확인합니다.

```text
decide
-> tool call
-> observe
-> decide
-> final 또는 stop
```

프레임워크를 사용하면 이 loop를 직접 작성하지 않아도 됩니다. 다만 README에 어떤 방식으로 이 흐름이 구현됐는지 설명합니다.

### 4. 종료 조건

최소 하나 이상의 종료 조건이 있어야 합니다.

- `max_steps`
- `time_budget`
- `cost_budget`
- `done` signal
- 같은 Tool/argument 반복 감지
- Tool 실패 횟수 제한

종료 조건 없는 Agent는 제출 기준을 만족하지 않습니다.

### 5. 검증

6주차 성공 판정 기준 중 최소 3개를 실제 실행 결과로 확인합니다.

권장 테스트 케이스:

| 케이스 | 확인할 것 |
|--------|-----------|
| 정상 케이스 | 의도한 Tool 조합으로 최종 답변 생성 |
| Tool 실패 케이스 | 실패 시 fallback 또는 에러 응답 |
| 종료 조건 케이스 | max steps 또는 실패 횟수 초과 시 중단 |

## 실행 로그 분석

실행 로그 제출은 필수가 아닙니다. 다만 Agent가 실제로 어떻게 동작했는지 확인하려면 로그를 남기는 편이 좋습니다.

로그에는 최소한 다음 정도가 있으면 충분합니다.

```text
user input
selected tool
tool arguments
tool result
final answer
```

로그를 남겼다면 README에 다음을 짧게 분석합니다.

- 설계서에서 예상한 Tool 선택 흐름은 무엇이었는가
- 실제 실행에서 어떤 Tool이 어떤 순서로 호출됐는가
- 예상과 다르게 동작한 부분이 있었는가
- 불필요한 Tool 호출이 있었는가
- Tool 실패 시 의도한 방식으로 처리했는가
- 종료 조건이 실제로 동작했는가

이 항목은 정교한 모니터링 과제가 아닙니다. 이번 주에는 구현한 Agent가 설계에서 예상했던 방식으로 실제 실행되는지 확인하는 용도로만 사용합니다.

## ai-agent-repo 제출 README 템플릿

아래 템플릿을 `week-7/{github-id}/README.md`에 작성합니다.

~~~md
# 7주차 AI Agent 구현 프로젝트

## 프로젝트 링크

- Repository:
- 6주차 설계 PR 또는 design.md:

## 구현한 Agent

- Agent 이름:
- 해결하려는 문제:
- 타깃 사용자:

## 6주차 설계와의 연결

- 유지한 설계:
- 변경한 설계:
- 변경 이유:

## 사용한 Tool

| Tool 이름 | 실제/API/mock | 역할 |
|-----------|---------------|------|
| ... | ... | ... |

## 실행 패턴

- 선택한 패턴:
- 이유:
- 간단한 흐름:

## 실행 방법

```bash
# 설치

# 실행
```

## 예시 실행

### 예시 1

입력:

```text
...
```

출력:

```text
...
```

### 예시 2

입력:

```text
...
```

출력:

```text
...
```

## 실행 로그 분석

- 선택 사항입니다.
- 로그를 남겼다면 예상한 동작과 실제 Tool 호출 흐름을 비교합니다.

## 성공 판정 기준 확인

| 기준 | 결과 | 근거 |
|------|------|------|
| ... | 통과/실패 | ... |

## 구현하며 배운 점

- ...
~~~

## 주의사항

- API key, `.env`, 개인 token은 절대 commit하지 않습니다.
- 실제 결제, 환불, 이메일 발송, 삭제 등 side effect가 있는 Tool은 mock으로 대체합니다.
- 실제 개인정보가 포함된 DB를 사용하지 않습니다.
- 공개 API를 사용할 경우 rate limit과 실패 응답을 처리합니다.
- 6주차 설계와 달라진 부분은 반드시 README에 적습니다.

## 자가 점검 체크리스트

제출 전에 확인합니다.

1. 개인 repository 링크가 있는가
2. 6주차 설계 PR 또는 `design.md` 링크가 있는가
3. Tool 2개 이상이 구현됐는가
4. Tool 실패 처리가 있는가
5. 종료 조건이 있는가
6. 예시 입력 2개 이상이 있는가
7. 성공 판정 기준 3개 이상을 확인했는가
8. API key나 `.env`가 commit되지 않았는가

## 참고 자료

- [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [OpenAI Agents SDK — Tools](https://openai.github.io/openai-agents-js/guides/tools/)
- [LangChain — Models and tool calling](https://docs.langchain.com/oss/javascript/langchain/models#parallel-tool-calls)
