# 6주차 메인 안내: AI Agent 설계서 작성 참고자료

이 문서는 6주차 과제의 메인 안내 문서입니다. 실제 제출 요구사항과 설계서 템플릿은 [`TASK.md`](./TASK.md)를 기준으로 하고, 아래 내용은 `TASK.md`의 설계서를 작성할 때 참고하는 배경 자료입니다.

특히 `TASK.md`의 다음 섹션을 작성할 때 참고하세요.

| TASK.md 섹션 | README.md 참고 위치 |
|-------------|--------------------|
| 4. Agent 패턴 선택과 근거 | Agent 패턴, Workflow 패턴 |
| 5. 동작 명세 | 구성 요소, Agent 패턴 |
| 6. Tool 명세 | 구성 요소, 설계 축별 레퍼런스 |
| 8. 성공 판정 기준 | 설계 축별 레퍼런스의 Agent 평가 |
| 9. 제약·확장 | Multi-Agent, 프레임워크 |

제출물은 `TASK.md`의 형식을 따릅니다. README.md의 모든 내용을 별도 이론 과제로 정리할 필요는 없습니다.

## 구성 요소

| 요소 | 역할 | 레퍼런스 |
|------|------|----------|
| LLM | 추론, 다음 행동 결정 | [Lilian Weng — LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/) |
| Tool | 외부 세계와의 접점 (함수·API·DB) | [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) |
| Memory | 단기(대화 이력)·장기(사실·벡터) 상태 | [Lilian Weng — LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/) |
| Planning | 목표를 하위 태스크로 분해 | [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) |

## Agent 패턴

| 패턴 | 루프 구조 | 레퍼런스 |
|------|----------|----------|
| ReAct | Thought → Action → Observation | [ReAct — Yao et al., 2022](https://arxiv.org/abs/2210.03629) / [Prompt Engineering Guide (한국어)](https://www.promptingguide.ai/kr/techniques/react) |
| Reflection / Reflexion | 결과 자기 평가 → 재시도 | [Reflexion — Shinn et al., 2023](https://arxiv.org/abs/2303.11366) |
| Plan-and-Execute | 전체 계획 → 순차 실행 | [Plan-and-Solve — Wang et al., 2023](https://arxiv.org/abs/2305.04091) / [LangGraph Plan-and-Execute](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/plan-and-execute/) |
| Multi-Agent (Orchestrator-Workers) | 역할별 agent 협업 | [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system) |

## Workflow 패턴 (Agent 아님)

Anthropic이 경로가 고정된 비-Agent 패턴으로 분류.

| 패턴 | 구조 |
|------|------|
| Prompt chaining | 단계별 LLM 호출 직렬 연결 |
| Routing | 입력 분류 후 전용 핸들러로 분기 |
| Parallelization | 동일 입력을 여러 LLM에 병렬 처리 후 집계 |
| Orchestrator-workers | 오케스트레이터가 서브태스크 분배 (경로 고정) |
| Evaluator-optimizer | 생성 → 평가 → 재생성 루프 |

레퍼런스: [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)

주의: Orchestrator-workers는 설계 방식에 따라 Workflow일 수도 있고 Multi-Agent일 수도 있습니다.

- Workflow에 가까운 경우: 오케스트레이터가 항상 고정된 순서와 고정된 역할로 작업을 분배
- Multi-Agent에 가까운 경우: 요청에 따라 필요한 worker, 작업 순서, 반복 여부가 동적으로 달라짐

## 설계 축별 레퍼런스

| 축 | 레퍼런스 |
|----|----------|
| Tool 설계 | [OpenAI — A Practical Guide to Building Agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) |
| System prompt | [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) |
| 종료 조건·Guardrails | [OpenAI — A Practical Guide to Building Agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) |
| Agent 평가 (final/step/trajectory) | [LangSmith — Agent Evaluation](https://docs.smith.langchain.com/evaluation/tutorials/agents) / [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) |

## 프레임워크

| 프레임워크 | 레퍼런스 |
|-----------|----------|
| LangChain | [LangChain Concepts — Agents](https://python.langchain.com/docs/concepts/agents/) |
| LangGraph | [LangGraph 공식](https://langchain-ai.github.io/langgraph/) |
| CrewAI | [CrewAI 공식](https://docs.crewai.com/) |
| AutoGen | [AutoGen 공식](https://microsoft.github.io/autogen/) |
| MCP (Tool 연결 표준) | [MCP 공식](https://modelcontextprotocol.io/) |
