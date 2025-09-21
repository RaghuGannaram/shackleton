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

from utils.logger import init_logger, get_logger, set_log_context, clear_log_context
from prompts.instructions import AGENT_INSTRUCTION, SESSION_INSTRUCTION, FAREWELL_INSTRUCTION
from tools.tools import get_weather, search_web, send_email

load_dotenv()


# agent configs
PROVIDER     = os.getenv("REALTIME_PROVIDER", "google").lower()  # "google" | "openai" | "pipeline"
VOICE        = os.getenv("REALTIME_VOICE", "Fenrir") # "Charon" | "Fenrir" | "Sadachbia" | "Enceladus" | "Orus"
TEMP         = float(os.getenv("REALTIME_TEMP", "0.8"))
ALLOW_VISION = os.getenv("ALLOW_VISION", "true").lower() == "true"
USE_BVC      = os.getenv("USE_BVC", "true").lower() == "true"

# logger configs
LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO").upper()  # "ERROR" | "WARNING" | "INFO" | "DEBUG"
LOG_DIR      = os.getenv("LOG_DIR", "./logs")
LOG_FILE     = os.getenv("LOG_FILE", "output.log")
MAX_BYTES    = int(os.getenv("LOG_MAX_BYTES", "5_242_880"))  # ~5MB
BACKUPS      = int(os.getenv("LOG_BACKUP_COUNT", "5"))       # keep 5 rotated files

# gaurdrails for sensitive tools
SENSITIVE_TOOLS = {"send_email"}
REQUIRE_CONFIRM_SENSITIVE = (os.getenv("REQUIRE_CONFIRM_SENSITIVE", "true").lower() == "true")

log = init_logger(
    log_level=LOG_LEVEL,
    log_dir=LOG_DIR,
    log_file=LOG_FILE,
    max_bytes=MAX_BYTES,
    backups=BACKUPS,
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

    if PROVIDER == "google":
        # Gemini Realtime: single model for STT -> Think -> TTS
        return google.beta.realtime.RealtimeModel(
            voice=VOICE,
            temperature=TEMP,
        )
    elif PROVIDER == "openai":
        # OpenAI Realtime: single model for STT -> Think -> TTS
        # return openai.realtime.RealtimeModel(
        #     voice=VOICE,
        #     temperature=TEMP,
        # )
        raise NotImplementedError("OpenAI Realtime provider not wired yet.")
    elif PROVIDER == "pipeline":
        # TODO: Build modular pipeline (TTS (Whisper) -> LLM (OpenAI) -> TTS (Piper)) here.
        raise NotImplementedError("Pipeline provider not wired yet.")
    else:
        raise ValueError(f"Unknown REALTIME_PROVIDER: {PROVIDER}")


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
            return ("This action may be sensitive. Please confirm before I proceed: " 
                    f"{name} with {args}. Say 'confirm' or provide corrections.")
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
    set_log_context(room=rid, provider=PROVIDER, voice=VOICE)

    async with session_lifecycle():
        session = AgentSession()
        log.info("starting Shackleton session 🚀")

        input_opts = RoomInputOptions(
            video_enabled=ALLOW_VISION,
            noise_cancellation=noise_cancellation.BVC() if USE_BVC else None,
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
            error_msg = str(e).lower()

            if "network" in error_msg or "connection" in error_msg:
                explanation = "It looks like there was a network connection issue."
            elif "timeout" in error_msg:
                explanation = "One of my tools took too long to respond."
            elif "authentication" in error_msg or "unauthorized" in error_msg:
                explanation = "There was an authentication issue while accessing a service."
            elif "not found" in error_msg:
                explanation = "I couldn't find the resource I was expecting."
            else:
                explanation = "Something unexpected happened while I was working on your request."

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


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
