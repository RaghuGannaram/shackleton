import asyncio
import json
import httpx
from typing import Dict, Any, List 
from urllib.parse import quote_plus

from livekit.agents import function_tool, RunContext

from langchain_community.tools import DuckDuckGoSearchRun
# import os
# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText
# from typing import Optional

from configs.logger import get_logger

log = get_logger()

DEFAULT_TIMEOUT_MS = 5000
RETRY_ATTEMPTS = 1

MAX_SEARCH_RESULTS = 5

def _ok(payload: Dict[str, Any]) -> str:
    """LLM-friendly structured success."""

    return json.dumps({"ok": True, **payload})


def _err(type: str, message: str, **extra) -> str:
    """LLM-friendly structured error."""

    payload = {"ok": False, "error": {"type": type, "message": message}}
    if extra:
        payload["error"].update(extra)

    return json.dumps(payload)


async def _fetch_wttr(city: str) -> str:
    url = f"https://wttr.in/{quote_plus(city)}?format=4"
    headers = {"User-Agent": "Shackleton/1.0"}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_MS / 1000, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()

        return response.text.strip()

def _format_search_results(raw_results: List[Dict[str, Any]], limit: int = MAX_SEARCH_RESULTS) -> List[Dict[str, Any]]:
    out = []
    for i, r in enumerate(raw_results[:limit]):
        out.append({
            "rank": i + 1,
            "title": r.get("title") or r.get("heading") or "",
            "link": r.get("link") or r.get("url") or "",
            "snippet": (r.get("snippet") or r.get("body") or "")[:500]  # keep snippet short
        })
    return out

@function_tool()
async def get_weather(ctx: RunContext, city: str) -> str:
    """
    Retrieve real-time weather information for a given city using the wttr.in service.

    Input:
        - city (str): Name of the city or location to fetch the weather for
          (e.g., "Hyderabad", "New York", "Tokyo").

    Output:
        - A concise, emoji-rich weather summary string returned directly from wttr.in,
          for example:
              "{Hyderabad}: ⛅️  🌡️+31°C 🌬️←18km/h"

          • Location name: the requested city
          • Sky/condition: emoji & description (e.g., ☀️ clear, 🌧️ rain, ⛅️ partly cloudy, etc..)
          • Temperature: current temperature in Celsius (prefixed with 🌡️)
          • Wind: current wind direction and speed in km/h (prefixed with 🌬️)

    Notes:
        - The output is intentionally compact and human-friendly, designed to be read
          aloud by a voice assistant or shown inline in chat.
    """
    last_exc = None
    for attempt in range(1 + RETRY_ATTEMPTS):
        try:
            response = await _fetch_wttr(city)
            log.info("✏️ weather update for %s: %s", city, response)

            return _ok({"city": city, "brief": response})
        except httpx.HTTPStatusError as e:
            log.warning("✏️ wttr http %s for %s", e.response.status_code, city)

            return _err("http_error", f"Could not retrieve weather for {city}", status_code=e.response.status_code)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.TransportError) as e:
            last_exc = e
            log.warning("✏️ wttr transient error (attempt %d): %s", attempt + 1, e)

            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(0.1 * (attempt + 1))
            else:
                break
        except Exception as e:
            log.exception("✏️ unexpected error retrieving weather for %s: %s", city, e)

            return _err("internal_error", f"Failed to fetch weather for {city}")

    return _err("network_error", f"Network trouble fetching weather for {city}", detail=str(last_exc) if last_exc else None)


@function_tool()
async def search_web(ctx: RunContext, query: str) -> str:
    last_exc = None
    for attempt in range(1 + RETRY_ATTEMPTS):
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(lambda: DuckDuckGoSearchRun().run(tool_input=query)),
                timeout=DEFAULT_TIMEOUT_MS
            )

            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = [{"title": query, "link": "", "snippet": raw}]
            else:
                parsed = raw

            results = _format_search_results(parsed, limit=MAX_SEARCH_RESULTS)
            log.info("✏️ search '%s' -> %d results (showing %d)", query, len(parsed), len(results))
            
            return _ok({"query": query, "results": results})
        except asyncio.TimeoutError as e:
            last_exc = e
            log.warning("✏️ search timeout for '%s' (attempt %d)", query, attempt + 1)
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(0.2 * (attempt + 1))
            else:
                return _err("timeout", f"Search timed out for query: {query}")
        except Exception as e:
            last_exc = e
            log.exception("✏️ unexpected error searching web for '%s': %s", query, e)
            return _err("internal_error", f"Failed to search web for {query}", detail=str(e))

    return _err("network_error", f"Network trouble during search for {query}", detail=str(last_exc) if last_exc else None)


# @function_tool()
# async def send_email(
#     context: RunContext,  # type: ignore
#     to_email: str,
#     subject: str,
#     message: str,
#     cc_email: Optional[str] = None
# ) -> str:
#     """
#     Send an email through Gmail.

#     Args:
#         to_email: Recipient email address
#         subject: Email subject line
#         message: Email body content
#         cc_email: Optional CC email address
#     """
#     try:
#         # Gmail SMTP configuration
#         smtp_server = "smtp.gmail.com"
#         smtp_port = 587

#         # Get credentials from environment variables
#         gmail_user = os.getenv("GMAIL_USER")
#         gmail_password = os.getenv("GMAIL_APP_PASSWORD")  # Use App Password, not regular password

#         if not gmail_user or not gmail_password:
#             log.error("Gmail credentials not found in environment variables")
#             return "Email sending failed: Gmail credentials not configured."

#         # Create message
#         msg = MIMEMultipart()
#         msg['From'] = gmail_user
#         msg['To'] = to_email
#         msg['Subject'] = subject

#         # Add CC if provided
#         recipients = [to_email]
#         if cc_email:
#             msg['Cc'] = cc_email
#             recipients.append(cc_email)

#         # Attach message body
#         msg.attach(MIMEText(message, 'plain'))

#         # Connect to Gmail SMTP server
#         server = smtplib.SMTP(smtp_server, smtp_port)
#         server.starttls()  # Enable TLS encryption
#         server.login(gmail_user, gmail_password)

#         # Send email
#         text = msg.as_string()
#         server.sendmail(gmail_user, recipients, text)
#         server.quit()

#         log.info(f"Email sent successfully to {to_email}")
#         return f"Email sent successfully to {to_email}"

#     except smtplib.SMTPAuthenticationError:
#         log.error("Gmail authentication failed")
#         return "Email sending failed: Authentication error. Please check your Gmail credentials."
#     except smtplib.SMTPException as e:
#         log.error(f"SMTP error occurred: {e}")
#         return f"Email sending failed: SMTP error - {str(e)}"
#     except Exception as e:
#         log.error(f"Error sending email: {e}")
#         return f"An error occurred while sending email: {str(e)}"
