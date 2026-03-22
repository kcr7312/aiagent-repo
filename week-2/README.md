# 2주차 이론 과제: 프롬프트 엔지니어링 기법 조사

## 개요

이론 과제는 프롬프트 엔지니어링의 핵심 기법을 **직접 조사하고 정리**하는 과제입니다. 실습 과제에서 사용할 기법들의 원리를 이해하는 것이 목적입니다.

## 필수 조사 항목

아래 자료를 읽고 각 기법에 대해 정리하세요.

### 1. 프롬프트 기법 4가지 정리

아래 4가지 기법을 각각 조사하고, **정의 → 동작 원리 → 예시 → 장단점**을 정리하세요.

| 기법 | 필수 참고 자료 |
|------|-------------|
| Zero-shot Prompting | https://www.promptingguide.ai/kr/techniques/zeroshot |
| Few-shot Prompting | https://www.promptingguide.ai/kr/techniques/fewshot |
| Chain-of-Thought (CoT) | https://www.promptingguide.ai/kr/techniques/cot |
| Self-Consistency | https://www.promptingguide.ai/kr/techniques/consistency |

각 기법별로 아래를 포함해주세요.
- **한 줄 정의**: 이 기법이 무엇인지 한 문장으로
- **핵심 원리**: 왜 효과가 있는지 (1주차 autoregressive 생성과 연결)
- **사용 예시**: 자료에서 본 예시를 자신의 말로 설명
- **언제 쓰면 좋은지 / 언제 효과가 적은지**

### 2. 추가 기법
다양한 프롬프트 방법론이 존재합니다. 테스트 한 것들을 자유롭게 정리해주세요.

- [Generate Knowledge Prompting](https://www.promptingguide.ai/kr/techniques/knowledge)
- [Prompt Chaining](https://www.promptingguide.ai/kr/techniques/prompt_chaining)
- [Tree of Thoughts](https://www.promptingguide.ai/kr/techniques/tot)
- [ReAct](https://www.promptingguide.ai/kr/techniques/react)
- [Meta Prompting](https://www.promptingguide.ai/kr/techniques/meta-prompting)

또는 아래 외부 자료에서 흥미로운 기법을 찾아 정리해도 됩니다.
- [Anthropic 프롬프트 엔지니어링 가이드 (한국어)](https://platform.claude.com/docs/ko/build-with-claude/prompt-engineering/overview)

### 3. 실습 과제 예측

실습 과제(`TASK.md`)와 `data/`, `image/` 아래의 의료급여 본인부담률 자료를 보고, **실습 전에 아래 가설을 세워주세요**.

1. Zero-shot(Step 1)에서 정답률이 어느 정도일지 예측하고 이유를 설명하세요
2. 어떤 난이도(easy/medium/hard)에서 가장 큰 개선이 일어날지 예측하세요
3. 4가지 기법(Zero-shot → Few-shot → CoT → Self-Consistency) 중 **가장 큰 정답률 점프**가 어디서 일어날지 예측하세요

> 실습 후에 가설과 실제 결과를 비교하여 본인의 제출 README(`week-2/<GithubID>/README.md`)에 포함하여 제출합니다.

## 추가 참고 자료

프롬프트 기법 전체 맵
- [Prompt Engineering Guide — Techniques (한국어)](https://www.promptingguide.ai/kr/techniques)
- [The Prompt Report](https://arxiv.org/abs/2406.06608) — 1,500+ 논문, 58가지 기법 분류

모델별 프롬프트 가이드
- [Anthropic Claude 프롬프팅 모범 사례](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [GPT-4.1 Prompting Guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)
- [Gemini Prompt Design Strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies)

CoT 관련 최신 연구 (선택 읽기)
- [To CoT or not to CoT?](https://arxiv.org/abs/2409.12183) (ICLR 2025) — CoT 효과가 수학/기호 추론에 편중됨
- [Reasoning Models Don't Always Say What They Think](https://arxiv.org/abs/2505.05410) (Anthropic, 2025) — CoT의 충실성 문제

## 제출 형식

- 제출 README(`week-2/<GithubID>/README.md`)에 이론 과제 답변 포함
- 실습 과제 결과와 함께 제출
- 3번 가설은 실습 전/후 비교 포함
