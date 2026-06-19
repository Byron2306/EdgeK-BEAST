# Provider Onboarding Notes

Generated: `2026-06-19`

## SambaNova Cloud

- **Requires API key:** yes.
- **Signup:** create a SambaCloud account at `https://cloud.sambanova.ai`.
- **API key location:** `https://cloud.sambanova.ai/apis`.
- **OpenAI-compatible base URL:** `https://api.sambanova.ai/v1`.
- **Chat completions endpoint:** `https://api.sambanova.ai/v1/chat/completions`.
- **Suggested initial BEAST env var:** `SAMBANOVA_API_KEY`.
- **Suggested initial model:** `Meta-Llama-3.3-70B-Instruct`.
- **Current official free access note:** SambaNova Cloud advertises `$5` in signup credits, no credit card required, with initial credits expiring in 30 days. Treat aggregator claims of a persistent unlimited free tier as unverified until confirmed directly in the SambaNova portal.
- **Current official model note:** official docs currently list `Meta-Llama-3.3-70B-Instruct`, `gpt-oss-120b`, and DeepSeek models for SambaCloud. The older/aggregator claim about Llama 3.1 405B should be verified in the portal before adding it to live benchmarks.

Sources:

- `https://sambanova-systems.mintlify.dev/docs/en/get-started/api-keys-urls.md`
- `https://sambanova-systems.mintlify.dev/docs/en/features/openai-compatibility.md`
- `https://sambanova-systems.mintlify.dev/docs/en/get-started/quickstart.md`
- `https://cloud.sambanova.ai/plans`

## Free/OpenAI-Compatible Provider Signup Matrix

This table records signup/API-key routes for providers worth adding to the next BEAST free/low-cost benchmark pass. "Free" claims should be rechecked immediately before running live tests because quotas and model catalogs change quickly.

| Provider | Signup / API key location | OpenAI-compatible base URL | Key env var | Free/access status | BEAST route note |
| --- | --- | --- | --- | --- | --- |
| SambaNova Cloud | `https://cloud.sambanova.ai`, API keys at `https://cloud.sambanova.ai/apis` | `https://api.sambanova.ai/v1` | `SAMBANOVA_API_KEY` | Official plan page currently shows `$5` signup credits, no card, expiring in 30 days; persistent-free claim needs portal verification. | Test direct API separately from HF SambaNova route. Start with `Meta-Llama-3.3-70B-Instruct`; verify whether Qwen/Coder and 405B are currently exposed. |
| SambaNova via Hugging Face | Use existing Hugging Face account/token; provider page at `https://huggingface.co/sambanovasystems/models` | Hugging Face router (`https://router.huggingface.co/v1`) with provider suffix where available | `HF_TOKEN` | HF org is a verified inference provider; route/catalog differs from SambaCloud direct. | Add as `sambanova_hfrouter`, not as the same provider as direct SambaNova Cloud. |
| GitHub Models | `https://github.com/marketplace/models`; use GitHub credentials/PAT with model access | `https://models.github.ai/inference` | `GITHUB_TOKEN` | Official docs: all GitHub accounts have rate-limited no-cost access for prototyping. | High-value benchmark: GPT-4o via a free/account-tied route would be headline-worthy. |
| Mistral La Plateforme | `https://console.mistral.ai`; create key in Studio/API Keys after activating Free mode | Mistral API endpoint from console/docs | `MISTRAL_API_KEY` | Official docs: Free mode API access enabled by default, no credit card, limited usage. | Prioritize `codestral-latest` or current Codestral equivalent for code-governance fitness. |
| Cloudflare Workers AI | Cloudflare dashboard -> Workers AI -> Use REST API | OpenAI-compatible endpoint is account-scoped under Cloudflare API | `CLOUDFLARE_API_TOKEN` or current alias `CLOUDFARE_API_KEY`, plus `CLOUDFLARE_ACCOUNT_ID` | Free allocation exists, but billing is neuron/request based and model/task dependent. | Best as latency/edge-inference benchmark; smaller context may push it toward scout/microtask roles. |
| SiliconFlow | SiliconFlow console/API Keys | `https://api.siliconflow.cn/v1` or current regional endpoint from docs | `SILICONFLOW_API_KEY` | Official docs/pricing advertise get-started/free access, but quotas need console confirmation. | Good Tier 2 route; OpenAI-compatible, broad model catalog. |
| Kilo Code Gateway | `https://app.kilo.ai`; API keys in app dashboard if using gateway | Kilo gateway endpoint from app/docs | `KILOCODE_API_KEY` | Kilo is primarily a coding-agent/gateway product, not a raw inference provider. | Treat as gateway/comparator only; do not rank beside base inference providers unless route is explicit. |
| ModelScope | ModelScope account; API-Inference key after login | `https://api-inference.modelscope.cn/v1` | `MODELSCOPE_API_KEY` | Docs describe free API-Inference for registered users and OpenAI-compatible LLM interface. | Useful diversity route; expect region/auth friction. |
| Z.AI / Zhipu AI | International: `https://z.ai/model-api`; China: `https://open.bigmodel.cn` | Z.AI/Open Platform endpoint from dashboard | `ZAI_API_KEY` | Signup/API key available; billing/top-up may be required depending region and model. | Test GLM coding/reasoning under strict Action IR. |
| Aion Labs | `https://www.aionlabs.ai` -> Sign In / Request Access | `https://api.aionlabs.ai/v1` | `AIONLABS_API_KEY` | OpenAI-compatible docs; access may require request/approval. | Mark `pending_access` until key issuance is confirmed. |
| LLM7.io | Basic access may be no-registration; token page commonly cited as `https://token.llm7.io` | `https://api.llm7.io/v1` | `LLM7_API_KEY` | Free gateway claim exists; provenance/model hosting should be treated cautiously. | Scout-only until reliability, data policy, and model provenance are verified. |
| Nebius | `https://studio.nebius.ai` / Token Factory docs | Nebius Studio/Token Factory OpenAI-compatible endpoint | `NEBIUS_API_KEY` | OpenAI-compatible; free-credit status must be confirmed in account. | Good for large OSS models, possibly 405B-class if currently listed. |
| DeepSeek | API keys at `https://platform.deepseek.com/api_keys` | `https://api.deepseek.com` or `/v1` for OpenAI SDKs | `DEEPSEEK_API_KEY` | Official docs require API key; third-party current claims mention signup tokens, but verify in dashboard. | High-priority: reasoning model under output governor could be a meaningful proof point. |
| DeepSeek via Puter | Puter account/dashboard; copy Puter auth token if using the OpenAI-compatible API | `https://api.puter.com/puterai/openai/v1` | `PUTER_AUTH_TOKEN` or `PUTER_API_KEY` | Puter advertises free-for-developer AI access with user-funded usage. This is a different economic route from DeepSeek direct. | Add as `puter_deepseek`; keep separate from `deepseek` because route, billing, and auth semantics differ. |
| Together AI | `https://api.together.ai` | `https://api.together.xyz/v1` or current docs endpoint | `TOGETHER_API_KEY` | OpenAI-compatible; free credits vary by account/promotion. | Widely recognized developer route; good benchmark resonance. |
| Fireworks AI | `https://app.fireworks.ai` dashboard/API keys | `https://api.fireworks.ai/inference/v1` | `FIREWORKS_API_KEY` | OpenAI-compatible; free credits often advertised but current amount should be verified in dashboard. | Good benchmark route for Qwen, Llama, DeepSeek, coding models. |

