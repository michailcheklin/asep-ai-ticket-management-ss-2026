# LLM & Hardware Requirements

This page documents the LLM setup (current and planned) and the hardware requirements for running the ZIM Helper stack (Zammad + Backend + Frontend + RAG + LLM) locally.

## LLM setup

### Currently used LLM (today's code, `backend/llm/llm.py`)

Selected via `USE_SAIA_API` in `.env`:

| Mode | Model | Provider | Config |
|---|---|---|---|
| Local (default, `USE_SAIA_API=false`) | `qwen3:8b` | Ollama (`ChatOllama`) | `OLLAMA_BASE_URL` (default `http://localhost:11434`), temperature 0.2 |
| Remote (`USE_SAIA_API=true`) | `openai-gpt-oss-120b` | SAIA API / Academic Cloud (`ChatOpenAI`, base URL `https://chat-ai.academiccloud.de/v1`) | `SAIA_API_KEY` required, temperature 0.2, timeout 120s |

SAIA has a hard cap of **3,000 requests/month** — local development runs against Ollama by default; SAIA is reserved for quality evaluation and final feature review.

### Planned direction (agreed target, not yet implemented)

As agreed for whoever continues this project, the target setup reverses today's default:

- **Primary: `openai-gpt-oss-120b` running locally** via Ollama, instead of remotely via SAIA.
- **Fallback: a hosted API (e.g. Claude)**, used only when the local model is unavailable (connection error, timeout, OOM) — not as the default path.

Only one local model is planned: `gpt-oss-120b`. `GLM-4.7` is not a local alternative — it is used only as a development-time fallback over the SAIA API, in case SAIA drops support for `gpt-oss-120b` in the future (see the benchmark comparison below, where it is evaluated as a hosted/API-path candidate, not a local one).

This fallback logic is not implemented yet — see [`docs/FUTURE_WORK.md`](FUTURE_WORK.md), section "Local model → API fallback", for the required changes to `backend/llm/llm.py`. The hardware sizing below is for this planned local `gpt-oss-120b` setup, since it is significantly heavier than the currently-used `qwen3:8b`.

## Hardware requirements for local operation (`openai-gpt-oss-120b` via Ollama)

`gpt-oss-120b` is a ~117B-parameter mixture-of-experts model (~5.1B active parameters per token), natively released in MXFP4 quantization. Figures below are approximate, based on OpenAI's and Ollama's published model-card sizing for this quantized format — validate against actual target hardware before relying on them.

Sizing below assumes a departmental server the ZIM university IT team would actually procure or repurpose — a workstation/rack server with a handful of prosumer or workstation GPUs — not a datacenter-class multi-H100 box.

| | Minimum (runnable) | Recommended (production-ready, acceptable response times) |
|---|---|---|
| GPU / VRAM | ~48 GB VRAM across 1–2 workstation/prosumer GPUs (e.g. 2× RTX 3090/4090 24GB, or 1× RTX A6000 48GB), with the remaining MoE experts CPU-offloaded (Ollama/llama.cpp support this) — slower per-token, but avoids requiring a full 65 GB+ GPU | ~80–96 GB VRAM across 2 GPUs (e.g. 2× RTX A6000/L40S 48GB, or 4× RTX 4090 24GB), enough to hold the whole model in VRAM with no CPU offload |
| System RAM (Arbeitsspeicher) | 64 GB — headroom for CPU-offloaded experts plus the rest of the Docker stack (Zammad, RAG) | 128 GB — no offload needed for the model itself, but leaves headroom for concurrent chat sessions and Zammad/Elasticsearch under load |
| CPU | 8 cores (host process + Docker stack) | 16 cores (PCIe/offload bandwidth matters more than raw core count once GPUs are involved) |
| Disk | ~65 GB for the quantized model weights | ~100 GB (model + cache + other pulled models) |

This is a substantially larger footprint than the `qwen3:8b` model used today (~6 GB, runnable on CPU): moving to a locally-hosted `gpt-oss-120b` means budgeting for a small GPU server (workstation cards, not a datacenter accelerator), not a developer laptop or a single consumer GPU.

If the hosted-API fallback (e.g. Claude) is used instead of the local model, no local LLM hardware is needed for that path — only network access to the API and a valid API key.

## Smaller model evaluation (benchmark-based)

