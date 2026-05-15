---
title: "Coffee Fermentation Processing"
page_type: "concept"
corpus: "wiki"
canonical: true
created: "2026-04-18"
aliases:
  - "concept--coffee-fermentation-processing"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--coffee-fermentation-processing

## Summary
coffee fermentation processing은 post-harvest fermentation을 저장 단계가 아니라 cup quality를 upstream에서 바꾸는 `microbial / chemical / sensory control variable`로 읽는 개념이다.

## Why it matters here
현재 coffee chemistry corpus에는 fermentation source가 있지만, [[concept--coffee-brew-chemistry]] 안에 묶여 있어 water, roast, brew temperature와 같은 레벨로 섞이기 쉽다. fermentation은 brewer가 추출 중 조절하는 변수가 아니라 producer/process 단계에서 volatile and nonvolatile matrix를 바꾸는 upstream variable이므로 별도 concept가 있으면 route가 선명해진다.

## Main body
### Fermentation changes the bean before brewing starts
[[source--coffee-fermentation-conditions-and-sensory-quality-2026-04-13]]는 yeast inoculation, processing condition, producing region이 volatile/nonvolatile composition과 sensory quality에 영향을 줄 수 있음을 보여 준다. 즉 fermentation은 추출 레시피의 보정 대상이 아니라, 컵에 들어올 chemical matrix를 먼저 형성하는 단계다.

### Strain, region, and process interaction matter
현재 corpus의 anchor source는 Saccharomyces cerevisiae와 Torulaspora delbrueckii, 자연건조와 pulped natural 처리, 지역 차이를 함께 본다. 이 때문에 `발효하면 맛이 좋아진다` 같은 단일 rule보다, strain effect와 origin/process interaction을 분리해 읽는 편이 안전하다.

### Future fermentation families should stay evidence-labeled
external review report는 anaerobic fermentation, carbonic maceration, lactic fermentation 같은 future subfamilies를 제안한다. 다만 현재 canonical source는 specific yeast inoculation experiment가 중심이므로, 이 subfamily들은 후속 raw가 들어오기 전까지 future ingest route로 남긴다.

## Scope boundaries
- 이 concept는 post-harvest processing과 fermentation-induced sensory/chemical changes를 다룬다.
- brew water, alkalinity, dissolved cations는 [[concept--coffee-water-chemistry]]가 우선이다.
- roast chemistry와 Maillard/Strecker 반응은 future roasting concept가 생기기 전까지 [[concept--coffee-brew-chemistry]]의 adjacent route로 둔다.
- 특정 fermentation protocol을 universal recipe로 추천하지 않는다.

## Examples and non-examples
- example: yeast inoculation이 sensory quality와 volatile/nonvolatile composition을 바꾼다는 실험 논문은 fermentation processing anchor다.
- example: anaerobic, lactic, carbonic maceration raw가 후속 ingest되면 이 concept의 subfamily 후보가 된다.
- non-example: cold brew steep time이나 water recipe는 fermentation이 아니라 brew-stage chemistry다.
- non-example: marketing-only "fermented coffee" claim은 microbial/process evidence 없이는 이 concept의 강한 근거가 아니다.

## How to reuse this concept
- fermentation source를 읽을 때는 `microbe/strain`, `processing method`, `origin/region`, `chemical profile`, `sensory result`를 분리해 기록한다.
- downstream brew chemistry와 연결할 때도, fermentation이 만든 matrix와 brewing이 끌어온 extraction result를 같은 원인으로 합치지 않는다.
- new fermentation source가 들어오면 anaerobic/lactic/carbonic 같은 label보다 먼저 evidence strength와 measured outcome을 확인한다.

## Related pages
- [[index]]
- [[query--coffee-science-corpus-map-2026-04-13]]
- [[concept--coffee-brew-chemistry]]
- [[concept--coffee-water-chemistry]]
- [[synthesis--coffee-brew-chemistry-and-processing-2026-04-13]]
- [[source--coffee-fermentation-conditions-and-sensory-quality-2026-04-13]]
- [[source--coffee-volatile-compounds-by-roast-and-brew-2026-04-13]]
- [[source--science-behind-good-cup-of-coffee-2026-04-13]]

## Open questions
- anaerobic, lactic, carbonic maceration source를 ingest하면 이 concept 안의 sections로 충분한가, 아니면 separate synthesis가 필요한가?
- fermentation-induced sensory differences는 roast 이후에도 얼마나 안정적으로 유지되는가?
- producer-level process variable과 consumer-level brewing variable을 어떤 bridge synthesis로 연결할 것인가?

## Source trace
- `raw/1-s2.0-S096399692030507X-main.pdf`
- `wiki/source--coffee-fermentation-conditions-and-sensory-quality-2026-04-13.md`
- `wiki/concept--coffee-brew-chemistry.md`
- `wiki/synthesis--coffee-brew-chemistry-and-processing-2026-04-13.md`
