---
title: "Coffee Sensory Lexicon"
page_type: "concept"
corpus: "wiki"
canonical: true
created: "2026-04-13"
aliases:
  - "concept--coffee-sensory-lexicon"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--coffee-sensory-lexicon

## Summary
coffee sensory lexicon은 커피 향미를 기술할 때 쓰는 정의된 용어 집합과 그 관계 구조를 뜻한다. 단순 flavor wheel만이 아니라, 각 감각 속성의 정의, reference, clustering 방식, 그리고 acidity·mouthfeel·aftertaste까지 포함하는 묘사 체계를 가리킨다.

## Why it matters here
coffee science corpus는 추출 변수만으로는 충분하지 않고, 컵에서 관찰된 감각 차이를 같은 언어로 기술해야 재사용 가치가 생긴다. 이 concept는 flavor wheel, character wheel, WCR lexicon 같은 source를 하나의 canonical vocabulary 문제로 묶는다.

## Main body
### lexicon과 wheel은 같은 것이 아니다
lexicon은 용어와 정의의 목록이고, wheel은 그 용어를 시각적으로 배열한 지도에 가깝다. 따라서 flavor wheel이 보기 쉬운 인터페이스라면, sensory lexicon은 그 뒤의 canonical dictionary 역할을 한다.

### 왜 industry에 중요한가
coffee tasting에서 용어가 정리돼 있지 않으면 서로 다른 패널, roaster, trainer가 같은 컵을 두고도 다른 말을 하게 된다. lexicon과 wheel은 공통 reference를 제공해 sensory discussion을 반복 가능한 비교 대상으로 만든다.

### flavor만으로는 부족하다
최근 source들은 acidity, mouthfeel, aftertaste 같은 character가 기존 flavor wheel보다 덜 정리돼 있었다고 지적한다. 따라서 coffee sensory lexicon은 aroma/flavor vocabulary를 넘어서 cup experience 전체를 다루는 방향으로 확장된다.

### 무엇이 이 concept의 경계 바깥인가
이 concept는 추출 yield, TDS, flow rate 같은 process variable 자체를 설명하지 않는다. sensory language가 공정 변수와 연결될 수는 있지만, 그 변수의 인과 구조는 `coffee-extraction-and-brew-control` 쪽이 맡는다.

### 후속 source에서 먼저 볼 신호
새 source가 들어오면 용어 정의를 제시하는지, 기존 wheel을 재구성하는지, 아니면 acidity·mouthfeel·aftertaste처럼 아직 덜 표준화된 character를 보완하는지부터 보는 편이 좋다. 이 세 신호가 있으면 coffee sensory lexicon 축으로 편입할 가치가 높다.

## Scope boundaries
이 concept는 커피 감각을 `어떤 단어로, 어떤 기준으로, 어떤 구조 안에서` 말할지 다룬다. 그래서 extraction yield나 roast chemistry처럼 감각 차이의 원인을 설명하는 문헌과는 연결되더라도, 중심 관심은 원인보다 묘사 체계에 있다.

또한 모든 tasting note 모음이 곧 sensory lexicon은 아니다. 누가 봐도 예쁜 descriptor list라도 정의, reference, 구조적 clustering이 없으면 canonical vocabulary로 쓰기엔 약하다.

## Examples and non-examples
example은 WCR lexicon처럼 용어와 정의를 제공하는 자료, flavor wheel처럼 그 용어를 시각적으로 재배치하는 자료, character wheel처럼 부족한 감각 층을 보완하는 자료다. 이 셋은 서로 역할이 다르지만 같은 lexicon 문제를 푸는 자료로 묶을 수 있다.

non-example은 단일 로스터의 상품 tasting note나, 추출 조건에 따른 flavor 변화 관찰 메모다. 감각 언어가 등장하더라도 그것만으로는 공통 vocabulary infrastructure라고 보기 어렵다.

## How to reuse this concept
후속 source를 읽을 때는 `정의가 있는가`, `reference sample 또는 구조적 grouping이 있는가`, `기존 vocabulary의 공백을 메우는가`를 먼저 보면 된다. 이 세 질문으로 descriptor list와 reusable lexicon을 빠르게 구분할 수 있다.

새 synthesis에서 이 concept를 재사용할 때는 flavor 중심인지, character 확장인지, training interface인지까지 같이 적는 편이 좋다. 그래야 lexicon, wheel, poster가 각자 어떤 역할을 하는지 future session이 덜 섞어 읽게 된다.

## Related pages
- [[index]]
- [[query--coffee-science-corpus-map-2026-04-13]]
- [[synthesis--coffee-sensory-language-and-flavor-mapping-2026-04-13]]
- [[source--world-coffee-research-sensory-lexicon-v2-2026-04-13]]
- [[source--coffee-tasters-flavor-wheel-redesign-2026-04-13]]
- [[source--coffee-character-wheel-beyond-flavor-2026-04-13]]
- [[source--coffee-flavor-wheel-poster-2026-04-13]]

## Open questions
- flavor vocabulary와 character vocabulary를 같은 wheel 안에서 다루는 것이 실제 cupping workflow에 유리한가?
- 앞으로 coffee sensory lexicon에 process-linked descriptor까지 포함해야 하는가?

## Source trace
- `raw/20170622_WCR_Sensory_Lexicon_2-0-1.pdf`
- `raw/Journal of Food Science - 2016 - Spencer - Using Single Free Sorting and Multivariate Exploratory Methods to Design a New.pdf`
- `raw/Journal of Sensory Studies - 2023 - Williams - Coffee is more than flavor the creation of a coffee character wheel.pdf`
- `raw/flavorwheel.pdf`
- `wiki/synthesis--coffee-sensory-language-and-flavor-mapping-2026-04-13.md`
