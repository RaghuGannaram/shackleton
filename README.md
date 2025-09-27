# Shackleton | AI Voice Assistant — Combined Roadmap & README

> **Shackleton** is a resilient, loyal, and companionable AI assistant — a leader of tools and tasks who brings the explorer’s determination into your daily work, while speaking with warmth, humor, and steady support.
>
> **Goal:** Ship a real-time, multimodal personal assistant (voice-first, camera/vision optional) that runs in the browser/mobile, connects over **LiveKit** for ultra-low-latency media, and uses realtime LLMs for reasoning, tools, and speech.

---

### Core loop (server‑authoritative)
1. **Capture**: Browser/mobile streams mic (and optionally cam/screen) to a **LiveKit room**.
2. **Transcribe**:
   - Realtime path: Realtime LLMs via LiveKit Agents plugin (STT → LLM → TTS), _or_
   - Pipeline path: LiveKit VoicePipelineAgent wiring STT (Whisper) → LLM → TTS.
3. **Reason**: Model calls dev‑defined tools (calendar, search, RAG, home automation) via function‑calling.
4. **Speak**: Audio is synthesized and sent back as WebRTC audio (barge‑in/interrupt ready).
5. **State**: Short‑term dialogue state and long‑term memory (Qdrant/Postgres) + file-based RAG.

### Must‑haves (non‑negotiable)
- Low latency (<~300–500 ms E2E speak‑back on good networks).
- Barge‑in (cancel TTS when user starts speaking).
- Robust endpointing & VAD at the edge.
- PII redaction, opt‑in camera, retention controls.
- Observability: per‑turn metrics and tool audit logs.

---

## Phases (precise & consolidated)

### Phase 0 — Foundation (Current)
**Goal:** Run a voice bot in LiveKit and wire basic tools.
- LiveKit integration, ephemeral tokens, simple frontend for mic join.
- Tools: Weather (wttr.in), DuckDuckGo search (discovery).
- Exit criteria: Bot can join a room and reply; barge‑in works; ASR/LLM/TTS spans captured.

### Phase 1 — Context‑Aware Retrieval (MVP)
**Goal:** Reliable factual answers with provenance and timeline awareness.
- Replace snippet-only behavior by: DuckDuckGo discovery + full-HTML fetch (ScrapingBee/ScraperAPI) + extractor (`newspaper3k`/Readability).
- Timeline intelligence: Shackleton infers or asks timeline clarifying questions (yesterday, day before yesterday, tomorrow, custom range).
- Publish-date verification and filtering (drop results outside requested window).
- Add provenance store (URL, fetch time, excerpt, confidence).
- Vector DB (Pinecone/FAISS/Qdrant) ingestion for RAG.
**Exit criteria:** Verified sources for time-based queries and citations returned with answers.

### Phase 2 — Knowledge Expansion & Tools
**Goal:** Broader knowledge and researcher capabilities.
- Add News APIs, finance APIs, knowledge graphs, and hybrid retrieval (BM25 + embeddings).
- Enhanced summarization & multi‑doc QA.
- More connectors: PDF ingestion, OCR, and structured document parsing.
**Exit criteria:** Multi‑source synthesis with accurate citations and date-aware retrieval.

### Phase 3 — Productivity & Action Tools
**Goal:** Make Shackleton actionable in workflows.
- Connectors: Google Calendar, Gmail (read/draft), Slack, Drive, GitHub, Jira.
- Action manager: safe actuation (create events, send drafts) with explicit confirmations and audit logs.
- Improved session memory and personalization.
**Exit criteria:** Secure OAuth flows and safe execution of user-confirmed actions.

### Phase 4 — Multimodality (See & Show)
**Goal:** Allow Shackleton to see and interact with visual content and richer inputs.
- Vision: frame OCR, scene description, screen-share analysis.
- Render-out: cards, images, attachments in UI while speaking.
**Exit criteria:** Assistant can reason about images/screens and reference specific regions verbally.

### Phase 5 — Autonomous Agent Mode
**Goal:** Multi‑step planning and autonomous workflows.
- Define macros and watchlists, schedule monitoring and briefing jobs, autonomous low-risk tasks.
- Personal long-term memory with opt-in retention and adaptive persona.
**Exit criteria:** End-to-end autonomous workflows (with explicit user opt-in) and audit trail.

