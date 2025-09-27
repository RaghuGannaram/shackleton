from __future__ import annotations

import asyncio
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions

from livekit.plugins import openai
from livekit.plugins import google
from livekit.plugins import noise_cancellation

from configs.settings import settings
from configs.logger import (
    init_logger,
    get_logger,
    fetch_log_context,
    set_log_context,
    clear_log_context,
)
from tools.get_weather import get_weather
from tools.search_web import search_web
from prompts.instructions import (
    AGENT_INSTRUCTION,
    SESSION_INSTRUCTION,
)

load_dotenv()


# agent configs
REALTIME_PROVIDER = settings.REALTIME_PROVIDER
REALTIME_VOICE = settings.REALTIME_VOICE
REALTIME_TEMP = settings.REALTIME_TEMP
REALTIME_VISION = settings.REALTIME_VISION
REALTIME_USE_BVC = settings.REALTIME_USE_BVC

# logger configs
LOG_LEVEL = settings.LOG_LEVEL
LOG_DIR = settings.LOG_DIR
LOG_FILE = settings.LOG_FILE
LOG_MAX_BYTES = settings.LOG_MAX_BYTES
LOG_BACKUP_COUNT = settings.LOG_BACKUP_COUNT

# gaurdrails for sensitive tools
REQUIRE_CONFIRM_SENSITIVE = settings.REQUIRE_CONFIRM_SENSITIVE
SENSITIVE_TOOLS = {"send_email"}

log = init_logger(
    log_level=LOG_LEVEL,
    log_dir=LOG_DIR,
    log_file=LOG_FILE,
    max_bytes=LOG_MAX_BYTES,
    backups=LOG_BACKUP_COUNT,
)


def _requires_confirmation(tool_name: str, args: dict) -> bool:
    if not REQUIRE_CONFIRM_SENSITIVE:
        return False
    return tool_name in SENSITIVE_TOOLS


def _build_realtime_model():
    """
    Returns a LiveKit-compatible realtime model instance
    depending on the PROVIDER flag.
    """

    if REALTIME_PROVIDER == "google":
        # Gemini Realtime: single model for STT -> Think -> TTS
        return google.beta.realtime.RealtimeModel(
            voice=REALTIME_VOICE,
            temperature=REALTIME_TEMP,
        )
    elif REALTIME_PROVIDER == "openai":
        # OpenAI Realtime: single model for STT -> Think -> TTS
        return openai.realtime.RealtimeModel(
            voice=REALTIME_VOICE,
            temperature=REALTIME_TEMP,
        )
        raise NotImplementedError("OpenAI Realtime provider not wired yet.")
    elif REALTIME_PROVIDER == "pipeline":
        # TODO: Build modular pipeline (TTS (Whisper) -> LLM (OpenAI) -> TTS (Piper)) here.
        raise NotImplementedError("Pipeline provider not wired yet.")
    else:
        raise ValueError(f"Unknown REALTIME_PROVIDER: {REALTIME_PROVIDER}")


class Assistant(Agent):
    """
    Shackleton: leadership in service, tools as crew, loyal to the user.
    """

    def __init__(self) -> None:

        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=_build_realtime_model(),
            tools=[get_weather, search_web],
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions=SESSION_INSTRUCTION, allow_interruptions=True
        )

    async def on_tool_call(self, name: str, args: dict) -> Optional[str]:
        """
        Intercept tool calls for safety/confirmation, audit, and metrics.
        Return a string message to the user to block/confirm, or None to allow.
        """
        log.info("✏️ tool call requested: %s args=%s", name, args)

        if _requires_confirmation(name, args):
            return (
                "This action may be sensitive. Please confirm before I proceed: "
                f"{name} with {args}. Say 'confirm' or provide corrections."
            )
        
        return None


@asynccontextmanager
async def session_lifecycle():
    """
    Context manager so we always clean up and can add shared resources later
    (DB connections, vector store clients, telemetry exporters, etc.).
    """
    # TODO: init db/vector-store/telemetry here
    try:
        yield
    finally:
        # TODO: flush telemetry, close db, etc.
        room_context = fetch_log_context()
        log.info(
            "✏️ ending Shackleton's session for room=%s", room_context.get("room", "-")
        )
        clear_log_context()


async def entrypoint(ctx: agents.JobContext):
    room_obj = getattr(ctx, "room", None).sid or "-"
    room_id = str(room_obj)

    set_log_context(room=room_id, provider=REALTIME_PROVIDER, voice=REALTIME_VOICE)

    async with session_lifecycle():
        log.info("✏️ starting Shackleton session 🚀🚀🚀 ")

        session = AgentSession()
        input_opts = RoomInputOptions(
            video_enabled=REALTIME_VISION,
            noise_cancellation=noise_cancellation.BVC() if REALTIME_USE_BVC else None,
        )

        try:
            await session.start(
                room=ctx.room,
                agent=Assistant(),
                room_input_options=input_opts,
            )
            await ctx.connect()
            log.info("✏️ worker connected 🔗, preparing to greet👋")

            while await asyncio.sleep(60, result=True):
                log.info("✏️ Shackleton still here in room=%s, standing by 🫡")

        except Exception as e:
            log.exception(
                "✏️ fatal error in Shackleton session [room=%s]: %s", e
            )
            raise


if __name__ == "__main__":
    try:
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    except KeyboardInterrupt:
        log.info("✏️ received termination signal ⏹️; shutting down gracefully.")
    finally:
        pass
