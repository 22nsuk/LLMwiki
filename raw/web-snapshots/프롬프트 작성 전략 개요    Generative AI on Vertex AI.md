---
title: "프롬프트 작성 전략 개요  |  Generative AI on Vertex AI"
source: "https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-design-strategies?hl=ko"
author:
published: "unknown"
created: "2026-04-16"
description:
tags:
  - "clippings"
---

프롬프트를 설계하는 데 있어 옳거나 그른 방법은 없지만 모델 응답에 영향을 미치는 데 사용할 수 있는 일반적인 전략이 있습니다. 모델 성능 최적화를 위해서는 여전히 엄격한 테스트와 평가가 중요합니다.

대규모 언어 모델(LLM)은 언어 단위 간의 패턴과 관계를 배우기 위해 방대한 양의 텍스트 데이터에 대해 학습합니다. 일부 텍스트(프롬프트)가 제공되면 언어 모델은 정교한 자동 완성 도구와 같이 다음에 나올 내용을 예측할 수 있습니다. 따라서 프롬프트를 설계할 때 모델이 다음에 올 내용을 예측할 때 영향을 미칠 수 있는 다양한 요소를 고려하십시오.

### 프롬프트 엔지니어링 워크플로

프롬프트 엔지니어링은 모델 성능을 향상시킬 수 있는 테스트 기반의 반복 프로세스입니다. 프롬프트를 만들 때는 각 프롬프트의 목표와 예상 결과를 명확하게 정의하고 이를 체계적으로 테스트하여 개선할 부분을 파악할 수 있어야 합니다.

다음 다이어그램은 프롬프트 엔지니어링 워크플로를 보여줍니다.

