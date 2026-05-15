---
title: "Anthropic's Claude Mythos isn't a sentient super-hacker, it's a sales pitch — claims of 'thousands' of severe zero-days rely on just 198 manual reviews"
source: "https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropics-claude-mythos-isnt-a-sentient-super-hacker-its-a-sales-pitch-claims-of-thousands-of-severe-zero-days-rely-on-just-198-manual-reviews"
author:
  - "[[Jon Martindale]]"
published: 2026-04-10
created: 2026-04-12
description: "Many of the \"thousands\" of bugs and vulnerabilities it found are in older software, or are impossible to exploit."
tags:
  - "clippings"
---
[![](https://cdn.mos.cms.futurecdn.net/flexiimages/4149vle0tf1752093685.svg)](https://www.tomshardware.com/premium)

![Dario Amodei looking a little menacing.](https://cdn.mos.cms.futurecdn.net/LzLSoTfRnpwCpMdewqmutZ-1600-80.jpg.webp)

(Image credit: Ludovic MARIN / AFP via Getty Images)

Claude AI developer Anthropic [made headlines this week](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropics-latest-ai-model-identifies-thousands-of-zero-day-vulnerabilities-in-every-major-operating-system-and-every-major-web-browser-claude-mythos-preview-sparks-race-to-fix-critical-bugs-some-unpatched-for-decades) for its development and internal release of a new model known as Mythos. This mythically-named AI model allegedly has incredible capabilities, including finding bugs and vulnerabilities in various apps, operating systems, browsers, and legacy software. Enough that Anthropic was concerned about its general release and will instead keep it internal and focus on working with major tech companies and governments to prevent this tool from falling into the wrong hands, where it could cause untold mayhem.

That's the pitch in Anthropic's blog and [verbose 250-page report](https://www-cdn.anthropic.com/8b8380204f74670be75e81c820ca8dda846ab289.pdf) on the model — which includes over 20 pages of Anthropic staff waxing lyrically about their novel impressions of the new model and its "fondness for particular philosophers."

Article continues below

Latest Videos From Tom's Hardware

## Exploit hunting

The big ["Project Glasswing" blog post](https://www.anthropic.com/glasswing) and report on Mythos from Anthropic claimed its new model had found "thousands of high-severity vulnerabilities," which is indeed big news. Those bugs were said to be across every major operating system and web browser, and in some cases have been there for decades.

But it's not clear how realistic these vulnerabilities are, how many of them aren't actually exploitable, or even how problematic they are.

In the case of the FFMPeg vulnerability that has existed for 16 years, [Anthropic's own analysis](https://red.anthropic.com/2026/mythos-preview/) of the release suggested "This bug ultimately is not a critical severity vulnerability," and "would be challenging to turn this vulnerability into a functioning exploit."

Mythos reportedly found several potential exploits in the Linux kernel, but was unable to exploit any of them because of Linux's defense-in-depth [security](https://www.tomshardware.com/tag/security) systems. A number of the exploits had also been [recently patched, too,](https://github.com/torvalds/linux/commit/e2f78c7ec1655fedd945366151ba54fcb9580508) making it rather confusing why they were included in the total.

In its OSS-Fuzz-style testing of over 7,000 open source software stacks, Mythos found crashable exploits in around 600 examples and 10 severe vulnerabilities. That's a lot more than its previous Claude models, but not exactly thousands of devastating exploits.

Under the subheading, "and several thousand more," Anthropic also states that it can't actually confirm that all of the thousands of bugs Mythos claims to have found are actually critical security vulnerabilities. It's just extrapolated that number from having found in around 90% of the "198 manually reviewed vulnerability reports, \[Anthropic's\] expert contractors agreed with Claude’s severity assessment exactly."

It also can't discuss all the bugs in detail for security reasons. While that does make some measure of sense, it also makes it hard to accurately gauge the relative importance of its findings.

## You're not worth it

![Triangle as a weighing scale](https://cdn.mos.cms.futurecdn.net/uDe5V9DftAJYbZae7cTwQU-1200-80.png.webp)

(Image credit: Anthropic)

As much as Anthropic claims it's keeping Mythos behind arbitrarily closed doors over what it claims are security fears, this isn't exactly out of character for the company. Its Claude tool was famously the [first large language model AI to be given security clearance](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropic-sues-pentagon-over-ai-blacklisting) for use by the U.S. government and American military, and that only changed after it drew a line in the sand on being used for mass surveillance or fully autonomous targeting.

Anthropic might have a consumer-facing product in its coding tools, but it is very keen on selling its services to big companies and government entities. If it can sell Mythos to large firms or any number of governments around the world, why would it need to sell it to consumers?

## Hot air, or real worries?

As much as Anthropic might sell itself as the security and safety-conscious AI developer, it has also repeatedly leveraged that public image as part of its sales pitch. Over the past couple of years, Anthropic has published several alarming papers, reports, and studies, many of them claiming that AI is dangerous and needs strict control and monitoring.

It claimed to have [foiled the first AI hacking attempts in the latter months of last year,](https://www.tomshardware.com/tech-industry/cyber-security/anthropic-says-it-has-foiled-the-first-ever-ai-orchestrated-cyber-attack-originating-from-china-company-alleges-attack-was-run-by-chinese-state-sponsored-group) and it was Anthropic CEO Dario Amodei who said in May that year that AI could [replace up to 20% of white-collar workers.](https://www.tomshardware.com/tech-industry/artificial-intelligence/anthropic-ceo-says-ai-could-cause-up-to-20-percent-unemployment-within-five-years-wipe-out-half-of-all-entry-level-white-collar-jobs) He doubled down on that claim in 2026, saying that [AI taking over jobs would overwhelm our ability to adapt](https://www.windowscentral.com/artificial-intelligence/anthropic-ceo-fears-ai-development-is-exponentially-compounding-fearing-it-could-erase-entry-level-jobs-it-will-overwhelm-our-ability-to-adapt).

Nvidia CEO Jensen Huang [called out this fear-mongering in mid-2025](https://www.tomshardware.com/tech-industry/artificial-intelligence/nvidia-ceo-slams-anthropic-chief-over-claims-of-job-eliminations-says-many-jobs-are-going-to-be-created), claiming Anthropic wanted to position itself as the only company that could responsibly develop AI.

This isn't even anything new in AI marketing. [OpenAI was doing it in 2019](https://techcrunch.com/2019/02/17/openai-text-generator-dangerous/), before ChatGPT was even a twinkle in Sam Altman's eye, and Dario Amodei hadn't yet left OpenAI.

Speaking of OpenAI, days after Anthropic's Mythos reveal, it was also working on an advanced cybersecurity AI model. It too will limit the rollout of this powerful and concerning tool, [*Axios* reports.](https://www.axios.com/2026/04/09/openai-new-model-cyber-mythos-anthopic) As models develop, they reach a similar level of capability, so it's no surprise that OpenAI could have a Mythos-level or adjacent model waiting in the wings.

## Sentience and security

AI isn't conscious. It's more like a [Chinese room from the John Searle thought experiment](https://en.wikipedia.org/wiki/Chinese_room), but even then, it has no understanding. It doesn't truly remember anything in a biological sense; it can just recall contexts and weight its responses differently based on previous inputs. So, sentience and consciousness claims may yet be unfounded.

AI models may well be good at discovering vulnerabilities, and if Anthropic and other software developers can find and patch bugs using AI, that's good news, not scary news.

As [Red Hat's analysis of this release shows](https://www.redhat.com/en/blog/navigating-mythos-haunted-world-platform-security), many of the bugs are functionality flaws and aren't a security concern. But even if hackers can leverage AI tools in the future to find exploits and then exploit them, that's only a concern if the security industry doesn't respond. Which it will.

So, sure, AI is impacting security. It already was. And it will continue to do so. While Mythos might be capable in ways that previous models were not, this appears to be part-marketing, part-truth. For the rest of us, this is just another AI model. For Anthropic, it's an opportunity to gain mindshare and potentially lucrative contracts.

Unlock this article with a Tom’s Hardware Premium subscription