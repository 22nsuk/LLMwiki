---
title: "Raw Intake Absorption Decisions 2026-04-22"
page_type: "query"
corpus: "wiki"
source_count: 180
question_scope: "raw-intake-absorption-review"
created: "2026-04-22"
aliases:
  - "query--raw-intake-absorption-decisions-2026-04-22"
tags:
  - "corpus/wiki"
  - "type/query"
---
# query--raw-intake-absorption-decisions-2026-04-22

## Question
2026-04-21 raw intake batch에서 어떤 source-only page가 기존 source/synthesis route로 흡수되어야 하고, 어떤 항목이 seed로 남아야 하며, 어떤 cluster가 새 family를 만들 만큼 충분한가?

## Short answer
이 batch는 이제 단순 등록 상태가 아니다. 180개 intake source에는 `runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json`이라는 per-source absorption matrix가 붙어 있고, review trail은 provenance를 보존한 채 `refresh_existing_synthesis`, `create_new_synthesis_family`, `keep_source_only_seed`로 정리됐다.

2026-04-22 follow-through에서 두 개의 active queue는 이미 corpus에 반영됐다. `refresh_existing_synthesis`는 기존 synthesis `10`개를 갱신했고, `create_new_synthesis_family`는 새 synthesis `20`개를 만들었다. 이번 정리에서 남아 있던 12개 residual item은 모두 `keep_source_only_seed`로 정규화했으며, `middle-east-negotiation-and-iran-regime-friction`은 concept 승격 검토를 거쳐 [[concept--middle-east-negotiation-and-iran-regime-friction]]와 연결됐다. 실행 리포트는 `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-profiles-2026-04-22.json`에 있다.

## Evidence considered
- [[query--raw-intake-roundup-2026-04-21]]
- `ops/raw-registry.json`
- `wiki/source--*-2026-04-21.md`
- `system/system-raw-registry/wiki/*-intake-2026-04-21*.md`
- `runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json`

## Analysis
### 조치 집계
- `refresh_existing_synthesis`: `64`
- `create_new_synthesis_family`: `104`
- `keep_source_only_seed`: `12`

### 기존 synthesis 갱신 queue
- `synthesis--ai-capability-claims-and-validation-gap-2026-04-12`: `13` sources (W-222, W-226, W-233, W-234, W-235, W-250, W-303, W-313, W-347, W-348, W-350, W-352, W-368)
- `synthesis--middle-east-shipping-and-energy-risk-2026-04-12`: `12` sources (W-225, W-273, W-276, W-295, W-319, W-365, W-387, W-389, W-390, W-394, W-399, W-400)
- `synthesis--korea-defense-export-and-physical-ai-2026-04-18`: `11` sources (W-223, W-242, W-255, W-265, W-269, W-279, W-301, W-308, W-323, W-355, W-396)
- `synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18`: `8` sources (W-236, W-317, W-326, W-329, W-335, W-353, W-354, W-393)
- `synthesis--korea-fx-liquidity-and-spot-dollar-pressure-2026-04-14`: `6` sources (W-229, W-247, W-312, W-340, W-341, W-356)
- `synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14`: `5` sources (W-232, W-237, W-285, W-343, W-395)
- `synthesis--middle-east-war-macro-and-market-repricing-2026-04-13`: `3` sources (W-261, W-318, W-339)
- `synthesis--ai-compute-control-us-china-geopolitical-choke-2026-04-18`: `2` sources (W-228, W-290)
- `synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13`: `2` sources (W-240, W-331)
- `synthesis--ai-inference-economics-and-pricing-2026-04-18`: `2` sources (W-243, W-246)

### 신규 family 후보
- `middle-east-negotiation-and-iran-regime-friction`: `11` sources (W-259, W-337, W-358, W-359, W-360, W-361, W-362, W-363, W-364, W-376, W-377)
- `korea-corporate-governance-value-up-and-market-structure`: `10` sources (W-227, W-248, W-268, W-305, W-316, W-330, W-372, W-378, W-386, W-397)
- `global-political-economy-and-institutional-realignment`: `9` sources (W-252, W-277, W-291, W-298, W-321, W-351, W-371, W-384, W-385)
- `korea-financial-regulation-corporate-governance-and-consumer-redress`: `8` sources (W-249, W-263, W-266, W-294, W-328, W-333, W-380, W-391)
- `ai-product-platform-and-agentic-ui`: `7` sources (W-257, W-288, W-289, W-322, W-342, W-346, W-392)
- `korea-political-economy-and-policy-coordination`: `7` sources (W-278, W-302, W-304, W-309, W-320, W-369, W-370)
- `korea-public-science-health-and-social-policy`: `7` sources (W-256, W-292, W-293, W-299, W-307, W-366, W-375)
- `korea-real-estate-infrastructure-and-consumption`: `6` sources (W-230, W-231, W-267, W-300, W-367, W-381)
- `ai-adoption-labor-and-public-sector-deployment`: `4` sources (W-238, W-258, W-286, W-287)
- `commodity-supply-and-price-transmission`: `4` sources (W-284, W-311, W-334, W-344)
- `korea-india-industrial-and-energy-cooperation`: `4` sources (W-254, W-272, W-280, W-281)
- `korea-labor-tax-and-domestic-policy`: `4` sources (W-282, W-296, W-297, W-338)
- `korean-peninsula-deterrence-and-nuclear-intelligence-claims`: `4` sources (W-271, W-275, W-325, W-373)
- `public-health-behavior-and-risk-prevention`: `4` sources (W-253, W-262, W-264, W-382)
- `semiconductor-memory-supply-and-labor-risk`: `4` sources (W-245, W-306, W-327, W-357)
- `biomedicine-platform-and-disease-evidence`: `3` sources (W-244, W-315, W-345)
- `cyber-statecraft-and-ai-security`: `3` sources (W-224, W-270, W-388)
- `industrial-policy-space-and-ev-competition`: `3` sources (W-274, W-324, W-398)
- `energy-transition-policy-under-shock`: `1` sources (W-379)
- `korea-fiscal-and-public-debt-risk`: `1` sources (W-241)

