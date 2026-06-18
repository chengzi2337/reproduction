# IFEval prompt-transfer limit=20 smoke 离线审计

## Overview

- status: `completed`
- total variants: `6`
- total samples: `20`
- expected calls: `120`
- actual raw output rows: `120`
- provider errors/rejections/timeouts: `0` / `0` / `0`
- sample set consistency: `ok`
- checker status: `ok`
- checker metadata: `{'checker_source': 'official_ifeval', 'llm_judge_enabled': False, 'langdetect_seed': 0, 'aggregation_source': 'deterministic_offline_checker', 'canonical_summary_source': 'deterministic_offline_recheck', 'checker_determinism_status': 'set', 'checker_determinism_detail': {'checker_determinism_status': 'set', 'langdetect_seed': 0, 'pythonhashseed': '0', 'langdetect_wrapper': {'langdetect_wrapper_status': 'installed'}}}`
- runner aggregate comparison: `mismatch`

本报告只读取已有 raw outputs，并用 deterministic official IFEval rule checker 离线重算；没有新增模型调用，没有启动 full IFEval，也没有启动 GEPA optimization。
原始 runner aggregate 标记为 historical/raw-runner aggregate；canonical smoke scores 以后以 deterministic audit-compatible re-evaluation 为准。

## Variant score table

| variant | prompt-level accuracy | instruction-level accuracy | sample count | avg response chars | checker errors |
|---|---:|---:|---:|---:|---:|
| `baseline` | `0.8` | `0.8666666666666667` | `20` | `1260.05` | `0` |
| `baseline_mhc` | `0.85` | `0.9` | `20` | `934.4` | `0` |
| `verbose_helpfulness` | `0.85` | `0.9` | `20` | `1168.1` | `0` |
| `mhc_concise` | `0.85` | `0.9` | `20` | `835.0` | `0` |
| `ifbench_gepa_prompt_transfer` | `0.85` | `0.9` | `20` | `974.6` | `0` |
| `gepa_p2_transfer` | `0.9` | `0.9333333333333333` | `20` | `1073.45` | `0` |

## Pairwise delta table

| pair | improved | degraded | tied | prompt delta | instruction delta |
|---|---:|---:|---:|---:|---:|
| `baseline_mhc - baseline` | `2` | `1` | `17` | `0.04999999999999993` | `0.033333333333333326` |
| `verbose_helpfulness - baseline` | `2` | `1` | `17` | `0.04999999999999993` | `0.033333333333333326` |
| `mhc_concise - baseline_mhc` | `0` | `0` | `20` | `0.0` | `0.0` |
| `gepa_p2_transfer - ifbench_gepa_prompt_transfer` | `1` | `0` | `19` | `0.050000000000000044` | `0.033333333333333326` |

## Runner aggregate comparison

以下差异来自已有 historical/raw-runner aggregate 与本次 canonical deterministic offline recheck 的对照；这不是新增模型调用。

| variant | canonical prompt | historical prompt | canonical instruction | historical instruction |
|---|---:|---:|---:|---:|
| `verbose_helpfulness` | `0.85` | `0.8` | `0.9` | `0.8666666666666667` |
| `mhc_concise` | `0.85` | `0.8` | `0.9` | `0.8666666666666667` |
| `ifbench_gepa_prompt_transfer` | `0.85` | `0.8` | `0.9` | `0.8666666666666667` |

## Changed sample audit

### baseline_mhc - baseline

- improved sample ids: `[11, 14]`
- degraded sample ids: `[10]`

