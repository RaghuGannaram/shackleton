import json
import asyncio

from typing import Dict, Any, List, Optional 
from urllib.parse import quote_plus

from livekit.agents import function_tool, RunContext, ToolError

import httpx
from ddgs import DDGS

# import os
# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText
# from typing import Optional

from configs.logger import get_logger

log = get_logger()

DEFAULT_TIMEOUT_MS = 10_000
RETRY_ATTEMPTS = 1

MAX_SEARCH_RESULTS = 10
MAX_SEARCH_TEXT_LENGTH = 1000  # chars

async def _fetch_wttr(city: str) -> str:
    url = f"https://wttr.in/{quote_plus(city)}?format=4"
    headers = {"User-Agent": "Shackleton/1.0"}
    timeout = httpx.Timeout(DEFAULT_TIMEOUT_MS / 1000.0)

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()

        return response.text.strip()


@function_tool()
async def get_weather(ctx: RunContext, city: str) -> Dict[str, Any]:
    """
    Retrieve real-time weather information for a given city using the wttr.in service.

    Input:
        - city (str): Name of the city or location to fetch the weather for
          (e.g., "Hyderabad", "New York", "Tokyo").

    Output:
        - A dictionary named `weather_info` containing the following keys:
            • ok (bool): True if the request succeeded, False otherwise.
            • city (str): The requested city name.
            • brief (str): A concise, emoji-rich weather summary from wttr.in, for example:
                "⛅️  🌡️+31°C 🌬️←18km/h"
                - Sky/condition: emoji & description (e.g., ☀️ clear, 🌧️ rain, ⛅️ partly cloudy)
                - Temperature: current temperature in Celsius (prefixed with 🌡️)
                - Wind: current wind direction and speed in km/h (prefixed with 🌬️)
            • text (str): A human-friendly message combining the city and brief weather summary,
              e.g., "The current weather in Hyderabad is ⛅️  🌡️+31°C 🌬️←18km/h."

    Notes:
        - The output is intentionally compact and readable, suitable for:
            • Voice assistants
            • Chatbot responses
            • Inline display in UIs
        - `weather_info` provides both a machine-readable format (`brief`, `city`, `ok`) and
          a human-readable string (`text`).
    """

    log.info("✏️ get_weather: fetching %s's weather", city)
    last_exc = None
    for attempt in range(1 + RETRY_ATTEMPTS):
        try:
            brief = await _fetch_wttr(city)
            
            if brief.lower().startswith(f"{city.lower()}:"):
                brief = brief[len(city) + 1 :].strip()

            text = f"The current weather in {city} is {brief}."
            weather_info = {"ok": True, "city": city, "brief": brief, "text": text}

            log.info("✏️ get_weather: response %s", repr(weather_info))

            return weather_info
        except httpx.HTTPStatusError as e:
            log.warning("✏️ get_weather: faced wttr http error %s", e.response.status_code)

            raise ToolError(f"Could not retrieve weather for {city} (status {e.response.status_code})")
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.TransportError) as e:
            last_exc = e
            log.warning("✏️ get_weather: faced wttr transient error (attempt %d): %s", attempt + 1, e)

            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(0.1 * (attempt + 1))
            else:
                break
        except Exception as e:
            last_exc = e
            log.exception("✏️ get_weather: faced unexpected error %s", e)

            raise ToolError("Unexpected error fetching weather")

    raise ToolError(f"Network trouble fetching weather for {city}: {last_exc}")

def _ddg_search(query, region="in", max_results=MAX_SEARCH_RESULTS):
    search_results = []
    with DDGS() as ddgs:
        for result in ddgs.text(query, region=region, safesearch="Off"):
            search_results.append({
                "title": result.get("title"),
                "url": result.get("href"),
                "snippet": result.get("body")
            })
            if len(search_results) >= max_results:
                break
    return search_results


def _format_search_results(raw_results: List[Dict[str, Any]], limit: int = MAX_SEARCH_RESULTS) -> List[Dict[str, Any]]:
    out = []
    for i, result in enumerate(raw_results[:limit]):
        out.append({
            "rank": i + 1,
            "title": result.get("title") or result.get("heading") or "",
            "link": result.get("link") or result.get("url") or "",
            "snippet": (result.get("snippet") or result.get("body") or "")[:MAX_SEARCH_TEXT_LENGTH]
        })
    return out


@function_tool()
async def search_web(ctx: RunContext, query: str) -> str:
    """
    Perform a web search using DuckDuckGo and return structured results.

    Input:
        - query (str): The search query string.

    Output:
        - Dictionary `search_info` containing:
            • ok (bool): True if search succeeded, False otherwise.
            • query (str): The original search query.
            • results (List[Dict]): A list of formatted search results, each containing:
                • rank (int): Result ranking starting at 1.
                • title (str): The result title.
                • link (str): The result URL.
                • snippet (str): Short snippet/description of the result (max 500 chars).

    Notes:
        - `search_info` provides both machine-readable structured data (`results`) and
          a human-friendly summary (`title` + `snippet`) for display or LLM consumption.
        - Handles timeouts, network errors, and internal exceptions gracefully.
    """
    log.debug("✏️ search_web: searching for %s", query)
    last_exc = None
    for attempt in range(1 + RETRY_ATTEMPTS):
        try:
            raw_results = await asyncio.wait_for(
                asyncio.to_thread(lambda: _ddg_search(query)),
                timeout=DEFAULT_TIMEOUT_MS
            )

            if isinstance(raw_results, str):
                try:
                    parsed = json.loads(raw_results)
                except Exception:
                    parsed = [{"title": query, "link": "", "snippet": raw_results}]
            else:
                parsed = raw_results

            results = _format_search_results(parsed, limit=MAX_SEARCH_RESULTS)

            search_info = {"ok": True, "query": query, "results": results}
            log.info("✏️ search_web: fetched search results %s", repr(search_info))

            return search_info
        except asyncio.TimeoutError as e:
            last_exc = e
            log.warning("✏️ search_web: faced timeout error (attempt %d)", attempt + 1)

            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(0.2 * (attempt + 1))
            else:
                break
        except Exception as e:
            last_exc = e
            log.exception("✏️ search_web: faced unexpected error %s", e)

            raise ToolError("Unexpected error searching web")

    raise ToolError(f"Network trouble searching web for {query}: {last_exc}")


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