Two smaller candidates were compared against the current production model `gpt-oss-120b`, based on the DeepEval conversation benchmark (four metrics — Conversation Completeness, Hallucination Detection, Knowledge Retention, Answer Relevancy — judged by `qwen3.6-35b-a3b`; full methodology, per-scenario scores and raw logs in `tests/README_TESTS.md` and `tests/logs/`). `gpt-oss-120b` is the only model planned for local hosting (see [LLM setup](#llm-setup) above); the candidates below are evaluated as-is, not as local replacements.

### Candidate comparison

| Model | Parameters | VRAM (local, quantized) | License |
|---|---|---|---|
| `gpt-oss-120b` (current) | ~117B MoE (~5.1B active per token) | ~65–80 GB | Apache 2.0 |
| `glm-4.7` | 358B MoE | >200 GB quantized — not viable on a single GPU; accessed via SAIA API in this project | MIT |
| `llama-3.1-8b` | 8B | ~6 GB | Meta Llama 3.1 Community License |

### Benchmark results (DeepEval, judge `qwen3.6-35b-a3b`, 5 scenarios)

| Model | Completeness | Hallucination | Knowledge Retention | Answer Relevancy | Overall |
|---|---|---|---|---|---|
| gpt-oss-120b | 0.93 | 0.98 | 0.70 | 0.96 | **0.89** |
| glm-4.7 | 0.80 | 0.98 | 0.64 | 0.84 | **0.82** |
| llama-3.1-8b | 0.60 | 0.62 | 0.46 | 0.50 | **0.55** |

(Scores from the archived reference runs in `tests/logs/`; three further models were evaluated and rejected — see `tests/README_TESTS.md` for the full six-model table.)

### Recommendation

* **`glm-4.7` is sufficient quality-wise as the SAIA-API fallback for `gpt-oss-120b`** (see [LLM setup](#llm-setup) above) — it is the only candidate with a hallucination score on par with `gpt-oss-120b` (0.98) and completed all five scenarios. Observed limitations: in one of five scenarios it lost the conversation thread and restarted with a generic greeting (Knowledge Retention 0.64, its weakest metric), and its per-scenario scores varied noticeably between identical runs, so single-run figures are indicative only. As a 358B model it is not viable for local hosting (see candidate comparison above) — it is only ever reached via the SAIA API, never run locally.
* **`llama-3.1-8b` is not sufficient for the production use case** — it handles the two simplest scenarios well, but fails to reach any resolution in two of five scenarios (Completeness 0.00), and it violated the structured-output schema in one run (returned a wrong field instead of `intent`), which aborts the graph flow. It is defensible only as an emergency fallback where availability matters more than answer quality, and only with additional schema-validation guards.
* German language capability was adequate for all three models in the tested scenarios (all conversations are in German); no candidate failed specifically on language grounds.


## RAG components (embedding & re-ranking models)

Defined in `backend/rag/retrieve_info.py`, `rag_store_faq.py`, `rag_store_tickets.py` (see `backend/rag/README.md`):

| Collection | Model | Purpose | Parameters | Approx. RAM footprint (fp32) |
|---|---|---|---|---|
| `faq_db` | `intfloat/multilingual-e5-large` | Bi-encoder (embedding) | ~560M | ~2.2 GB |
| `faq_db` | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Cross-encoder re-ranker (2nd stage) | ~33M | ~0.2 GB |
| `ticket_db` | `deutsche-telekom/gbert-large-paraphrase-cosine` | Embedding | ~336M | ~1.3 GB |
| `recent_incidents_db` | `deutsche-telekom/gbert-large-paraphrase-cosine` (same model as `ticket_db`) | Embedding | ~336M | ~1.3 GB (shared with `ticket_db` if loaded once in the same process) |

All three models run via `sentence-transformers` on CPU; no GPU is required. Budget roughly **4 GB additional RAM** for RAG models (weights + activations + overhead), plus disk cache (Docker volume `huggingface-models`).

## Docker stack overall

The stack comprises Backend, Frontend(s), Mailpit, Zammad (Postgres, Elasticsearch, Redis, Memcached, Rails server, Scheduler, Websocket, Nginx), and optionally Ollama.

No Compose file sets explicit `deploy.resources`/`mem_limit`/`cpus` limits; the figures below are guidance derived from Zammad's official system requirements and the heap sizes already set in `zammad/docker-compose.yml` (`ES_JAVA_OPTS: -Xms1g -Xmx1g` for Elasticsearch, `-m 256M` for Memcached).

| | Minimum (runnable) | Recommended (production-ready) |
|---|---|---|
| CPU (whole stack excl. LLM) | 2 cores | 4 cores |
| RAM (whole stack excl. LLM) | 4 GB | 8 GB |
| RAM (Backend incl. RAG models) | +4 GB | +6 GB |
| VRAM (local LLM, `gpt-oss-120b` via Ollama) | +48 GB (1–2 GPUs) | +80–96 GB (2 GPUs) |
| System RAM (local LLM, `gpt-oss-120b` via Ollama) | +64 GB | +128 GB |
| **Total (fully local, `gpt-oss-120b` + Zammad + RAG)** | **~48 GB VRAM + ~72 GB RAM, GPU server required** | **~80–96 GB VRAM + ~142 GB RAM, GPU server required** |
| **Total (hosted API instead of local LLM)** | **~8 GB RAM, no GPU** | **~14 GB RAM, no GPU** |
| Disk | ~80 GB (images, volumes, model weights) | ~130 GB (incl. ticket/mail history over time) |

## Minimum vs. recommended — summary

- **Minimum (runnable):** stack starts and functions; running `gpt-oss-120b` locally requires a small GPU server (~48 GB VRAM across 1–2 workstation/prosumer cards, with the rest of the model's experts CPU-offloaded) plus 64 GB system RAM — there is no practical CPU-only minimum for this model, unlike the smaller `qwen3:8b` used today. No headroom for load spikes, and CPU-offloaded inference is noticeably slower per token.
- **Recommended (production-ready):** a 2-GPU server with ~80–96 GB total VRAM (e.g. 2× RTX A6000/L40S 48GB) so the whole model stays resident in VRAM, plus 128 GB system RAM for headroom — or rely on the hosted-API fallback (e.g. Claude) to avoid local GPU hardware entirely; sufficient RAM headroom for Zammad under load (Elasticsearch indexing, multiple concurrent chat sessions); response times in the 1–3s range for production/demo use.