### Phase 6 — Top-Level Assistant (Final)
**Goal:** Proactive, multimodal, context-rich assistant.
- Continuous context awareness, proactive notifications, domain-specific skills, enterprise controls.
**Exit criteria:** High user satisfaction in pilots; SLAs and governance in place.

---

## Essential Tooling & Infrastructure (summary)

- **Discovery & Fetching**: DuckDuckGo / SerpApi (discovery) → ScrapingBee / ScraperAPI / Playwright (full HTML rendering).
- **Extraction**: newspaper3k, Readability, BeautifulSoup, custom heuristics.
- **Indexing & RAG**: Pinecone / Qdrant / FAISS; embeddings (OpenAI or open-source).
- **Agent Orchestration**: LangChain / LlamaIndex or a custom orchestrator with tool schemas (Zod/JSON Schema).
- **Workers**: Celery / RQ / K8s jobs for Playwright rendering, ingestion, and scheduled tasks.
- **Storage**: Postgres (metadata), S3 (raw artifacts), Redis (session & rate-limits).
- **Realtime Stack**: LiveKit (rooms), model broker that routes to OpenAI/Google realtime models based on latency/cost.
- **Monitoring**: OpenTelemetry, Grafana, ELK for logs and traces.

---

## Operational Principles & Safety
- Respect robots.txt & site ToS; prefer licensed feeds for heavy news ingestion.
- Persist provenance for every externally-sourced fact (URL + timestamp + excerpt).
- Strong PII detection/redaction before logs and audits.
- Cost control: model broker, caching, and per-user quotas.
- Human-in-loop for destructive or sensitive actions; explicit confirmation UI.

---

## Developer Roadmap (sprint-style)
**Weeks 0–4**: Phase 1 core: full-fetch pipeline, publish-date verification, provenance.  
**Weeks 5–8**: Vector DB + simple RAG; orchestration controller; basic tests.  
**Weeks 9–12**: Connectors (Calendar, Slack); action manager.  
**Weeks 13–18**: Document ingestion, Playwright fallback, RSS/feeds.  
**Weeks 19–26**: LiveKit streaming improvements, STT/TTS polish, multimodal hooks.  
**Weeks 27+**: Security audits, scaling, enterprise features.

---

## Minimal API & Data Model (suggested)
- **/query** → orchestrates search→fetch→extract→answer; returns answer + provenance list.  
- **Provenance record**: `{source_url, publisher, fetch_timestamp, publish_date, excerpt, confidence}`.  
- **Stored artifact**: raw HTML → s3, extracted text → vector DB; metadata → Postgres.

---

## Prompts, Persona & Prompt Engineering
- System prompt: define persona, tool usage policy, citation requirement, safety rules, and latency budget.  
- Few-shots: canonical examples for tool calls and safe confirmations.  
- RAG prompts: include metadata block (url, date, publisher) for each chunk passed to the LLM.

---

## Testing & Validation
- Create **golden-case dataset** for time-sensitive queries (yesterday/last week/custom ranges).  
- Integration tests for search → fetch → publish-date verification flows.  
- Nightly synthetic conversations and red-team checks.

---

## Next Immediate Actions (prioritized)
1. Replace snippet-only search with full‑HTML fetch + publish‑date verification.  
2. Add provenance layer and expose in replies.  
3. Add small vector DB and pass snippets to LLM with citations.  
4. Implement timeline-intent disambiguation (ask user or infer) for each time-sensitive query.

---

## Appendices (Useful snippets & patterns)
- Tools must validate input via JSON Schema.  
- Chunking: 512–1024 tokens with overlap for RAG.  
- Caching: short TTL (minutes–hours) for news queries; longer for stable documents.

---

## Contact & Repo Layout (recommended)
```
apps/
  web/                 # frontend (LiveKit Web SDK)
  agent/               # LiveKit Agents worker
  tools/               # Tool executors
  ingest/              # ingestion jobs
  api/                 # auth + endpoints
infra/
  docker-compose.yml
  k8s/
```

---

# Credits & Inspiration
This combined README merges your original Phase 0–8 design with the phase-by-phase roadmap and retrieval recommendations (SERP + rendered-fetch + extractor + RAG) so Shackleton can be reliable, timeline-aware, and actionable.

---
