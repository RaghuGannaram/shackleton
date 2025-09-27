import json
import asyncio

from typing import Dict, Any, List
from urllib.parse import quote_plus

from livekit.agents import function_tool, RunContext, ToolError

from ddgs import DDGS

from configs.logger import get_logger

log = get_logger()

DEFAULT_TIMEOUT_MS = 10_000
RETRY_ATTEMPTS = 1

MAX_SEARCH_RESULTS = 20
MAX_SEARCH_TEXT_LENGTH = 2000  # chars

def _ddg_search(query, region="in", max_results=MAX_SEARCH_RESULTS):
    search_results = []
    with DDGS() as ddgs:
        for result in ddgs.text(query, region=region, safesearch="Off"):
            print(f"{result}\n\n")
            search_results.append({
                "title": result.get("title"),
                "url": result.get("href"),
                "snippet": result.get("body")
            })
            if len(search_results) >= max_results:
                break
    return search_results


def _format_search_results(raw_results: List[Dict[str, Any]], limit: int = MAX_SEARCH_TEXT_LENGTH) -> List[Dict[str, Any]]:
    formatted_results = []
    for i, result in enumerate(raw_results[:limit]):
        formatted_results.append({
            "rank": i + 1,
            "title": result.get("title") or result.get("heading") or "",
            "link": result.get("url") or result.get("link") or "",
            "snippet": (result.get("snippet") or result.get("body") or "")[:MAX_SEARCH_TEXT_LENGTH]
        })
    return formatted_results


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
                    parsed_results = json.loads(raw_results)
                except Exception:
                    parsed_results = [{"title": query, "link": "", "snippet": raw_results}]
            else:
                parsed_results = raw_results

            results = _format_search_results(parsed_results)

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



# if(__name__ == "__main__"):
#     import asyncio

#     async def main():
#         result =  _ddg_search("What happened in the ap assembly yesterday? what idi balakrishna said")
#         # print(result)

#     asyncio.run(main())