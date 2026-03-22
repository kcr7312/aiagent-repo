# 2주차 실습 과제: 프롬프트 엔지니어링으로 LLM 개선하기

## 배경

LLM은 텍스트를 잘 이해하지만, **복잡한 조건부 표 데이터에서 정확한 값을 찾고 추론하는 것**은 자주 실패합니다. 이번 과제에서는 실제 **의료급여 본인부담률 표**를 LLM에게 주고, 조건에 맞는 본인부담률을 답하게 합니다.

기본 프롬프트(Zero-shot)로는 정답률이 낮을 것입니다. 앞서 정리하셨던 다양한 파라미터들과 옵션들을 통해 **프롬프트 엔지니어링 기법을 순차적으로 적용하면서 정답률이 어떻게 개선되는지** 직접 확인하는 것이 이번 과제의 핵심입니다.


## 데이터

- `data/dataset.jsonl`: 질문 30건 + 난이도
- `data/answer_key.jsonl`: 정답 + 해설
- `image/2024 알기 쉬운 의료급여제도.pdf`, `image/image.png`: 의료급여 본인부담률 원본 자료

질문 예시

```
Q: 2종 수급권자인 생후 8개월 아기가 만성질환자이고 제2차의료급여기관에서 외래 진료를 받으면 본인부담률은?
A: 무료 (1세 미만 만성질환자 + 제2차의료급여기관 = 무료)
```

이 질문에 답하려면 여러 조건을 동시에 판단해야 합니다 — 수급권자 종별, 나이, 질환 유무, 의료기관 종별. **LLM이 이런 다중 조건 추론을 정확히 하도록 프롬프트로 유도**하는 것이 과제입니다.

## 실습 구조

### Step 1: Zero-shot Baseline

원본 자료(`image/` 아래 PDF·이미지)를 바탕으로 정리한 본인부담률 참조 데이터를 system prompt에 넣고, 질문만 user message로 보냅니다.

```python
copayment_reference = """아래는 원본 자료에서 정리한 의료급여 본인부담률 참조 데이터입니다.
..."""

system_prompt = f"""아래는 의료급여 본인부담률 참조 데이터입니다.
질문에 대해 정확한 본인부담률을 답하세요. 답만 간결하게 작성하세요.

{copayment_reference}
"""

response = client.chat.completions.create(
    model="gpt-5-mini",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ],
    temperature=0,
)
```

30건 전체를 돌리고 `data/answer_key.jsonl`의 `expected_answer`와 비교하여 **정답률**을 기록합니다.

### Step 2: Few-shot Prompting

system prompt에 **3개의 질문-답변 예시**를 추가합니다.
> Few-shot 예시로 사용한 질문은 평가에서 **제외**합니다 

### Step 3: Chain of Thought (CoT)

LLM이 답변 전에 **추론 과정을 단계별로 출력**하도록 유도합니다.

**Structured Outputs**를 활용하면 추론 과정과 최종 답변을 분리할 수 있습니다.


### Step 4: Self-Consistency

동일한 질문에 대해 **temperature를 올려 여러 번 생성**하고, **다수결 투표**로 최종 답을 결정합니다.

Self-Consistency는 **CoT + 다수결**의 조합입니다. Step 3의 CoT 프롬프트를 그대로 사용하되, 여러 번 생성하여 가장 많이 나온 답을 선택합니다.

- 참고: [Self-Consistency (한국어)](https://www.promptingguide.ai/kr/techniques/consistency)

### Step 5: (선택) 추가 기법 실험

아래 중 하나 이상을 추가로 시도해보세요.

- **프롬프트 구조 변경**: XML tags vs 마크다운 vs 구분자 없음
- **한/영 전환**: system prompt를 영어로 작성
- **표 형식 변경**: 마크다운 표 대신 JSON이나 YAML로 데이터 제공
- **역할 부여**: "당신은 국민건강보험공단의 본인부담률 산정 전문가입니다"

## 측정 방법

각 Step에서 30건(또는 Few-shot 제외 27건)에 대해 아래를 기록합니다.
- 반드시 구조화된 JSON 출력으로 반환합니다.
```
{
    "answer":"5%",
    "reason": "..."
}
```

```
정답률 = `answer_key.jsonl`의 `expected_answer`와 일치한 정답 수 / 전체 문항 수
```

## 구현 요구사항

### 필수


1. Step 1~4를 모두 구현하고 각 Step의 정답률을 기록
2. 각 Step에서 사용한 **프롬프트 전문**을 기록
3. 틀린 문항에 대해 **왜 틀렸는지** 분석

### 권장

- Langchain, LlamaIndex, Pydantic AI 등 AI 프레임워크 자유롭게 사용
- Python 사용
- Step 3에서 `pydantic` BaseModel로 추론 과정 구조화

### 금지

- ChatGPT/Claude 웹 UI 사용

## 제출물

PR 하나로 아래를 제출합니다.

제출 위치
- 브랜치 생성 `week2/<GithubID>` 후 PR 등록

필수 파일
- `week-2/<GithubID>/`
- `README.md` (이론 과제 답변 + 실습 과제 결과 포함)
- 관련 코드(참고용)

## README.md 필수 포함 항목

1. 사용한 모델, SDK, 실행 환경
2. 각 Step별 프롬프트 전문
3. 결과 요약 테이블 -> 프롬프트 기반 별 구성 
4. 오답 분석 — 가장 어려웠던 문항 3건과 원인
5. Step 1 → Step 4까지 정답률 개선 과정과 인사이트
6. (선택) Step 5 추가 실험 결과

## 참고자료

프롬프트 기법
- [Prompt Engineering Guide 한국어 — 전체 기법](https://www.promptingguide.ai/kr/techniques)
- [Zero-shot Prompting](https://www.promptingguide.ai/kr/techniques/zeroshot)
- [Few-shot Prompting](https://www.promptingguide.ai/kr/techniques/fewshot)
- [Chain-of-Thought Prompting](https://www.promptingguide.ai/kr/techniques/cot)
- [Self-Consistency](https://www.promptingguide.ai/kr/techniques/consistency)

프롬프트 모범 사례
- [Anthropic Claude 프롬프팅 모범 사례](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [OpenAI Prompt Engineering Guide](https://developers.openai.com/api/docs/guides/prompt-engineering)

Structured Outputs
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Anthropic Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)


## 힌트

- Zero-shot에서 hard 문항을 거의 못 맞추는 것은 **정상**입니다. 이것이 프롬프트 엔지니어링이 필요한 이유입니다.
- Few-shot 예시에 **추론 과정까지 포함**하면 (Few-shot CoT) 단순 Few-shot보다 효과가 좋을 수 있습니다.
- Self-Consistency에서 temperature가 너무 높으면 아예 엉뚱한 답이 나오고, 너무 낮으면 다양성이 없어 다수결의 의미가 없습니다. 0.5~0.8 범위를 실험해보세요.
- 참고 자료를 system prompt에 넣는 방식이 결과에 영향을 줍니다. 마크다운 표 그대로 vs JSON 변환 vs 핵심만 추출 vs 이미지 그대로 등을 비교해보세요.
