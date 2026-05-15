---
title: "An Open-Ended Embodied Agent with Large Language Models"
source: "https://voyager.minedojo.org/"
author:
published: "unknown"
created: "2026-04-13"
description:
tags:
  - "clippings"
---

<video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/diamond.mp4" type="video/mp4"> </video><video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/cactus.mp4" type="video/mp4"> </video><video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/base.mp4" type="video/mp4"> </video><video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/enderman.mp4" type="video/mp4"> </video><video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/house.mp4" type="video/mp4"> </video><video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/gold.mp4" type="video/mp4"> </video><video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/portal.mp4" type="video/mp4"> </video><video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/pig.mp4" type="video/mp4"> </video><video controls="" width="100%"><source src="https://voyager.minedojo.org/assets/videos/gallery/fish.mp4" type="video/mp4"></video>

## Abstract

We introduce Voyager, the first LLM-powered embodied lifelong learning agent in Minecraft that continuously explores the world, acquires diverse skills, and makes novel discoveries without human intervention. Voyager consists of three key components: 1) an automatic curriculum that maximizes exploration, 2) an ever-growing skill library of executable code for storing and retrieving complex behaviors, and 3) a new iterative prompting mechanism that incorporates environment feedback, execution errors, and self-verification for program improvement. Voyager interacts with GPT-4 via blackbox queries, which bypasses the need for model parameter fine-tuning. The skills developed by Voyager are temporally extended, interpretable, and compositional, which compounds the agent's abilities rapidly and alleviates catastrophic forgetting. Empirically, Voyager shows strong in-context lifelong learning capability and exhibits exceptional proficiency in playing Minecraft. It obtains 3.3x more unique items, travels 2.3x longer distances, and unlocks key tech tree milestones up to 15.3x faster than prior SOTA. Voyager is able to utilize the learned skill library in a new Minecraft world to solve novel tasks from scratch, while other techniques struggle to generalize.

![](https://voyager.minedojo.org/assets/images/exploration_performance.png)  
Voyager discovers new Minecraft items and skills continually by self-driven exploration, significantly outperforming the baselines.

## Introduction

Building generally capable embodied agents that continuously explore, plan, and develop new skills in open-ended worlds is a grand challenge for the AI community. Classical approaches employ reinforcement learning (RL) and imitation learning that operate on primitive actions, which could be challenging for systematic exploration, interpretability, and generalization. Recent advances in large language model (LLM) based agents harness the world knowledge encapsulated in pre-trained LLMs to generate consistent action plans or executable policies. They are applied to embodied tasks like games and robotics, as well as NLP tasks without embodiment. However, these agents are not lifelong learners that can progressively acquire, update, accumulate, and transfer knowledge over extended time spans.  
  
Let us consider Minecraft as an example. Unlike most other games studied in AI, Minecraft does not impose a predefined end goal or a fixed storyline but rather provides a unique playground with endless possibilities. An effective lifelong learning agent should have similar capabilities as human players: (1) **propose suitable tasks** based on its current skill level and world state, e.g., learn to harvest sand and cactus before iron if it finds itself in a desert rather than a forest; (2) **refine skills** based on environment feedback and **commit mastered skills to memory** for future reuse in similar situations (e.g. fighting zombies is similar to fighting spiders); (3) **continually explore the world** and seek out new tasks in a self-driven manner.

  

## Voyager Components

We introduce Voyager, the first *LLM-powered embodied lifelong learning agent* to drive exploration, master a wide range of skills, and make new discoveries continually without human intervention in Minecraft. Voyager is made possible through three key modules: 1) an **automatic curriculum** that maximizes exploration; 2) a **skill library** for storing and retrieving complex behaviors; and 3) a new **iterative prompting mechanism** that generates executable code for embodied control. We opt to use code as the action space instead of low-level motor commands because programs can naturally represent temporally extended and compositional actions, which are essential for many long-horizon tasks in Minecraft. Voyager interacts with a blackbox LLM (GPT-4) through prompting and in-context learning. Our approach bypasses the need for model parameter access and explicit gradient-based training or finetuning.

  
  
