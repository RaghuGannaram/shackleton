import asyncio

from typing import Dict, Any
from urllib.parse import quote_plus

from livekit.agents import function_tool, RunContext, ToolError

import httpx

from configs.logger import get_logger

log = get_logger()

DEFAULT_TIMEOUT_MS = 10_000
RETRY_ATTEMPTS = 1


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
