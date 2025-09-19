# Shackleton | Voice Assistant with LiveKit + OpenAI — Step‑by‑Step Roadmap

> Goal: Ship a real‑time, multimodal personal assistant (voice‑first, camera/vision optional) that runs in the browser/mobile, connects over LiveKit for ultra‑low‑latency media, and uses OpenAI models for reasoning, tools, and speech.

---

## Phase 0 — Architecture & Non‑negotiables

**Core loop (server‑authoritative):**

1. **Capture**: Browser/mobile streams mic (and optionally cam/screen) to a **LiveKit room**.
2. **Transcribe**: Either

    - **Realtime path**: Use **OpenAI Realtime API** via LiveKit Agents plugin (single model does STT → think → TTS), _or_
    - **Pipeline path**: LiveKit **VoicePipelineAgent** wires **STT (Whisper)** → **LLM** → **TTS**.

3. **Reason**: Model calls dev‑defined **tools** (calendar, search, RAG, home automation) via function‑calling.
4. **Speak**: Audio is synthesized and sent back as **WebRTC audio** into the same room (barge‑in/interrupt ready).
5. **State**: Short‑term dialogue state in memory; long‑term user memory in a store (e.g., **Qdrant/Postgres**), plus file‑based RAG.

**Must‑haves**

-   **Low latency** (<\~300–500 ms E2E speak‑back on fast networks). Prioritize Realtime path; fall back to pipeline for flexibility.
-   **Barge‑in**: Interrupt TTS when user starts speaking.
-   **Endpointing/VAD**: Robust end‑of‑speech detection (VAD + semantic endpointing) on the edge.
-   **Privacy**: PII redaction in logs; opt‑in camera; data retention controls.
-   **Observability**: per‑turn metrics (ASR delay, LLM thinking time, TTS synth time, RTT), transcripts, and tool audit.

---

## Phase 1 — Hello World (10–20 files)

1. **LiveKit project**: create a room; issue **ephemeral tokens** from a tiny auth server.
2. **Frontend** (Next.js or SvelteKit):

    - Join room, start mic, render waveform + push‑to‑talk and **hold‑to‑interrupt** buttons.

3. **Server Agent**:

    - **Option A: Realtime** — Create an **Agent Worker** that attaches to room as a bot participant using **OpenAI Realtime** via LiveKit Agents plugin.
    - **Option B: Pipeline** — Create a **VoicePipelineAgent** (STT→LLM→TTS) with OpenAI STT/TTS + LLM.

4. Ship: Say "Hello" to the bot; it replies. Verify barge‑in works.

**Exit criteria**: Duplex audio round‑trip < 500 ms, no crashes on network jitter, logs show timestamps for ASR/LLM/TTS.

---

## Phase 2 — Natural Conversation UX

-   **VAD & Endpointing**: Edge VAD (e.g., WebRTC VAD) + adaptive silence thresholds; enable **partial transcripts** and **semantic endpointing** (stop when intent is clear).
-   **Interruptions**: When user audio starts, **cancel TTS** and push the partial hypothesis back to the model (“Sorry, one moment…”) automatically.
-   **Personality & System Prompt**: Define **persona**, tone, and tool‑use policy. Add guardrails (no unsafe actions without confirmation).
-   **Transcripts UI**: Caption as you speak; show assistant’s words synchronized to audio.

**Exit criteria**: Users can cut in; captions stay in sync with speech; persona is consistent.

---

## Phase 3 — Tools (Shackleton capabilities)

Define JSON‑schema tools and the execution layer:

-   **Calendar**: `add_event`, `list_events`, `move_event` → Google/Microsoft adapters.
-   **Reminders**: `set_timer`, `remind_at` → server cron/queue.
-   **Web**: `web_search`, `get_url` → controlled browsing with source quoting.
-   **Local OS/Home** (opt‑in): `launch_app`, `control_device` via Home Assistant.
-   **Knowledge**: `rag_query`, `save_note`, `get_note` → Qdrant/Postgres. Ingest PDFs/notes to an embeddings index with metadata.

**Patterns**

-   Use OpenAI **function calling / tools** (Realtime or Responses API).
-   **Timeouts/Retries** and **circuit breakers** around external APIs.
-   **Tool sandbox**: Strong input validation; least‑privilege credentials per tool.