![](https://voyager.minedojo.org/assets/images/components.png) Voyager consists of three key components: an automatic curriculum for open-ended exploration, a skill library for increasingly complex behaviors, and an iterative prompting mechanism that uses code as action space.  
  

### Automatic Curriculum

![](https://voyager.minedojo.org/assets/images/curriculum.png)  

Automatic curriculum. The automatic curriculum takes into account the exploration progress and the agent's state to maximize exploration. The curriculum is generated by GPT-4 based on the overarching goal of "discovering as many diverse things as possible". This approach can be perceived as an in-context form of *novelty search*.

  
  

### Skill Library

![](https://voyager.minedojo.org/assets/images/skill_library.png)  

Skill library. **Top: Adding a new skill.** Each skill is indexed by the embedding of its description, which can be retrieved in similar situations in the future. **Bottom: Skill retrieval.** When faced with a new task proposed by the automatic curriculum, we perform querying to identify the top-5 relevant skills. Complex skills can be synthesized by composing simpler programs, which compounds Voyager's capabilities rapidly over time and alleviates catastrophic forgetting.

  
  

### Iterative Prompting Mechanism

![](https://voyager.minedojo.org/assets/images/feedback.png)  

Left: Environment feedback. GPT-4 realizes it needs 2 more planks before crafting sticks. Right: Execution error. GPT-4 realizes it should craft a wooden axe instead of an acacia axe since there is no acacia axe in Minecraft.

  
  
![](https://voyager.minedojo.org/assets/images/self_verification.png)  
Self-verification. By providing the agent's current state and the task to GPT-4, we ask it to act as a critic and inform us whether the program achieves the task. In addition, if the task fails, it provides a critique by suggesting how to complete the task.

## Experiments

We systematically evaluate Voyager and baselines on their exploration performance, tech tree mastery, map coverage, and zero-shot generalization capability to novel tasks in a new world.

  
  

### Significantly Better Exploration

As shown in the first figure, Voyager's superiority is evident in its ability to consistently make new strides, discovering 63 unique items within 160 prompting iterations, 3.3x many novel items compared to its counterparts. On the other hand, AutoGPT lags considerably in discovering new items, while ReAct and Reflexion struggle to make significant progress.  
  

### Tech Tree Mastery

![](https://voyager.minedojo.org/assets/images/tech_tree.png)

Tech tree mastery. The Minecraft tech tree tests the agent's ability to craft and use a hierarchy of tools. Progressing through this tree (wooden tool → stone tool → iron tool → diamond tool) requires the agent to master systematic and compositional skills. In this table, fractions indicate the number of successful trials out of three total runs. **Numbers are prompting iterations averaged over three trials. The fewer the iterations, the more efficient the method.** Compared with baselines, Voyager unlocks the wooden level 15.3x faster (in terms of the prompting iterations), the stone level 8.5x faster, the iron level 6.4x faster, and Voyager is the only one to unlock the diamond level of the tech tree

  
  

### Extensive Map Traversal

![](https://voyager.minedojo.org/assets/images/map.png)  

Map coverage: Two bird's eye views of Minecraft maps. Voyager is able to navigate distances 2.3x longer compared to baselines by traversing a variety of terrains, while the baseline agents often find themselves confined to local areas, which significantly hampers their capacity to discover new knowledge.

  
  

### Efficient Zero-Shot Generalization to Unseen Tasks

![](https://voyager.minedojo.org/assets/images/zero_shot_table.png) ![](https://voyager.minedojo.org/assets/images/zero_shot.png)  

Zero-shot generalization to unseen tasks. We clear the agent's inventory, reset it to a newly instantiated world, and test it with unseen tasks. In the table above, fractions indicate the number of successful trials out of three total runs. **Numbers are prompting iterations averaged over three trials. The fewer the iterations, the more efficient the method.** Voyager can consistently solve all the tasks, while baselines cannot solve any task within 50 prompting iterations. What's interesting to note is that our skill library constructed from lifelong learning not only enhances Voyager's performance but also gives a boost to AutoGPT. This demonstrates that the skill library serves as a versatile tool that can be readily employed by other methods, effectively acting as a plug-and-play asset to enhance performance.

  
  

### Ablation Studies

![](https://voyager.minedojo.org/assets/images/ablation.png)  

Ablation studies. GPT-3.5 means replacing GPT-4 with GPT-3.5 for code generation. Voyager outperforms all the alternatives, demonstrating the critical role of each component. In addition, GPT-4 significantly outperforms GPT-3.5 in code generation.

## Conclusion

In this work, we introduce Voyager, the first LLM-powered embodied lifelong learning agent, which leverages GPT-4 to explore the world continuously, develop increasingly sophisticated skills, and make new discoveries consistently without human intervention. Voyager exhibits superior performance in discovering novel items, unlocking the Minecraft tech tree, traversing diverse terrains, and applying its learned skill library to unseen tasks in a newly instantiated world. Voyager serves as a starting point to develop powerful generalist agents without tuning the model parameters.

## Media Coverage

"They Plugged GPT-4 Into Minecraft—and Unearthed New Potential for AI. The bot plays the video game by tapping the text generator to pick up new skills, suggesting that the tech behind ChatGPT could automate many workplace tasks." - Will Knight, [WIRED](https://www.wired.com/story/fast-forward-gpt-4-minecraft-chatgpt/)  
  
"The Voyager project shows, however, that by pairing GPT-4’s abilities with agent software that stores sequences that work and remembers what does not, developers can achieve stunning results." - John Koetsier, [Forbes](https://www.forbes.com/sites/johnkoetsier/2023/05/29/gpt-4-is-pretty-good-at-minecraft/?sh=1cf7262e2db6)  
  
"Voyager, the GTP-4 bot that plays Minecraft autonomously and better than anyone else" - [Ruetir](https://www.ruetir.com/2023/06/voyager-the-gtp-4-bot-that-plays-minecraft-autonomously-and-better-than-anyone-else/)  
  
"This AI used GPT-4 to become an expert Minecraft player" - Devin Coldewey, [TechCrunch](https://techcrunch.com/2023/06/02/this-ai-used-gpt-4-to-become-an-expert-minecraft-player/)  
  
Coverage Index: [\[Atmarkit\]](https://atmarkit.itmedia.co.jp/ait/articles/2305/31/news053.html) [\[Career Engine\]](https://posts.careerengine.us/p/64748e293d569e4bb807a367) [\[Crast.net\]](https://crast.net/344674/this-is-what-happens-when-you-teach-an-ai-to-play-minecraft-gpt-4-has-turned-out-to-be-quite-the-pro/) [\[Daily Top Feeds\]](https://dailytopfeeds.com/they-plugged-gpt-4-into-minecraft-and-unearthed-new-potential-for-ai/) [\[Entrepreneur en Espanol\]](https://www.entrepreneur.com/es/noticias/la-inteligencia-artificial-que-demostro-su-potencial/453264) [\[Finance Jxyuging\]](http://finance.jxyuging.com/gd/2023/0529/282042.html) [\[Forbes\]](https://www.forbes.com/sites/johnkoetsier/2023/05/29/gpt-4-is-pretty-good-at-minecraft/?sh=1cf7262e2db6) [\[Forbes Argentina\]](https://www.forbesargentina.com/innovacion/asi-funciona-voyager-agente-software-juega-minecraft-informacion-e-inteligencia-proporcionadas-gpt-4-n34583) [\[Gaming Deputy\]](https://www.gamingdeputy.com/nvidias-ai-agent-is-connected-to-gpt-4-outperforms-autogpt-and-writes-code-independently-to-dominate-my-world-without-human-intervention/) [\[Gearrice\]](https://www.gearrice.com/update/gpt-4s-ai-is-exceptional-playing-minecraft/) [\[Haberik\]](https://haberik.com/bir-nvidia-ekibi-tarafinca-gpt-4-kullanilarak-olusturulan-3-kattan-fazla-unsur-elde-eden-ve-oteki-ai-botlarindan-15-kat-daha-suratli-araclar-olusturan-voyagera-bir-bakis-will-knight-wired/) [\[Head Topics\]](https://headtopics.com/jp/125101245212531764898-39558875) [\[InfoQ\]](https://www.infoq.com/news/2023/05/minecraft-voyager-llm-agent/) [\[ITmedia News\]](https://news.line.me/detail/oa-rp23831/i66io34cqk2f?mediadetail=1) [\[Mark Tech Post\]](https://www.marktechpost.com/2023/05/31/nvidia-announced-real-time-ai-npcs-in-video-games/) [\[Medium\]](https://medium.com/@mikeyoung_97230/voyager-the-ai-gamer-thats-taking-minecraft-to-the-next-level-93449ff27537) [\[MSN\]](https://www.msn.com/de-de/nachrichten/digital/wie-ai-technologie-die-gaming-branche-f%C3%BCr-immer-ver%C3%A4ndern-wird/ar-AA1c0c0e) [\[Note\]](https://note.com/te_ftef/n/ne7ec02a3b209) [\[Noticias de Hoy\]](https://noticiasdehoy.com.mx/la-ia-de-gpt-4-es-excepcional-jugando-minecraft/) [\[Ruetir\]](https://www.ruetir.com/2023/06/voyager-the-gtp-4-bot-that-plays-minecraft-autonomously-and-better-than-anyone-else/) [\[Stock HK\]](https://www.stock-hk.com/news/232925) [\[Tech Tribune France\]](https://fr.techtribune.net/jeux-videos/minecraft/minecraft-accueille-son-premier-agent-propulse-par-llm/725434/) [\[TechCrunch\]](https://techcrunch.com/2023/06/02/this-ai-used-gpt-4-to-become-an-expert-minecraft-player/) [\[TechBeezer\]](https://techbeezer.com/they-connected-gpt-4-to-minecraft-and-revealed-new-potential-for-artificial-intelligence/) [\[Toutiao\]](https://www.toutiao.com/article/7238593146928513569/?wid=1686469229935) [\[US Times Post\]](https://ustimespost.com/they-plugged-gpt-4-into-minecraft-and-unearthed-new-potential-for-ai/) [\[VN Explorer\]](https://vnexplorer.net/nie-ma-sie-z-czego-smiac-naukowcy-nauczyli-sztuczna-inteligencje-grac-w-minecraft-s2612596.html) [\[WIRED\]](https://www.wired.com/story/fast-forward-gpt-4-minecraft-chatgpt/) [\[Zaker\]](http://www.myzaker.com/article/647460778e9f09203d3afe20)
