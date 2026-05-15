---
title: "MIT, 메모리 병목 해결 기술 공개…\"KV 캐시 50배 압축\""
source: "https://www.aitimes.com/news/articleView.html?idxno=207727"
author:
  - "[[박찬 기자]]"
published: 2026-03-09
created: 2026-04-13
description: "MIT가 대형언어모델(LLM)이 긴 문서나 장기 작업을 처리할 때 발생하는 메모리 병목 문제를 해결할 기술을 선보였다. MIT 연구진은 모델의 핵심 작업 메모리인"
tags:
  - "clippings"
---
![(사진=엔비디아)](https://cdn.aitimes.com/news/photo/202603/207727_209851_2811.jpg)

(사진=엔비디아)

MIT가 대형언어모델(LLM)이 긴 문서나 장기 작업을 처리할 때 발생하는 메모리 병목 문제를 해결할 기술을 선보였다.

MIT 연구진은 모델의 핵심 작업 메모리인 KV 캐시를 최대 50배까지 압축하면서도 성능 저하를 거의 발생시키지 않는 압축 기법 ‘ [어텐션 매칭(Attention Matching)](https://arxiv.org/pdf/2602.16284) ’을 온라인 아카이브를 통해 공개했다.

LLM은 답변을 생성할 때 이전에 처리한 모든 토큰 정보를 저장해 두고 이를 참고한다. 이때 저장되는 키(Key)와 값(Value) 벡터의 집합이 바로 KV 캐시다.

이 구조는 모델이 이전 대화나 문서 내용을 다시 계산하지 않고도 빠르게 추론하도록 돕지만, 컨텍스트 길이가 길어질수록 메모리 사용량이 급격히 증가한다는 문제가 있다.

특히 기업 환경에서는 특정 작업을 수행하는 과정에서 KV 캐시의 크기가 급격히 증가하는 경우가 많다. 대규모 법률 계약서를 분석하거나, 장기간에 걸친 고객 상담 대화를 유지하는 상황, 또는 자율 코딩 에이전트를 실행하는 과정에서 이러한 현상이 두드러진다.

이러한 작업들은 긴 문맥을 지속적으로 처리해야 하기 때문에, 단일 사용자 요청만으로도 수 기가바이트(GB) 규모의 메모리가 필요해질 수 있다.

현재 업계는 KV 캐시로 인한 메모리 부담을 줄이기 위해 다양한 방법을 시도 중이다. 대표적으로 중요도가 낮은 토큰을 삭제하거나, 의미가 비슷한 토큰을 병합하는 방식이 사용된다. 또 오래된 컨텍스트를 제거하거나, 기존 텍스트를 요약한 뒤 그 요약본으로 메모리를 대체하는 방법도 활용되고 있다.

그러나 이러한 방식들은 압축률이 높아질수록 모델 성능이 급격히 떨어지는 문제가 있다. 특히 널리 사용되는 컨텍스트 요약 방식은 중요한 정보가 요약 과정에서 사라질 가능성이 있어, 실제 업무 환경에서는 성능 저하로 이어질 수 있다는 지적이 나온다.

MIT 연구진이 제안한 어텐션 매칭은 토큰 자체를 단순히 요약하는 대신, 모델의 주의(attention) 동작을 유지하는 방식으로 메모리를 압축하는 기술이다. 즉 텍스트를 줄이는 것이 아니라 모델이 정보를 활용하는 방식 자체를 보존하는 데 초점을 맞춘 접근법이다.

이 기술은 압축 과정에서 두가지 핵심 특성을 유지하도록 설계됐다. 첫번째는 어텐션 아웃풋(Attention Output)으로, 모델이 메모리에서 실제로 추출해 사용하는 정보다. 두번째는 어텐션 매스(Attention Mass)로, 각 토큰이 모델의 판단 과정에서 차지하는 상대적 중요도를 의미한다.

연구진에 따르면, 압축된 메모리가 이 두가지 특성을 동일하게 유지할 수 있다면 메모리 크기가 줄어들더라도 모델은 원래 메모리를 사용할 때와 거의 동일한 방식으로 작동할 수 있다. 이는 기존 요약 기반 방식에서 발생하던 정보 손실 문제를 줄일 방법으로 평가된다.

연구진은 이를 위해 모델이 문서를 이해할 때 내부적으로 어떤 정보를 찾게 될지 미리 예측하는 ‘참조 쿼리(reference queries)’를 만들었다. 그리고 이 쿼리를 기준으로 문서에서 꼭 필요한 정보만 남기는 방식의 압축 구조를 설계했다.

또 일반적인 GPU 기반 학습이나 복잡한 최적화 과정을 사용하지 않고, 최소제곱법(least squares) 같은 대수적 계산 방식을 활용했다. 덕분에 별도의 긴 학습 과정 없이도 비교적 빠르게 메모리를 압축할 수 있다는 설명이다.

![큐원3-4B에 QuALITY 학습을 통한 정확도 대비 압축 시간의 트레이드오프 (사진=arXiv)](https://cdn.aitimes.com/news/photo/202603/207727_209852_2853.png)

큐원3-4B에 QuALITY 학습을 통한 정확도 대비 압축 시간의 트레이드오프 (사진=arXiv)

연구진은 제안한 방법의 성능을 검증하기 위해 오픈소스 모델인 '라마 3.1'과 '큐원-3'을 활용해 실험을 진행했다.

실험에는 두가지 데이터셋이 사용됐다. 하나는 5000~8000단어 길이의 장문 문서로 구성된 'QuALITY'이며, 다른 하나는 약 6만 토큰 규모의 의료 기록 데이터를 포함한 '롱헬스(LongHealth)'다.

그 결과, 어텐션 매칭 기법은 몇초 만에 KV 캐시를 최대 50배까지 압축하면서도 기존과 유사한 정확도를 유지하는 것으로 나타났다. 반면, 기존의 고급 압축 기술인 카트리지(Cartridges) 방식은 같은 수준의 성능을 얻기 위해 수시간에 걸친 GPU 최적화 작업이 필요한 것으로 확인됐다.

특히 정보 밀도가 높은 의료 기록 데이터에서는 기존 방법의 한계가 명확하게 드러났다.

연구진이 텍스트 요약 방식으로 컨텍스트를 줄였을 때 모델 정확도는 ‘컨텍스트 없음’ 수준까지 떨어졌다. 즉 모델이 문서를 읽지 않은 것과 비슷한 성능을 보였다. 하지만 어텐션 매칭은 이러한 상황에서도 높은 정확도를 유지했다.

연구진은 추가 실험에서 요약과 어텐션 매칭을 결합하는 방법도 테스트했다. 이 방식은 최대 200배 압축을 달성하면서도 기존 요약 방식과 동일한 정확도를 유지했다.

또 다른 실험에서는 수학 추론 테스트 중 메모리가 가득 차면 즉시 KV 캐시를 50% 압축하고 계산을 계속 진행하도록 설정했다. 모델은 여섯번 연속 메모리를 압축하면서도 문제를 정상적으로 해결했으며, 무제한 메모리를 가진 모델과 동일한 성능을 보였다.

하지만 이 기술은 바로 기업 환경에서 적용될 수 있는 것이 아니다. 어텐션 매칭은 모델 내부 구조 접근이 필요하기 때문에 모델 가중치를 공개한 오픈 모델에서만 적용 가능하다. 따라서 API 기반 폐쇄형 모델에서는 직접 구현하기 어렵다.

또 기존 AI 추론 시스템에는 프리픽스 캐싱(prefix caching)이나 가변 길이 메모리 패킹(variable-length memory packing)과 같은 다양한 최적화 기술이 이미 적용돼 있다. 따라서 새로운 메모리 압축 기술을 실제 시스템에 도입하려면 이러한 기존 구조와의 호환성을 맞추기 위한 추가적인 엔지니어링 작업이 필요하다.

연구진은 앞으로 AI 산업에서 메모리 압축 기술이 모델 제공자의 기본 기능으로 포함될 가능성이 높다고 전망했다.

박찬 기자 cpark@aitimes.com

관련기사

- [엔비디아, 추론 메모리 사용 8배까지 줄이는 기술 공개](https://www.aitimes.com/news/articleView.html?idxno=206868)
- [딥시크, MoE 모델 효율성 극대화하는 새로운 '메모리' 기능 공개](https://www.aitimes.com/news/articleView.html?idxno=205558)
- [애플, 장시간 채팅 메모리 6배 줄이는 기술 공개..."인간처럼 대화 기억"](https://www.aitimes.com/news/articleView.html?idxno=202708)
- [구글, AI 메모리 6배로 줄여 비용 50% 절감하는 '터보퀀트' 기술 공개](https://www.aitimes.com/news/articleView.html?idxno=208377)
- [엔비디아도 'KV 캐시' 해결... '트라이어텐션'으로 메모리 10배 절감](https://www.aitimes.com/news/articleView.html?idxno=208924)

![박찬 기자의 프로필 이미지](https://cdn.aitimes.com/news/photo/member/cpark_20220210101322.png)

[박찬 기자](https://www.aitimes.com/news/articleList.html?sc_area=I&sc_word=cpark&view_type=sm) [cpark@aitimes.com](mailto:cpark@aitimes.com)

[다른기사 보기](https://www.aitimes.com/news/articleList.html?sc_area=I&sc_word=cpark&view_type=sm)

키워드

[#MIT](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=MIT&view_type=sm) [#메모리 병목](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EB%A9%94%EB%AA%A8%EB%A6%AC%20%EB%B3%91%EB%AA%A9&view_type=sm) [#KV 캐시](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=KV%20%EC%BA%90%EC%8B%9C&view_type=sm) [#압축 기법](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EC%95%95%EC%B6%95%20%EA%B8%B0%EB%B2%95&view_type=sm) [#어텐션 매칭](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EC%96%B4%ED%85%90%EC%85%98%20%EB%A7%A4%EC%B9%AD&view_type=sm) [#컨텍스트 길이](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EC%BB%A8%ED%85%8D%EC%8A%A4%ED%8A%B8%20%EA%B8%B8%EC%9D%B4&view_type=sm) [#메모리 급증](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EB%A9%94%EB%AA%A8%EB%A6%AC%20%EA%B8%89%EC%A6%9D&view_type=sm) [#인공지능](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5&view_type=sm) [#AI](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=AI&view_type=sm)

저작권자 © AI타임스 무단전재 및 재배포, AI학습 및 활용 금지