![프롬프트 엔지니어링 워크플로 다이어그램](https://docs.cloud.google.com/static/vertex-ai/generative-ai/docs/learn/prompts/images/workflow.png?hl=ko)

## 효과적인 프롬프트를 만드는 방법

프롬프트의 효과에 궁극적으로 영향을 미치는 프롬프트의 두 가지 요소는 *콘텐츠* 와 *구조* 입니다.

- **콘텐츠:**
	태스크를 완료하려면 모델에 태스크와 관련된 모든 정보가 필요합니다. 이 정보에는 안내, 예시, 상황별 정보 등이 포함될 수 있습니다. 자세한 내용은 [프롬프트의 구성요소](#components-of-a-prompt) 를 참조하세요.
- **구조:**
	프롬프트에 필요한 모든 정보가 제공되더라도, 정보 구조를 제공하면 모델이 정보를 파싱하는 데 도움이 됩니다. 순서 지정, 라벨 지정, 구분 기호 사용 등이 모두 응답 품질에 영향을 줄 수 있습니다. 프롬프트 구조의 예시는 [샘플 프롬프트 템플릿](#sample-prompt-template) 을 참조하세요.

## 프롬프트 구성요소

다음 표에서는 프롬프트의 필수 구성요소와 선택적 구성요소를 보여줍니다.

<table><thead><tr><th>구성요소</th><th>설명</th><th>예</th></tr></thead><tbody><tr><td>목표</td><td>모델로 달성하려는 목표입니다. 구체적으로 설명하고 중요한 목표를 포함합니다. '미션' 또는 '목적'이라고도 합니다.</td><td>목표는 학생들에게 직접 답을 알려주지 않고 수학 문제를 풀 수 있게 도와주는 것입니다.</td></tr><tr><td>요청 사항</td><td>당면한 태스크를 수행하는 방법에 대한 단계별 안내입니다. '태스크', '단계', '경로'라고도 합니다.</td><td><ol><li>문제의 요점을 파악합니다.</li><li>학생이 어디에서 막혔는지 파악합니다.</li><li>문제의 다음 단계에 대한 힌트를 제공합니다.</li></ol></td></tr><tr><td colspan="3">선택적 구성요소</td></tr><tr><td>시스템 안내</td><td><p>태스크 집합에서 모델의 동작을 제어하거나 변경하는 작업이 포함될 수 있는 기술 또는 환경 지시문입니다. 대다수 모델 API의 경우 전용 매개변수에 시스템 안내가 지정됩니다.</p><p>시스템 요청 사항은 Gemini 2.0 Flash 이상 모델에서 사용할 수 있습니다.</p></td><td>프런트엔드 인터페이스의 코드 렌더링을 전문으로 하는 코딩 전문가입니다. 빌드하고자 하는 웹사이트의 구성요소를 설명할 때 빌드에 필요한 HTML과 CSS를 반환해야 합니다. 이 코드에 대한 설명을 제공하지 않습니다. UI 디자인 추천도 제공합니다.</td></tr><tr><td>페르소나</td><td>모델이 맡은 역입니다. '역할' 또는 '비전'이라고도 합니다.</td><td>여기서 귀하는 학생의 수학 숙제를 도와주는 수학 강사입니다.</td></tr><tr><td>제약조건</td><td>모델이 할 수 있는 것과 할 수 없는 것을 포함하여 응답을 생성할 때 준수해야 하는 것에 대한 제한사항입니다. '가드레일', '경계' 또는 '컨트롤'이라고도 합니다.</td><td>학생에게 직접 답을 알려주지 마세요. 대신 다음 단계에서 문제 해결을 위한 힌트를 제공하세요. 학생이 전혀 감을 잡지 못하는 경우 문제 해결을 위한 자세한 단계를 알려주세요.</td></tr><tr><td>어조</td><td>응답의 어조입니다. 캐릭터를 지정하여 스타일과 어조에 영향을 줄 수도 있습니다. '스타일', '음성', '기분'이라고도 합니다.</td><td>친근하고 전문적으로 응답합니다.</td></tr><tr><td>컨텍스트</td><td>모델이 당면한 태스크를 수행하기 위해 참조해야 하는 정보입니다. '배경', '문서' 또는 '입력' 데이터라고도 합니다.</td><td>학생의 수학 수업 계획 사본입니다.</td></tr><tr><td>퓨샷 예시</td><td>특정 프롬프트에 대한 응답 예시입니다. '예시' 또는 '샘플'이라고도 합니다.</td><td><code>input:</code> 부피가 1 입방 미터인 상자에 들어갈 수 있는 골프 공의 개수를 계산하려고 합니다. 1 입방 미터를 입방 센티미터로 변환하여 입방 센티미터 단위의 골프 공 부피로 나누었지만 시스템에서 내 답이 틀렸다고 표시됩니다.<br><code>output:</code> 골프 공은 구형이며 한 공간에 효율적으로 딱 맞게 들어갈 수 없습니다. 계산 시 구의 최대 적재 효율성을 고려해야 합니다.</td></tr><tr><td>추론 단계</td><td>추론을 설명하도록 모델에 지시합니다. 이렇게 하면 경우에 따라 모델의 추론 기능이 향상될 수 있습니다. '싱킹 단계'라고도 합니다.</td><td>추론을 단계별로 설명합니다.</td></tr><tr><td>응답 형식</td><td>사용할 응답 형식입니다. 예를 들어 응답을 JSON, 테이블, 마크다운, 단락, 글머리기호 목록, 키워드, 엘리베이터 피치 등으로 출력하도록 모델에 지시할 수 있습니다. '구조', '프레젠테이션' 또는 '레이아웃'이라고도 합니다.</td><td>응답 형식을 마크다운으로 지정합니다.</td></tr><tr><td>요약</td><td>프롬프트 끝에서 프롬프트의 핵심 사항, 특히 제약조건과 응답 형식을 간결하게 반복합니다.</td><td>정답을 제시하지 말고 힌트를 제공합니다. 항상 마크다운 형식으로 응답 형식을 지정합니다.</td></tr><tr><td>보호 장치</td><td>봇의 미션에 근거한 질문을 제시합니다. '안전 규칙'이라고도 합니다.</td><td>해당 사항 없음</td></tr></tbody></table>

당면한 특정 태스크에 따라 일부 선택적 구성요소를 포함하거나 제외할 수 있습니다. 또한 구성요소 순서를 조정하고 응답에 미치는 영향을 확인할 수도 있습니다.

## 샘플 프롬프트 템플릿

다음 프롬프트 템플릿은 잘 구조화된 프롬프트의 예시를 보여줍니다.

```
<OBJECTIVE_AND_PERSONA>
You are a [insert a persona, such as a "math teacher" or "automotive expert"]. Your task is to...
</OBJECTIVE_AND_PERSONA>

<INSTRUCTIONS>
To complete the task, you need to follow these steps:
1.
2.
...
</INSTRUCTIONS>

------------- Optional Components ------------

<CONSTRAINTS>
Dos and don'ts for the following aspects
1. Dos
2. Don'ts
</CONSTRAINTS>

<CONTEXT>
The provided context
</CONTEXT>

<OUTPUT_FORMAT>
The output format must be
1.
2.
...
</OUTPUT_FORMAT>

<FEW_SHOT_EXAMPLES>
Here we provide some examples:
1. Example #1
    Input:
    Thoughts:
    Output:
...
</FEW_SHOT_EXAMPLES>

<RECAP>
Re-emphasize the key aspects of the prompt, especially the constraints, output format, etc.
</RECAP>
```

## 권장사항

프롬프트 설계 권장사항은 다음과 같습니다.

- [명확하고 구체적인 요청 사항 제공](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/clear-instructions?hl=ko)
- [퓨샷 예시 포함](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/few-shot-examples?hl=ko)
- [다음과 같이 역할을 할당합니다.](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/assign-role?hl=ko)
- [컨텍스트 정보 추가](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/contextual-information?hl=ko)
- [시스템 안내 사용](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/system-instructions?hl=ko)
- [구조 프롬프트](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/structure-prompts?hl=ko)
- [이유를 설명하도록 모델에 지시](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/explain-reasoning?hl=ko)
- [복잡한 태스크 분류](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/break-down-prompts?hl=ko)
- [매개변수 값 실험](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/adjust-parameter-values?hl=ko)
- [프롬프트 반복 전략](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-iteration?hl=ko)

## 프롬프트 상태 체크리스트

프롬프트가 예상대로 작동하지 않는 경우 다음 체크리스트를 사용하여 잠재적인 문제를 파악하고 프롬프트의 성능을 개선하세요.

### 쓰기 문제

- **오타:** 철자 오류로 인해 성능이 저하될 수 있으므로 작업(예: *요악* 이 아닌 *요약*), 기술 용어 또는 항목 이름을 정의하는 키워드를 확인합니다.
- **문법:** 문장을 파싱하기 어렵거나, 불완전한 문장이 포함되거나, 주어와 동사가 일치하지 않거나, 구조적으로 어색한 경우 모델이 프롬프트를 제대로 이해하지 못할 수 있습니다.
- **구두점:** 쉼표, 마침표, 따옴표, 기타 구분 기호의 사용을 확인하세요. 구두점이 잘못되면 모델이 프롬프트를 잘못 해석할 수 있습니다.
- **정의되지 않은 전문 용어 사용:** 프롬프트에 명시적으로 정의되지 않은 경우 도메인별 용어, 약어 또는 두문자어를 범용적인 의미가 있는 것처럼 사용하지 마세요.
- **명확성:** 범위, 취해야 할 구체적인 단계 또는 암묵적인 가정을 확실히 모른다면 프롬프트가 명확하지 않을 수 있습니다.
- **모호성:** 구체적이고 측정 가능한 정의가 없는 주관적이거나 상대적인 수식어는 사용하지 마세요. 대신 객관적인 제약 조건을 제공하세요(예: '간단한 요약을 작성해' 대신 '3문장 이하로 요약을 작성해').
- **핵심 정보 누락:** 작업에 특정 문서, 회사 정책, 사용자 기록 또는 데이터 세트에 대한 지식이 필요한 경우 프롬프트에 해당 정보가 명시적으로 포함되어 있는지 확인합니다.
- **부적합한 단어 선택:** 모델을 혼동시킬 수 있으므로 불필요하게 복잡하거나 모호하거나 장황한 표현이 프롬프트에 있는지 확인합니다.
- **2차 검토:** 그래도 모델의 성능이 계속 저조하면 다른 사람에게 프롬프트 검토를 맡깁니다.

### 요청 사항 및 예 관련 문제

- **명백한 조작:** 감정적 호소, 공치사 또는 거짓된 압박을 사용하여 성능에 영향을 주려고 시도하는 프롬프트에서 핵심 작업 외의 언어를 삭제합니다. 1세대 파운데이션 모델은 '제대로 하지 않으면 정말로 나쁜 일이 일어날 거야'와 같은 요청 사항을 통해 개선되는 경우도 있었지만 더 이상은 파운데이션 모델 성능이 개선되지 않으며 많은 경우 오히려 악화됩니다.
- **충돌하는 요청 사항 및 예:** 프롬프트에서 논리적 모순이나 요청 사항 간의 불일치 또는 요청 사항과 예 간의 불일치가 있는지 감사하여 확인합니다.
- **중복된 요청 사항 및 예:** 프롬프트와 예를 살펴보고 정확히 동일한 요청 사항 또는 개념이 새로운 정보나 미묘한 차이를 추가하지 않는 약간 다른 방식으로 여러 번 언급되는지 확인합니다.
- **관련 없는 요청 사항 및 예:** 모든 요청 사항 및 예가 핵심 작업에 필수적인지 확인합니다. 요청 사항이나 예를 삭제해도 모델이 핵심 작업을 수행하는 능력이 저하되지 않는다면 관련성이 없는 것일 수 있습니다.
- **['퓨샷'](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/few-shot-examples?hl=ko) 예 사용:** 작업이 복잡하거나, 특정 형식이 필요하거나, 미묘한 어조가 있는 경우 샘플 입력과 해당 출력을 보여주는 설명 용도의 구체적인 예가 있는지 확인합니다.
- **출력 형식 사양 누락:** 모델이 출력 구조를 추측하도록 두지 말고 명확하고 명시적인 요청 사항을 사용하여 형식을 지정하고 퓨샷 예에서 출력 구조를 보여줍니다.
- **역할 정의 누락:** 모델에 특정 역할을 수행하도록 요청하려면 해당 역할이 시스템 요청 사항에 정의되어 있어야 합니다.

### 프롬프트 및 시스템 설계 문제

- **과소 지정된 작업:** 프롬프트의 요청 사항이 특이 사례와 예상치 못한 입력을 처리하는 명확한 경로를 제공하고 삽입된 데이터가 항상 존재하고 형식이 올바르다고 가정하는 대신 누락된 데이터를 처리하는 요청 사항을 제공하는지 확인합니다.
- **모델 기능 외의 작업:** 모델에 알려진 근본적인 한계가 있는 작업을 수행하도록 요청하는 프롬프트를 사용하지 마세요.
- **과도한 작업:** 프롬프트에서 모델이 단일 전달에서 여러 개의 서로 다른 인지 작업을 수행하도록 요청하는 경우(예: 1. 요약, 2. 항목 추출, 3. 번역 4. 이메일 초안 작성) 너무 많은 작업을 시도하게 될 수 있습니다. 요청을 별도의 프롬프트로 나누세요.
- **비표준 데이터 형식:** 모델 출력을 기계가 읽을 수 있어야 하거나 특정 형식을 따라야 하는 경우 일반적인 라이브러리에서 파싱할 수 있는 JSON, XML, 마크다운, YAML과 같은 널리 알려진 표준을 사용합니다. 사용 사례에 비표준 형식이 필요한 경우 모델에 일반적인 형식으로 출력하도록 요청한 다음 코드를 사용하여 출력을 변환하는 것이 좋습니다.
- **잘못된 연쇄적 사고(CoT) 순서:** 모델이 단계별 추론을 완료하기 전에 최종적인 구조화된 대답을 생성하는 예를 제공하지 마세요.
- **사고 모드와 추론:** [사고 모드](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking?hl=ko) 를 사용하는 경우 모델이 작업을 추론하는 방법에 관한 단계별 요청 사항 없이 프롬프트를 작성해 보세요. 대신 사고 모드를 사용해 테스트하고 사고 모드가 생성하는 단계별 추론이 명시적인 단계별 추론 요청 사항보다 성능을 개선하는지 확인합니다.
- **충돌하는 내부 참조:** 모델이 프롬프트의 여러 다른 위치에서 분산된 요청 사항을 조합해야 하는 비선형 논리 또는 조건이 포함된 프롬프트를 작성하지 마세요.
- **프롬프트 인젝션 위험:** 프롬프트에 삽입된 신뢰할 수 없는 사용자 입력과 관련된 명시적 보호 장치가 있는지 확인합니다. 이는 심각한 보안 위험이 될 수 있습니다.

## 다음 단계

- [프롬프트 갤러리](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/prompt-gallery?hl=ko) 에서 프롬프트 예시 살펴보기
- [Vertex AI 프롬프트 옵티마이저(미리보기)](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-optimizer?hl=ko) 를 사용하여 [Google 모델](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/models?hl=ko) 과 함께 사용할 프롬프트를 최적화하는 방법 알아보기
- [책임감 있는 AI 권장사항 및 Vertex AI 안전 필터](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/responsible-ai?hl=ko) 알아보기