### source-only seed 유지
- `corporate-operations-litigation-and-strategy-seeds`: `4` sources (W-239, W-251, W-336, W-349)
- `ai-index-report-metadata-only`: `1` sources (W-221)
- `biotech-market-conduct-and-regulation-seed`: `1` sources (W-332)
- `global-markets-misc-seed`: `1` sources (W-374)
- `korea-telecom-consumer-regulation-seed`: `1` sources (W-283)
- `middle-east-security-statecraft-seed`: `1` sources (W-314)
- `low-reuse-off-route-items`: `3` sources (W-260, W-310, W-383)

### Concept 승격 후속 반영
- `middle-east-negotiation-and-iran-regime-friction`: `wiki_missing_concept_candidate` advisory를 받았고, 기존 [[concept--middle-east-energy-shock-transmission]] 및 Middle East shipping/macro synthesis와의 경계를 유지하는 별도 concept로 [[concept--middle-east-negotiation-and-iran-regime-friction]]를 연결했다.

## Decision / takeaway
이 batch의 review trail은 JSON matrix를 기준으로 읽는다. 2026-04-22 후속 적용 기준으로 `refresh_existing_synthesis`와 `create_new_synthesis_family`는 더 이상 queue에 머물지 않고 corpus에 반영됐다. 남은 residual item은 모두 `keep_source_only_seed`로 정리돼, 이번 batch에는 별도의 `discard_from_active_routes` 대기열을 남기지 않았다.

## Follow-up questions
- 다음 batch에서도 source별 absorption action을 closeout 전에 필수로 확정할 것인가?
- 새로 canonical concept로 올린 Middle East negotiation route에 더 오래된 seed source를 흡수할 것인가?
- `low-reuse-off-route-items` seed는 장기적으로 misc router로 남길 것인가, 아니면 더 구체적 seed bucket으로 재분류할 것인가?

## Related pages
- [[index]]
- [[query--raw-intake-roundup-2026-04-21]]
- [[system-raw-registry]]
- [[concept--middle-east-negotiation-and-iran-regime-friction]]
- [[synthesis--middle-east-shipping-and-energy-risk-2026-04-12]]
- [[synthesis--middle-east-war-macro-and-market-repricing-2026-04-13]]
- [[synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18]]
- [[synthesis--korea-fx-liquidity-and-spot-dollar-pressure-2026-04-14]]

- [[synthesis--middle-east-negotiation-and-iran-regime-friction-2026-04-22]]
- [[synthesis--korea-corporate-governance-value-up-and-market-structure-2026-04-22]]
- [[synthesis--global-political-economy-and-institutional-realignment-2026-04-22]]
- [[synthesis--korea-financial-regulation-corporate-governance-and-consumer-redress-2026-04-22]]
- [[synthesis--ai-product-platform-and-agentic-ui-2026-04-22]]
- [[synthesis--korea-political-economy-and-policy-coordination-2026-04-22]]
- [[synthesis--korea-public-science-health-and-social-policy-2026-04-22]]
- [[synthesis--korea-real-estate-infrastructure-and-consumption-2026-04-22]]
- [[synthesis--ai-adoption-labor-and-public-sector-deployment-2026-04-22]]
- [[synthesis--commodity-supply-and-price-transmission-2026-04-22]]
- [[synthesis--korea-india-industrial-and-energy-cooperation-2026-04-22]]
- [[synthesis--korea-labor-tax-and-domestic-policy-2026-04-22]]
- [[synthesis--korean-peninsula-deterrence-and-nuclear-intelligence-claims-2026-04-22]]
- [[synthesis--public-health-behavior-and-risk-prevention-2026-04-22]]
- [[synthesis--semiconductor-memory-supply-and-labor-risk-2026-04-22]]
- [[synthesis--biomedicine-platform-and-disease-evidence-2026-04-22]]
- [[synthesis--cyber-statecraft-and-ai-security-2026-04-22]]
- [[synthesis--industrial-policy-space-and-ev-competition-2026-04-22]]
- [[synthesis--energy-transition-policy-under-shock-2026-04-22]]
- [[synthesis--korea-fiscal-and-public-debt-risk-2026-04-22]]

## Source trace
- `runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json`
- `wiki/query--raw-intake-roundup-2026-04-21.md`
- `ops/raw-registry.json`
- `system/system-raw-registry/wiki/ai-capability-governance-intake-2026-04-21.md`
- `system/system-raw-registry/wiki/ai-infra-compute-intake-2026-04-21.md`
- `system/system-raw-registry/wiki/defense-statecraft-intake-2026-04-21.md`
- `system/system-raw-registry/wiki/global-markets-misc-intake-2026-04-21-1.md`
- `system/system-raw-registry/wiki/global-markets-misc-intake-2026-04-21-2.md`
- `system/system-raw-registry/wiki/health-and-science-intake-2026-04-21.md`
- `system/system-raw-registry/wiki/korea-macro-domestic-intake-2026-04-21.md`
- `system/system-raw-registry/wiki/middle-east-energy-intake-2026-04-21.md`

- `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-profiles-2026-04-22.json`