**Exit criteria**: Tool calls are observable (request/response), fail gracefully, and are cancellable.

---

## Phase 4 — Multimodality (“See & Show”)

-   **Vision‑in**: Periodic low‑FPS frames from camera; tool `describe_scene`, OCR receipts, read dashboards.
-   **Screen‑in** (desktop): screen‑share thumbnails for “explain this chart”.
-   **Render‑out**: Show images, code blocks, and small cards in the UI while it speaks. For longer content, offer a “Send to phone/email/Drive”.

**Exit criteria**: Assistant can answer questions about what it sees and reference specific regions verbally.

---

## Phase 5 — Memory & Personalization

-   **Short‑term**: windowed summary of the last N turns, stored per session.
-   **Long‑term**: events/notes/preferences → embeddings (Qdrant) + structured tables (Postgres). Add **privacy toggles** per memory item.
-   **Identity**: user profile (name, locale, time zone, work hours). Use to set defaults (e.g., “tomorrow 10am IST”).

**Exit criteria**: “Remind me to call mom Friday” persists and survives restarts; “What did I say about project X last week?” works.

---

## Phase 6 — Quality, Safety, & Tests

-   **Eval harness**: scripted conversations measuring ASR WER, tool accuracy, latency percentiles, hallucination rate, and refusal correctness.
-   **Red‑team prompts**: jailbreaks, unsafe actions; require explicit confirmations for destructive tools.
-   **Audio QA**: clipping detection, ducking, volume normalization.

**Exit criteria**: Dashboards with P50/P90 latency, tool success rate > a threshold, and refusal policy passes.

---

## Phase 7 — Delivery & Ops

-   **Hosting**: LiveKit Cloud _or_ self‑hosted SFU; Agents/Workers on a stateless compute (K8s, Fly.io, AWS ECS/Fargate).
-   **Secrets**: short‑lived tokens; bind API keys to server only; per‑tool scoped tokens.
-   **Cost control**:

    -   Realtime/token budgets; compress/segment video; adaptive frame rates.
    -   Cache TTS for common phrases; summarize long contexts.

-   **Observability**: OpenTelemetry spans per turn; log transcripts (redacted) + tool I/O.

**Exit criteria**: Zero‑downtime deploys; rolling upgrades of models/tools without dropping rooms.

---

## Phase 8 — Polishing the Assistant

-   **Wake‑word** (optional): on‑device (e.g., Porcupine or custom tiny model).
-   **Few‑shot skills**: quick “playbooks” (e.g., stand‑up notes, travel planning).
-   **Proactive**: scheduled jobs (“summarize my calendar every morning at 9”).
-   **Multi‑party**: handle crosstalk; attribute speakers; summarize meetings.

---

## Tech Blueprint (suggested)

**Frontend**

-   Next.js/SvelteKit; LiveKit Web SDK; Tailwind + shadcn; media controls, captions, tool‑result cards.

**Backend**

-   **LiveKit Agents**: Node or Python worker.
-   **Realtime path**: OpenAI Realtime model via LiveKit OpenAI integration.
-   **Pipeline path**: Whisper (STT) → OpenAI LLM (reasoning) → OpenAI TTS.
-   **Tools**: modular executors with Zod/JSON Schema validation.
-   **Memory**: Postgres + Qdrant; ingestion jobs (PDF/URL/MD → chunks → embeddings).

**Infra**

-   LiveKit Cloud (or self‑host); Redis (pub/sub + rate limits); Postgres; Qdrant; object storage for logs/artifacts.

---

## Minimal Code Sketches (pseudocode)

### 1) Agent (Realtime path)

```ts
// livekit-agent.ts (pseudocode)
import { Worker, connectAgent } from "livekit-agents";
import { openaiRealtime } from "livekit-agents-openai";

Worker.run(async (job) => {
    const agent = await connectAgent(
        job,
        openaiRealtime({
            model: process.env.OPENAI_REALTIME_MODEL,
            apiKey: process.env.OPENAI_API_KEY,
            // optional: tool schemas go here
        })
    );

    agent.on("tool", async (call) => {
        const result = await executeTool(call.name, call.args);
        await call.respond(result);
    });
});
```

