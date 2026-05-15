---
title: "Research Object Crate (RO-Crate)"
source: "https://www.researchobject.org/ro-crate/about_ro_crate"
author:
published: "unknown"
created: "2026-04-13"
description: "What RO-Crate is, how RO-Crate makes research FAIR, and how to get started"
tags:
  - "clippings"
---

## RO-Crate 소개

## 목차

1. [RO-Crate 소개](#about-ro-crate-1)
2. [RO-Crate란 무엇인가요?](#what-is-an-ro-crate)
3. [RO-Crate의 응용 분야](#applications-of-ro-crate)
4. [RO-Crate가 연구를 공정하게 만드는 방법](#how-ro-crate-makes-your-research-fair)
5. [어디서부터 시작해야 할까요?](#where-do-i-start)
	1. [예시를 통해 배우세요](#learn-by-example)
		2. [간략한 기술 개요](#quick-technical-overview)
		3. [RO-Crate 팀에 문의하세요](#speak-to-the-ro-crate-team)
		4. [자주 묻는 질문](#faq)
6. [RO-Crate를 인용하세요](#cite-ro-crate)
	1. [RO-Crate를 프로젝트/접근 방식으로 인용하십시오.](#cite-ro-crate-as-projectapproach)
		2. [RO-Crate 사양(모든 버전)을 인용하십시오.](#cite-ro-crate-specification-any-version)
		3. [기타 인용문](#other-citations)

## RO-Crate 소개

RO-Crate는 사람들이 연구를 [FAIR](https://www.go-fair.org/fair-principles/) (찾기 쉽고, 접근 가능하며, 상호 운용 가능하고, 재사용 가능)하게 만들 수 있도록 돕는 것을 목표로 합니다. 혹시 이런 질문을 접해 보신 적이 있나요?

- **연구자:** 사람들이 내 데이터를 (재)사용하고 분석 결과를 재현하는 방법을 알도록 하려면 어떻게 해야 할까요?
- **데이터 소비자:** 수천 개의 알 수 없는 이름의 파일로 구성된 데이터 세트를 어떻게 찾고 이해할 수 있을까요?
- **데이터 관리자:** 저는 새로운 대규모 프로젝트에 참여하고 있는데, 우리가 생성하는 데이터를 FAIR 원칙에 따라 관리하려면 어떻게 해야 할까요?

RO-Crate는 이러한 모든 **메타데이터 관련 질문** 에 답하도록 설계되었습니다.

## RO-Crate란 무엇인가요?

[RO-Crate는 연구 대상](https://www.researchobject.org/ro-crate/background#research-object-background) 전체를 통합적으로 보여주는 도구로 , 연구 방법, 데이터, 결과물, 그리고 프로젝트 또는 연구 성과까지 모두 포함합니다. 이 모든 것을 연결함으로써 연구 결과물을 맥락과 함께 일관성 있는 전체로서 공유할 수 있습니다.

RO-Crates는 데이터와 메타데이터가 어디에 저장되어 있든 상관없이 데이터를 연결합니다. 따라서 논문에서 데이터를 찾을 수 있고, 데이터에서 저자를 찾을 수 있는 식입니다.

예를 들어, RO 크레이트에는 저자의 이름만 포함되는 것이 아닙니다. 저자의 ORCID도 포함되며, 이는 소속 기관, 연구 자금 출처 및 기타 출판물과 연결됩니다.

![RO-Crate 연결을 나타내는 다이어그램입니다. '패키지 및 구성품 설명'이라고 표시된 열린 골판지 상자에는 ORCID를 가진 사람과 RRID를 가진 실험 장비가 들어 있습니다. 이 상자는 DOI를 통해 '통합 보기'라고 표시된 말풍선에 연결되어 있으며, 이 말풍선에는 다른 유형의 연구 객체가 포함되어 있습니다. 각 객체 유형에는 해당 데이터의 저장소 또는 레지스트리를 가리키는 화살표가 있습니다. 예를 들어 워크플로는 WorkflowHub, 프레젠테이션은 PubMed, 데이터는 데이터베이스로 연결됩니다.](https://www.researchobject.org/ro-crate/assets/img/ro-crate_packaging.png)

RO-Crates는 ORCID 및 DOI와 같은 영구 식별자를 사용하여 다양한 출처의 연구 객체와 연결되거나 연결될 수 있습니다. 이미지 출처: Goble, C. (2024년 2월 16일). FAIR 디지털 연구 객체: 메타데이터 여정. 오클랜드 대학교 세미나, 오클랜드. Zenodo. https://doi.org/10.5281/zenodo.10710142

## RO-Crate의 응용 분야

RO-Crate는 연구 데이터를 공유하기 위한 구조화된 패키지입니다. RO-Crate는 다음과 같은 기능을 제공합니다.

- 파일을 포함하고 온라인에 저장된 대규모 데이터 세트에 대한 링크를 제공합니다.
- 분석 과정 전체(입력값, 출력값, 사용 도구 포함)를 기록하십시오.
- 관련 논문 및 데이터 세트를 연결합니다.
- 장기 보관을 위해 데이터 세트를 보존하세요.
- 다양한 용도를 조합하여 여러 요구에 맞게 사용하세요.

RO-Crate는 생물정보학, 디지털 인문학, 규제 과학 등의 분야에서 사용됩니다. 또한 다양한 커뮤니티에서 특정 데이터 및 요구 사항에 맞게 RO-Crate를 적용하고 확장할 수 있습니다.

## RO-Crate가 연구를 공정하게 만드는 방법

**검색 용이성:** RO-Crate는 Zenodo와 같은 저장소에 게시하고 다른 데이터와 마찬가지로 DOI를 부여할 수 있습니다. 연결된 메타데이터는 RO-Crate 사용자가 관련 연구, 인물 및 기관을 찾는 데 도움이 됩니다.

**접근성:** RO-Crate는 [FAIR Signposting](https://signposting.org/FAIR/) 과 호환되므로 DOI 또는 기타 영구 식별자만 있으면 메타데이터를 자동으로 검색할 수 있습니다.

**상호 운용성: RO-Crate는 표준적이고 널리 사용되는 웹 기술(JSON-LD 및** [schema.org](http://schema.org/) 포함)을 기반으로 하므로 플랫폼 간 호환성과 상호 운용성이 뛰어납니다. 또한 외부 데이터가 RO-Crate 자체를 사용하는지 여부와 관계없이 모든 종류의 외부 (메타)데이터를 참조할 수 있을 만큼 유연합니다.

**재사용 가능:** RO-Crate는 상세한 출처 정보를 기록하도록 설계되었습니다. 예를 들어, RO-Crate에는 분석의 일부로 실행된 개별 단계에 대한 완전한 정보가 포함될 수 있으며, 여기에는 입력, 출력, 컴퓨팅 환경 및 참여 연구자가 포함됩니다.

[RO-Crate는 FAIR Signposting과 결합될 때 FAIR 디지털 객체 프레임워크](https://fairdigitalobjectframework.org/) 의 실질적인 구현체가 됩니다 .

## 어디서부터 시작해야 할까요?

#### 예시를 통해 배우세요

RO-Crate에 대해 더 자세히 알아보려면 [여기에서 튜토리얼과 자료를](https://www.researchobject.org/ro-crate/tutorials) 참조하세요.

RO-Crate를 사용하는 프로젝트를 찾아보거나 [도메인](https://www.researchobject.org/ro-crate/domains), [프로젝트 역할](https://www.researchobject.org/ro-crate/roles) 또는 [작업 에 대한 관련 정보를 찾으려면](https://www.researchobject.org/ro-crate/tasks) [사용 사례](https://www.researchobject.org/ro-crate/use_cases) 페이지를 방문할 수도 있습니다 .

#### 간략한 기술 개요

RO-Crate에 대한 기술적인 소개는 [RO-Crate 기술 개요를](https://www.researchobject.org/ro-crate/technical_overview) 참조하십시오.

RO-Crate와 그 전신 제품의 역사에 대해 알아보려면 [배경](https://www.researchobject.org/ro-crate/background) 페이지를 읽어보세요.

#### RO-Crate 팀에 문의하세요

모든 수준에 적합한 저희 드롭인 세션에 참여하시거나 [ro-crate@researchobject.org](mailto:ro-crate@researchobject.org) 로 팀에 이메일을 보내주세요.

자세한 내용은 [커뮤니티](https://www.researchobject.org/ro-crate/community) 페이지를 참조하세요.

#### 자주 묻는 질문

[자주 묻는 질문(FAQ)](https://www.researchobject.org/ro-crate/faq) 에서 일반적인 질문에 대한 답변을 확인하세요.

## RO-Crate를 인용하세요

#### RO-Crate를 프로젝트/접근 방식으로 인용하십시오.

Stian Soiland-Reyes, Peter Sefton, Mercè Crosas, Leyla Jael Castro, Frederik Coppens, José M. Fernández, Daniel Garijo, Björn Grüning, Marco La Rosa, Simone Leo, Eoghan Ó Carragáin, Marc Portier, Ana Trisovic, RO-Crate Community, Paul Groth, Carole Goble(2022):  
**포장 연구 유물 RO-Crate와 함께**.  
*데이터 과학* **5** (2)  
[https://doi.org/10.3233/DS-210053](https://doi.org/10.3233/DS-210053)

#### RO-Crate 사양(모든 버전)을 인용하십시오.

Peter Sefton, Eoghan Ó Carragáin, Stian Soiland-Reyes, Oscar Corcho, Daniel Garijo, Raul Palma, Frederik Coppens, Carole Goble, José María Fernández, Kyle Chard, Jose Manuel Gomez-Perez, Michael R Crusoe, Ignacio Eguinoa, Nick Juty, Kristi Holmes, Jason A. Clark, Salvador Capella-Gutierrez, Alasdair JG Gray, Stuart Owen, Alan R Williams, Giacomo Tartari, Finn Bacall, Thomas Thelen, Hervé Ménager, Laura Rodríguez Navas, Paul Walk, Brandon Whitehead, Mark Wilkinson, Paul Groth, Erich Bremer, LJ Garcia Castro, Karl Sebby, Alexander Kanitz, Ana Trisovic, Gavin Kennedy, Mark Graves, Jasper 코호스트, 시몬 레오, 마크 포르티어(2020):  
**RO-Crate 메타데이터 사양**  
*Researchobject.org / Zenodo*  
[https://doi.org/10.5281/zenodo.3406497](https://doi.org/10.5281/zenodo.3406497)

[RO-Crate 사양의](https://www.researchobject.org/ro-crate/specification) 특정 버전을 인용하려면 내장된 " *이 버전 인용* " DOI를 참조하십시오.