## Local Route Smoke Status

Checked: `2026-06-19`

These checks used a tiny JSON prompt and did not print secret values.

| Provider | Preset | Status | Notes |
| --- | --- | --- | --- |
| SambaNova Cloud | `sambanova` | OK | Direct OpenAI-compatible route responded with strict JSON. |
| Mistral | `mistral` | OK | Route responded; wrapped JSON in markdown in the smoke test, so output governance remains important. |
| DeepSeek | `deepseek` | Blocked | Route returned `402 Payment Required`; key/route shape is likely correct, but billing/free-credit activation is needed. |
| DeepSeek via Puter | `puter_deepseek` | OK | OpenAI-compatible Puter route responded with strict JSON. |
| LLM7.io | `llm7` | OK | Route responded; wrapped JSON in markdown in the smoke test, so start with strict output contract. |
| Aion Labs | `aion_labs` | OK | Route responded with strict JSON using the default preset model. |
| Cloudflare Workers AI | `cloudflare` | OK | Account-scoped endpoint works. Original `@cf/meta/llama-3.1-8b-instruct` returned `410 Gone`; preset now uses `@cf/meta/llama-3.1-8b-instruct-fast`. |
| GitHub Models | `github_models` | Blocked | Token is accepted by the endpoint, but probed models returned `403 no_access`. Recreate PAT with GitHub Models access / `models` scope, or enable model access for the account/org. |

Useful source pages:

- `https://huggingface.co/sambanovasystems/models`
- `https://docs.github.com/en/github-models/quickstart`
- `https://docs.github.com/billing/managing-billing-for-your-products/about-billing-for-github-models`
- `https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key`
- `https://developers.cloudflare.com/workers-ai/get-started/rest-api/`
- `https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/`
- `https://docs.siliconflow.com/en/userguide/quickstart`
- `https://modelscope.cn/docs/model-service/API-Inference/intro`
- `https://docs.z.ai/guides/overview/quick-start`
- `https://www.aionlabs.ai/docs/`
- `https://api-docs.deepseek.com/`
- `https://developer.puter.com/tutorials/free-unlimited-deepseek-api/`
- `https://developer.puter.com/tutorials/access-deepseek-using-openai-compatible-api/`
- `https://docs.together.ai/docs/inference/openai-compatibility`
- `https://docs.fireworks.ai/tools-sdks/openai-compatibility`