### 2) Agent (Pipeline path)

```ts
// voice-pipeline.ts (pseudocode)
import { VoicePipelineAgent } from "livekit-agents";
import { whisperSTT, openaiLLM, openaiTTS } from "livekit-agents-openai";

new VoicePipelineAgent({
    stt: whisperSTT({ model: "whisper‑1" }),
    llm: openaiLLM({ model: "gpt‑4o‑mini" }),
    tts: openaiTTS({ voice: "alloy" }),
});
```

### 3) Tool schema

```ts
export const addEvent = {
    name: "calendar_add_event",
    description: "Create a calendar event",
    parameters: {
        type: "object",
        properties: {
            title: { type: "string" },
            when: { type: "string", description: "ISO datetime or natural language" },
            durationMin: { type: "number" },
            attendees: { type: "array", items: { type: "string", format: "email" } },
        },
        required: ["title", "when"],
    },
};
```

---

## Data & Prompts

-   **System**: persona, safety rules, escalation policy, confirmation thresholds, how/when to use tools, style (concise, cite sources), and latency budget.
-   **Few‑shots**: canonical examples (timer, meetings, “open my IDE”, “explain this chart”).
-   **RAG**: chunk sizes 512–1,024 tokens; store URL/section anchors; add recency decay.

---

## Latency Budget (targets)

-   Capture→ASR partial: **<150 ms**
-   ASR finalization: **<300 ms**
-   LLM first token: **<100–200 ms** (with Realtime)
-   TTS speak start: **<150 ms** after first token
-   End‑to‑end barge‑in recovery: **<150 ms** to pause/cancel

---

## Security & Privacy Checklist

-   Rotate ephemeral LiveKit tokens; bind to room and role.
-   Do not expose OpenAI keys to the client; only server workers can call models/tools.
-   Per‑tool scoped credentials; rate limits and quotas per user.
-   Redact PII in logs; encrypt transcripts at rest; retention windows per user setting.

---

## What to Build First (milestones)

1. **Voice echo** (join room, bot says “I’m here”).
2. **Conversational turn‑taking** with barge‑in.
3. **Timers + Calendar** tools (real utility).
4. **RAG on your docs** (notes, PDFs, code).
5. **Vision‑in** (optional) with scene description.
6. **Proactive morning brief** (agenda + weather + inbox summary).

---

## Nice‑to‑haves

-   Offline fallback (local wake‑word + local STT for quick commands).
-   Telephony (SIP) to call/receive phone calls.
-   Multi‑agent routing: specialized “skills” for travel, coding, home.

---

## Project Skeleton (suggested)

```
apps/
  web/                 # Next.js/SvelteKit frontend (LiveKit Web SDK)
  agent/               # LiveKit Agents worker (Realtime or Pipeline)
  tools/               # Tool executors (calendar, web, rag, os)
  ingest/              # RAG ingestion jobs (pdf, url, md)
  api/                 # Tiny auth (ephemeral tokens), tool webhooks
infra/
  docker-compose.yml   # local dev (postgres, qdrant, redis)
  k8s/                 # prod manifests …
```

---

## Operational Playbook

-   Deploy web + agent separately; rolling update the agent worker pool.
-   Canary new model versions per room tag.
-   Track per‑turn spans (OpenTelemetry); alert on P95 > thresholds.
-   Nightly eval runs (synthetic conversations) with trend reports.

---

## Cutover Guidance

-   Start with **Realtime path** for best latency and simple dev.
-   Keep **Pipeline path** behind a flag for fallback/customization.
-   Build tools once; expose to both paths via a shared executor.

---

## Appendix — Choices & Trade‑offs

-   **Realtime (mono‑model)**: ✔ simplest E2E, best barge‑in; ✖ tighter coupling to a single vendor.
-   **Pipeline (modular)**: ✔ swap STT/TTS providers; ✖ more moving parts and buffering latency.
-   **Vision**: opt‑in only; resize & rate‑limit frames.
-   **RAG**: start with small corpora; add feedback (“did that answer help?”) to tune.

---

**Next step:** implement Phase 1. If you want, I can drop in a minimal starter repo layout with real code for the agent worker and a LiveKit‑ready frontend.
