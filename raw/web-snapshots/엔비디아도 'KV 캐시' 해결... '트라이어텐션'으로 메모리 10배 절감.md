---
title: "엔비디아도 'KV 캐시' 해결... '트라이어텐션'으로 메모리 10배 절감"
source: "https://www.aitimes.com/news/articleView.html?idxno=208924"
author:
  - "[[박찬 기자]]"
published: 2026-04-08
created: 2026-04-12
description: "AI 성능 경쟁의 중심축이 더 큰 모델에서 더 효율적인 모델로 이동하는 가운데, 엔비디아가 메모리 병목을 획기적으로 줄이는 새로운 기술을 공개했다. 특히, 얼마"
tags:
  - "clippings"
---
![(사진=깃허브)](https://cdn.aitimes.com/news/photo/202604/208924_211313_446.png)

(사진=깃허브)

AI 성능 경쟁의 중심축이 더 큰 모델에서 더 효율적인 모델로 이동하는 가운데, 엔비디아가 메모리 병목을 획기적으로 줄이는 새로운 기술을 공개했다. 특히, 얼마 전 구글이 공개해 화제가 됐던 '터보퀀트(TurboQuant)'의 메모리 6분의 1 압축보다 더 큰, 메모리 사용량 10.7배 감소라는 수치를 제시했다.

엔비디아와 MIT 연구진은 6일(현지시간) 대형언어모델(LLM)의 핵심 한계로 지적돼 온 ‘KV 캐시(KV cache)’ 문제를 근본적으로 개선하는 접근법 ‘ [트라이어텐션(TriAttention)](https://arxiv.org/pdf/2604.04921) ’을 온라인 아카이브를 통해 공개했다.

KV 캐시는 AI가 이전 대화와 데이터를 기억하기 위해 사용하는 메모리 공간으로, 문맥이 길어질수록 사용량이 폭발적으로 증가해 GPU 메모리를 빠르게 소진시키는 병목으로 작용해 왔다. 이로 인해 AI는 긴 문서나 복잡한 추론을 수행하다가 ‘메모리 부족’ 상태에 빠지는 경우가 많았고, 이는 실제 상용화의 가장 큰 물리적 제약 중 하나로 꼽혀왔다.

기존 연구들은 메모리 부담을 줄이기 위해 중요하지 않은 정보를 제거하는 압축 기법을 제시해 왔지만, 성능 저하라는 치명적인 문제가 있었다. 특히 RoPE(위치 인코딩)가 적용된 이후에는 데이터가 이미 뒤섞인 상태가 되는데, 이 상태(Post-RoPE)에서 중요도를 판단하다 보니 필요한 정보까지 함께 지워지는 문제가 생겼다. 이는 복잡한 수학 문제나 장기 추론에서 AI 성능이 급격히 떨어지는 원인이었다.

트라이어텐션은 이 문제를 해결하기 위해 데이터가 뒤섞인 상태(Post-RoPE)에서도 수학적으로 그 패턴을 역추적할 수 있다는 점에 주목했다. 기존 연구들은 위치 정보(RoPE)가 입혀지면 데이터 상관관계가 복잡해져 핵심 정보를 골라내기 어렵다고 보았으나, 엔비디아 연구진은 수학적 필터(TriA-Filter)를 통해 뒤섞인 데이터 속에서도 'Pre-RoPE' 단계의 중요한 특징을 정확히 식별해 낼 수 있음을 증명했다.

![트라이어텐션 개요. 먼저 오프라인 캘리브레이션 단계에서 Q 분포의 중심을 계산한다. 이후 추론 과정에서는 Strig 기반 요소와 노름(norm) 기반 요소를 결합해 기존 어텐션 점수를 산출한다. 가장 오른쪽 패널은 가지치기(pruning) 이후의 어텐션 맵을 보여준다. 일부 헤드에서 거리 선호(distance preference)가 나타나는 것을 관찰했는데, 이는 멀리 떨어진 키들이 더 높은 어텐션을 받는 경향을 의미한다. 그러나 동시에, 쿼리로부터 멀리 떨어져 있음에도 노름 값이 낮아 거의 주목받지 못하는 키들도 존재한다는 점을 확인했다. 이러한 관찰은 두 가지 점수 계산 요소의 필요성을 보여준다. Strig는 거리 선호를 포착하고, 노름 기반 점수는 노름이 낮은 키를 식별한다. 이 예시에서 Strig는 가까운 키들에 낮은 점수를 부여하는 데 성공하며, 노름 기반 점수는 가장 왼쪽에 있는 최초 토큰이 최대 거리에도 불구하고 노름이 낮아 중요하지 않음을 식별한다. 이 두 요소를 결합함으로써 모델은 실제로 주목되지 않을 토큰을 정확하게 찾아내고 이를 제거할 수 있다.  (사진=아카이브)](https://cdn.aitimes.com/news/photo/202604/208924_211254_2647.png)

트라이어텐션 개요. 먼저 오프라인 캘리브레이션 단계에서 Q 분포의 중심을 계산한다. 이후 추론 과정에서는 Strig 기반 요소와 노름(norm) 기반 요소를 결합해 기존 어텐션 점수를 산출한다. 가장 오른쪽 패널은 가지치기(pruning) 이후의 어텐션 맵을 보여준다. (사진=areXiv)

이를 통해 별도의 추가 학습 없이도 불필요한 데이터만 골라 삭제하는 정교한 최적화 로직을 완성했다.

핵심은 삼각함수를 활용한 분석 방식이다. AI가 어떤 위치의 정보를 중요하게 볼지를 ‘거리 패턴’으로 예측해서, 필요한 데이터만 골라 남긴다. 이는 기존처럼 모든 데이터를 하나씩 비교하는 대신 수학적인 필터로 빠르고 효율적으로 걸러내는 방식이다.

![AIME25(Qwen3-8B)에서의 성능 트레이드오프. (A)동일한 정확도(40.8%) 기준에서, TriAttention은 Full Attention 대비 2.5배 더 높은 처리량(throughput)을 달성한다. (B)TriAttention은 Full Attention과 동일한 정확도를 유지하면서 KV 캐시 메모리를 10.7배 줄인다. (사진=arXiv)](https://cdn.aitimes.com/news/photo/202604/208924_211255_2938.png)

AIME25(Qwen3-8B)에서의 성능 트레이드오프. (A)동일한 정확도(40.8%) 기준에서, TriAttention은 Full Attention 대비 2.5배 더 높은 처리량(throughput)을 달성한다. (B)TriAttention은 Full Attention과 동일한 정확도를 유지하면서 KV 캐시 메모리를 10.7배 줄인다. (사진=arXiv)

실험 결과는 인상적이다. 고난도 수학 추론 테스트인 'AIME25'에서 트라이어텐션은 기존 풀 어텐션(Full Attention) 대비 정확도를 유지하면서도 KV 캐시 메모리를 10.7배 줄였다.

또 메모리 절감 대신 속도에 집중할 경우 최대 2.5배 빠른 처리 성능을 기록했다. 이는 단순한 트레이드오프가 아니라, 효율성과 성능을 동시에 확보한 결과로 평가된다.

특히 책 한권 분량인 3만2000 토큰의 초장문 환경에서도 정확도를 유지하며 장기 추론 안정성을 입증했다.

![AIME24 및 AIME25에서의 추론 성능. 모든 방법은 동일한 KV 캐시 예산 조건에서 비교됐으며, 최고 성능은 굵게 표시, 차선 성능은 밑줄로 표시된다. (사진=arXiv)](https://cdn.aitimes.com/news/photo/202604/208924_211256_302.jpg)

AIME24 및 AIME25에서의 추론 성능. 모든 방법은 동일한 KV 캐시 예산 조건에서 비교됐으며, 최고 성능은 굵게 표시, 차선 성능은 밑줄로 표시된다. (사진=arXiv)

이 기술의 파급력은 실사용 환경에서 더욱 크다. 기존에는 320억(32B) 매개변수급 모델을 긴 문맥으로 실행하려면 다수의 GPU가 필요했지만, 트라이어텐션을 적용하면 일반 소비자용 GPU(24GB VRAM 등) 한장으로도 실행 가능해진다.

이는 개인 PC에서도 고성능 AI를 구동할 수 있는 길을 열었다는 의미다. 특히 '오픈클로(OpenClaw)'와 같은 개인용 AI 에이전트나 온디바이스 모델 확산에 중요한 전환점이 될 것으로 보인다. 엔비디아가 이 기술을 강조하는 것도 GPU 한장으로 오픈클로를 구동할 수 있다는 것을 보여주려는 의도다.

이 같은 흐름은 구글의 최근 기술과도 연결된다. 구글의 터보퀀트는 압축 기술을 사용해 KV 캐시 사용량을 6분의 1로 줄이면서도 처리 속도를 최대 8배까지 끌어올리는 성과를 냈다.

물론 두 방식은 다르다. 구글이 데이터를 6분의 1로 압축해 효율을 높였다면, 엔비디아는 수학적 필터로 불필요한 데이터를 10분의 1 넘게 골라내 버리면서도 추론 정확도를 지켜냈다는 것이 핵심이다.

또 KV 캐시 축소가 전체 메모리 사용량 감소로 직결되는 것은 아니다. 예를 들어, 전체 32GB 메모리 중 모델이 18GB, KV 캐시가 12GB, 기타가 2GB를 차지하는 구조라면, KV 캐시를 10분의 1로 줄이더라도 총 메모리는 약 21.2GB 수준으로 감소하는 데 그친다.

결국 핵심은 '메모리 수요가 사라진다'라는 것이 아니다. '같은 VRAM으로 더 긴 문맥과 더 큰 작업을 처리할 수 있다'라는 점이다.

이는 실질적인 AI 활용 범위를 크게 확장하는 요소로 평가된다.

박찬 기자 cpark@aitimes.com

관련기사

- [“구글의 '터보퀀트', 메모리 6분의 1 절감은 과장된 수치일 뿐”](https://www.aitimes.com/news/articleView.html?idxno=208694)
- [MIT, 메모리 병목 해결 기술 공개…"KV 캐시 50배 압축"](https://www.aitimes.com/news/articleView.html?idxno=207727)
- [엔비디아, 추론 메모리 사용 8배까지 줄이는 기술 공개](https://www.aitimes.com/news/articleView.html?idxno=206868)

![박찬 기자의 프로필 이미지](https://cdn.aitimes.com/news/photo/member/cpark_20220210101322.png)

[박찬 기자](https://www.aitimes.com/news/articleList.html?sc_area=I&sc_word=cpark&view_type=sm) [cpark@aitimes.com](mailto:cpark@aitimes.com)

[다른기사 보기](https://www.aitimes.com/news/articleList.html?sc_area=I&sc_word=cpark&view_type=sm)

키워드

[#엔비디아](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EC%97%94%EB%B9%84%EB%94%94%EC%95%84&view_type=sm) [#KV 캐시](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=KV%20%EC%BA%90%EC%8B%9C&view_type=sm) [#메모리 병목](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EB%A9%94%EB%AA%A8%EB%A6%AC%20%EB%B3%91%EB%AA%A9&view_type=sm) [#트라이어텐션](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%ED%8A%B8%EB%9D%BC%EC%9D%B4%EC%96%B4%ED%85%90%EC%85%98&view_type=sm) [#구글](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EA%B5%AC%EA%B8%80&view_type=sm) [#터보퀀트](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%ED%84%B0%EB%B3%B4%ED%80%80%ED%8A%B8&view_type=sm) [#메모리 사용량 감소](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EB%A9%94%EB%AA%A8%EB%A6%AC%20%EC%82%AC%EC%9A%A9%EB%9F%89%20%EA%B0%90%EC%86%8C&view_type=sm) [#인공지능](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5&view_type=sm) [#AI](https://www.aitimes.com/news/articleList.html?sc_area=K&sc_word=AI&view_type=sm)

저작권자 © AI타임스 무단전재 및 재배포, AI학습 및 활용 금지