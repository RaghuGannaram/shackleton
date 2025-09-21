from __future__ import annotations

import os
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions

# from livekit.plugins import openai
from livekit.plugins import google
from livekit.plugins import noise_cancellation

from configs.settings import settings
from configs.logger import init_logger, get_logger, set_log_context, clear_log_context
from tools.tools import get_weather, search_web, send_email
from prompts.instructions import (
    AGENT_INSTRUCTION,
    SESSION_INSTRUCTION,
    FAREWELL_INSTRUCTION,
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
SENSITIVE_TOOLS = {"send_email"}
REQUIRE_CONFIRM_SENSITIVE = (
    os.getenv("REQUIRE_CONFIRM_SENSITIVE", "true").lower() == "true"
)

log = init_logger(
    log_level=LOG_LEVEL,
    log_dir=LOG_DIR,
    log_file=LOG_FILE,
    max_bytes=LOG_MAX_BYTES,
    backups=LOG_BACKUP_COUNT,
)


def requires_confirmation(tool_name: str, args: dict) -> bool:
    if not REQUIRE_CONFIRM_SENSITIVE:
        return False
    return tool_name in SENSITIVE_TOOLS


def build_realtime_model():
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
        # return openai.realtime.RealtimeModel(
        #     voice=VOICE,
        #     temperature=TEMP,
        # )
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
        tools = [get_weather, search_web, send_email]

        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=build_realtime_model(),
            tools=tools,
        )

    async def on_tool_call(self, name: str, args: dict) -> Optional[str]:
        """
        Intercept tool calls for safety/confirmation, audit, and metrics.
        Return a string message to the user to block/confirm, or None to allow.
        """
        log.info("tool call requested: %s args=%s", name, args)

        if requires_confirmation(name, args):
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
        pass


async def entrypoint(ctx: agents.JobContext):
    try:
        rid = getattr(ctx, "room", None) or "-"
    except Exception:
        rid = "-"
    set_log_context(room=rid, provider=REALTIME_PROVIDER, voice=REALTIME_VOICE)

    async with session_lifecycle():
        session = AgentSession()
        log.info("starting Shackleton session 🚀")

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

            log.info("worker connected 🔗; generating opening reply")
            await session.generate_reply(instructions=SESSION_INSTRUCTION)

            # The session now streams audio both ways and reacts in real time.
            # If you want background tasks, you could await an Event or sleep forever:
            # while await asyncio.sleep(60, result=True):
            #     # TODO: proactive checks / heartbeats / periodic summaries
            #     pass

        except Exception as e:
            explanation = user_friendly_error(e)

            await session.generate_reply(
                instructions=(
                    f"I ran into a problem: {explanation} "
                    "I'll steady things on my end and try again shortly."
                )
            )

            log.exception("fatal error in Shackleton session [room=%s]: %s", rid, e)

            raise
        finally:
            try:
                await session.generate_reply(instructions=FAREWELL_INSTRUCTION)
            except Exception:
                log.warning("could not send closing message for room=%s", rid)

            log.info("ending Shackleton's session for room=%s", rid)


def user_friendly_error(e: Exception) -> str:
    s = str(e).lower()
    if "network" in s or "connection" in s:
        return "It looks like there was a network connection issue."
    if "timeout" in s:
        return "One of my tools took too long to respond."
    if "authentication" in s or "unauthorized" in s:
        return "There was an authentication issue while accessing a service."
    if "not found" in s:
        return "I couldn't find the resource I was expecting."
    return "Something unexpected happened while I was working on your request."


if __name__ == "__main__":
    try:
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    except KeyboardInterrupt:
        log.info("received termination signal ⏹️; shutting down gracefully.")
    finally:
        pass