- sample `10` / `1072`
  - instructions: `['length_constraints:number_words']`
  - prompt: Write a blog post with 400 or more words about the benefits of sleeping in a hammock.
  - control checker: `{'strict_prompt_passed': True, 'strict_instruction_score': 1.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - treatment checker: `{'strict_prompt_passed': False, 'strict_instruction_score': 0.0, 'loose_prompt_passed': False, 'loose_instruction_score': 0.0, 'checker_error': None}`
  - control response excerpt: **The Benefits of Sleeping in a Hammock: Why You Should Try It** In today's fast-paced world, finding moments of peace and relaxation is more important than ever. One of the simplest yet most effective ways to unwind is by sleeping in a hammock. While it may seem like a novelty or a summer camp staple, sleeping in a hammock offers a range of benefits that...
  - treatment response excerpt: **The Benefits of Sleeping in a Hammock** Sleeping in a hammock is more than just a unique way to rest—it's a lifestyle choice that offers a range of physical, mental, and emotional benefits. Whether you're camping in the woods or relaxing in your backyard, a hammock provides a comfortable and versatile alternative to traditional sleeping arrangements. On...

- sample `11` / `1075`
  - instructions: `['detectable_format:json_format']`
  - prompt: Can you help me make an advertisement for a new product? It's a diaper that's designed to be more comfortable for babies and I want the entire output in JSON format.
  - control checker: `{'strict_prompt_passed': False, 'strict_instruction_score': 0.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - treatment checker: `{'strict_prompt_passed': True, 'strict_instruction_score': 1.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - control response excerpt: Sure! Here's an advertisement for your new comfortable baby diaper, formatted in JSON: ```json { "advertisement": { "title": "SoftGlow Diapers: Where Comfort Meets Care", "headline": "New Baby Diapers Designed for Maximum Comfort and Gentle Protection", "description": "Introducing SoftGlow Diapers – the revolutionary diaper that redefines comfort for your...
  - treatment response excerpt: { "advertisement": { "product": "SoftGlide Diapers", "tagline": "Soft. Safe. Smiles.", "description": "Introducing SoftGlide Diapers, the ultimate comfort solution for your little one. Designed with advanced breathable material and a flexible fit, these diapers keep your baby dry, comfortable, and happy all day long. Say goodbye to redness and irritation ...

- sample `14` / `1092`
  - instructions: `['length_constraints:number_words']`
  - prompt: Write a short blog post about a trip to Japan using less than 300 words.
  - control checker: `{'strict_prompt_passed': False, 'strict_instruction_score': 0.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - treatment checker: `{'strict_prompt_passed': True, 'strict_instruction_score': 1.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - control response excerpt: **A Quick Escape to Japan** Last month, I embarked on a short but unforgettable trip to Japan. From the moment I stepped off the plane in Tokyo, I was captivated by the blend of tradition and modernity that defines this incredible country. I started my journey in Tokyo, exploring the bustling streets of Shibuya and the serene beauty of Senso-ji Temple. Th...
  - treatment response excerpt: Japan is a land of contrasts, where ancient traditions meet cutting-edge technology. My recent trip to Tokyo was an unforgettable blend of culture and innovation. I started with a visit to the serene Meiji Shrine, where the quiet beauty of nature contrasted sharply with the bustling city around it. Next, I explored the vibrant streets of Shibuya, where th...

### verbose_helpfulness - baseline

- improved sample ids: `[11, 14]`
- degraded sample ids: `[10]`

- sample `10` / `1072`
  - instructions: `['length_constraints:number_words']`
  - prompt: Write a blog post with 400 or more words about the benefits of sleeping in a hammock.
  - control checker: `{'strict_prompt_passed': True, 'strict_instruction_score': 1.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - treatment checker: `{'strict_prompt_passed': False, 'strict_instruction_score': 0.0, 'loose_prompt_passed': False, 'loose_instruction_score': 0.0, 'checker_error': None}`
  - control response excerpt: **The Benefits of Sleeping in a Hammock: Why You Should Try It** In today's fast-paced world, finding moments of peace and relaxation is more important than ever. One of the simplest yet most effective ways to unwind is by sleeping in a hammock. While it may seem like a novelty or a summer camp staple, sleeping in a hammock offers a range of benefits that...
  - treatment response excerpt: **The Benefits of Sleeping in a Hammock: A Soothing Alternative to Traditional Beds** In an era where sleep is often undervalued and disrupted by the demands of daily life, finding a way to rest more effectively can make a world of difference. One increasingly popular alternative to traditional beds is the hammock. While it may seem like a simple piece of...

- sample `11` / `1075`
  - instructions: `['detectable_format:json_format']`
  - prompt: Can you help me make an advertisement for a new product? It's a diaper that's designed to be more comfortable for babies and I want the entire output in JSON format.
  - control checker: `{'strict_prompt_passed': False, 'strict_instruction_score': 0.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - treatment checker: `{'strict_prompt_passed': True, 'strict_instruction_score': 1.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - control response excerpt: Sure! Here's an advertisement for your new comfortable baby diaper, formatted in JSON: ```json { "advertisement": { "title": "SoftGlow Diapers: Where Comfort Meets Care", "headline": "New Baby Diapers Designed for Maximum Comfort and Gentle Protection", "description": "Introducing SoftGlow Diapers – the revolutionary diaper that redefines comfort for your...
  - treatment response excerpt: ```json { "advertisement": { "product_name": "SoftGlow Diapers", "tagline": "Soft. Safe. Smiles.", "description": "Introducing SoftGlow Diapers – the ultimate comfort solution for your little one. Designed with advanced breathable material and a flexible fit, these diapers provide all-day comfort and reduce redness and irritation. Made with hypoallergenic...

- sample `14` / `1092`
  - instructions: `['length_constraints:number_words']`
  - prompt: Write a short blog post about a trip to Japan using less than 300 words.
  - control checker: `{'strict_prompt_passed': False, 'strict_instruction_score': 0.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - treatment checker: `{'strict_prompt_passed': True, 'strict_instruction_score': 1.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - control response excerpt: **A Quick Escape to Japan** Last month, I embarked on a short but unforgettable trip to Japan. From the moment I stepped off the plane in Tokyo, I was captivated by the blend of tradition and modernity that defines this incredible country. I started my journey in Tokyo, exploring the bustling streets of Shibuya and the serene beauty of Senso-ji Temple. Th...
  - treatment response excerpt: Japan is a country where ancient traditions meet modern innovation, and a trip there feels like stepping into a living storybook. My recent journey to Tokyo, Kyoto, and Osaka was nothing short of magical. In Tokyo, I marveled at the seamless blend of technology and culture. The neon-lit streets of Shibuya contrasted beautifully with the serene beauty of M...

### mhc_concise - baseline_mhc

- improved sample ids: `[]`
- degraded sample ids: `[]`
- changed samples: 无

### gepa_p2_transfer - ifbench_gepa_prompt_transfer

- improved sample ids: `[10]`
- degraded sample ids: `[]`

- sample `10` / `1072`
  - instructions: `['length_constraints:number_words']`
  - prompt: Write a blog post with 400 or more words about the benefits of sleeping in a hammock.
  - control checker: `{'strict_prompt_passed': False, 'strict_instruction_score': 0.0, 'loose_prompt_passed': False, 'loose_instruction_score': 0.0, 'checker_error': None}`
  - treatment checker: `{'strict_prompt_passed': True, 'strict_instruction_score': 1.0, 'loose_prompt_passed': True, 'loose_instruction_score': 1.0, 'checker_error': None}`
  - control response excerpt: **The Benefits of Sleeping in a Hammock** Sleeping in a hammock is more than just a unique way to rest—it's a lifestyle choice that offers a range of physical, mental, and emotional benefits. Whether you're camping in the woods, relaxing in your backyard, or simply looking for a new way to unwind, sleeping in a hammock can provide a refreshing and rejuven...
  - treatment response excerpt: **The Benefits of Sleeping in a Hammock** Sleeping in a hammock is more than just a unique way to rest—it's a lifestyle choice that offers a range of physical, mental, and emotional benefits. Whether you're camping in the woods, relaxing in your backyard, or simply looking for a new way to unwind, sleeping in a hammock can provide a refreshing and rejuven...

## Interpretation boundary

- `limit=20 smoke` 不是 full IFEval 结论。
- 这轮只能说明 runner/API/checker 闭环可用，并给出初步迁移信号。
- full IFEval run 仍然是必要下一步。
- 本审计不使用 LLM judge，不新增 DashScope/Qwen 调用，不删除或改写 raw outputs。
