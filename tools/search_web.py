import os
import sys
import time
import json
import asyncio
import aiohttp
import hashlib
import random
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode

from livekit.agents import function_tool, ToolError
from ddgs import DDGS

from configs.settings import settings
from configs.logger import get_logger

log = get_logger()

# -------------------------
# Configurable constants
# -------------------------
JINA_API_KEY = settings.JINA_API_KEY

# DDGS (DuckDuckGo) settings
DDGS_FETCH_TIMEOUT_S = 10.0
DDGS_FETCH_RETRIES = 2
DDGS_MAX_RESULTS = 20
DDGS_MAX_SNIPPET_CHARS = 2_000
DDGS_TOP_K_RESULTS = 2  # how many to deep-fetch with Jina by default

# Jina Reader settings
JINA_READER_URL = "https://r.jina.ai"
JINA_FETCH_TIMEOUT_S = 30.0
JINA_FETCH_RETRIES = 2
JINA_MAX_CONCURRENCY = 3
JINA_MAX_TEXT_CHARS = 20_000
JINA_CACHE_DIR = "./temp/jina_reader_cache"
JINA_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 hours

os.makedirs(JINA_CACHE_DIR, exist_ok=True)


# -------------------------
# Helper: DDGS (discovery)
# -------------------------
def _ddg_search(query: str, region: str = "in", max_results: int = DDGS_MAX_RESULTS) -> List[Dict[str, Any]]:
    """
    Synchronous DDGS call. Caller should wrap in to_thread for async use.
    Returns a list of raw results with keys: title, link, snippet.
    """
    results: List[Dict[str, Any]] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, region=region, safesearch="Off"):
            # debug print is optional; keep for local debugging but not for prod logs
            # print(f"{item}\n\n")
            results.append({
                "title": item.get("title"),
                "link": item.get("href"),
                "snippet": item.get("body")
            })
            if len(results) >= max_results:
                break
    return results


def _format_ddgs_search_results(raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    formatted: List[Dict[str, Any]] = []
    for i, r in enumerate(raw_results[:DDGS_MAX_RESULTS]):
        formatted.append({
            "rank": i + 1,
            "title": r.get("title") or r.get("heading") or "",
            "link": r.get("link") or r.get("url") or "",
            "snippet": (r.get("snippet") or r.get("body") or "")[:DDGS_MAX_SNIPPET_CHARS]
        })
    return formatted


def _score_ddgs_result(query: str, result: Dict[str, Any]) -> float:
    title = (result.get("title") or "").lower()
    snippet = (result.get("snippet") or "").lower()
    q_terms = [t.strip().lower() for t in query.split() if t.strip()]
    overlap = sum(1 for t in q_terms if t in title or t in snippet) if q_terms else 0.0
    length_bonus = min(len(snippet), 800) / 800.0
    rank = float(result.get("rank", 9999))
    rank_bonus = 1.0 / (1.0 + rank / 10.0)

    score = overlap * 2.0 + length_bonus + rank_bonus
    return float(score)


def _extract_ddgs_top_results(query: str, results: List[Dict[str, Any]], k: int = DDGS_TOP_K_RESULTS) -> List[Dict[str, Any]]:
    scored: List[tuple] = []
    for r in results:
        try:
            s = _score_ddgs_result(query, r)
        except Exception:
            s = 0.0
        scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [r for (_, r) in scored[:k]]
    return top


# -------------------------
# Helper: Jina Reader cache
# -------------------------
def _cache_key_for_url(url: str) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return os.path.join(JINA_CACHE_DIR, f"{h}.json")


def _read_cache(url: str) -> Optional[Dict[str, Any]]:
    path = _cache_key_for_url(url)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        fetched_at = data.get("_fetched_at", 0)
        if time.time() - fetched_at > JINA_CACHE_TTL_SECONDS:
            try:
                os.remove(path)
            except Exception:
                pass
                log.exception("search_web: failed to remove stale cache file %s", path)
            return None
        return data
    except Exception:
        log.exception("search_web: failed to read cache for %s", url)
        return None


def _write_cache(url: str, payload: Dict[str, Any]) -> None:
    path = _cache_key_for_url(url)
    payload["_fetched_at"] = time.time()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
    except Exception:
        pass
        log.exception("search_web: failed to write cache for %s", url)


# -------------------------
# Helper: Jina Reader fetch
# -------------------------
async def _fetch_jina_reader(session: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
    """
    Fetch a single URL via Jina Reader (r.jina.ai/?url=...).
    Returns consistent dict:
      {"ok": bool, "url": str, "status": Optional[int], "content": Optional[str], "error": Optional[str], "cached": Optional[bool]}
    """
    url_to_fetch = (url or "").strip()
    if not url_to_fetch:
        return {"ok": False, "url": url, "error": "empty url"}

    # Cache
    cached = _read_cache(url_to_fetch)
    if cached:
        log.debug("search_web: Jina cache hit for %s", url_to_fetch)
        return {"ok": True, "url": url_to_fetch, "content": cached.get("content", ""), "cached": True}

    endpoint = f"{JINA_READER_URL}/{url_to_fetch}"
    last_exc: Optional[BaseException] = None
    max_attempts = JINA_FETCH_RETRIES

    for attempt in range(1, max_attempts + 1):
        try:
            headers = {}
            if JINA_API_KEY:
                headers["Authorization"] = f"Bearer {JINA_API_KEY}"

            timeout = aiohttp.ClientTimeout(total=JINA_FETCH_TIMEOUT_S)
            async with session.get(endpoint, headers=headers, timeout=timeout) as resp:
                status = resp.status

                if status == 200:
                    text = await resp.text()
                    trimmed = text[:JINA_MAX_TEXT_CHARS]
                    payload = {"status": status, "content": trimmed}
                    _write_cache(url_to_fetch, payload)
                    log.debug("search_web: Jina fetched and cached %d chars for %s (attempt %d/%d)", len(trimmed), url_to_fetch, attempt, max_attempts)
                    return {"ok": True, "status": status, "url": url_to_fetch, "content": trimmed}

                if status in (429, 502, 503, 504):
                    last_exc = Exception(f"HTTP {status}")
                    # exponential backoff with jitter
                    backoff = min(10.0, 2 ** (attempt - 1))
                    jitter = random.uniform(0, 0.5)
                    wait = backoff + jitter
                    log.warning("search_web: transient Jina status %s for %s (attempt %d/%d), sleeping %.2fs", status, url_to_fetch, attempt, max_attempts, wait)
                    await asyncio.sleep(wait)
                    continue

                # Non-retryable non-200
                body = await resp.text()
                log.warning("search_web: Jina fetch failed (status=%s) for %s: %s", status, url_to_fetch, body[:400])
                return {"ok": False, "url": url_to_fetch, "status": status, "error": body}

        except asyncio.TimeoutError as te:
            last_exc = te
            log.warning("search_web: Jina fetch timeout for %s (attempt %d/%d): %s", url_to_fetch, attempt, max_attempts, te)
            await asyncio.sleep(min(10.0, 0.5 * attempt))
            continue

        except aiohttp.ClientError as ce:
            last_exc = ce
            log.warning("search_web: Jina fetch network error for %s (attempt %d/%d): %s", url_to_fetch, attempt, max_attempts, ce)
            await asyncio.sleep(min(10.0, 0.5 * attempt))
            continue

        except Exception as e:
            last_exc = e
            log.exception("search_web: unexpected error fetching %s (attempt %d/%d): %s", url_to_fetch, attempt, max_attempts, e)
            break

    err_msg = f"failed after {max_attempts} attempts: {repr(last_exc)}"
    log.error("search_web: Jina fetch ultimately failed for %s: %s", url_to_fetch, err_msg)
    return {"ok": False, "url": url_to_fetch, "error": err_msg}


async def _select_and_fetch_with_jina(query: str, ddgs_results: List[Dict[str, Any]], k: int = DDGS_TOP_K_RESULTS) -> List[Dict[str, Any]]:
    """
    Given DDGS-formatted results, select top-K and fetch their full text via Jina.
    Returns a list of fetch results in the same order as selected.
    """
    # select top-k using scoring (ensures we fetch the best K)
    top_candidates = _extract_ddgs_top_results(query, ddgs_results, k=k)

    sem = asyncio.Semaphore(JINA_MAX_CONCURRENCY)
    async with aiohttp.ClientSession() as session:

        async def guarded_fetch(res: Dict[str, Any]):
            async with sem:
                url = res.get("link") or res.get("url") or ""
                return await _fetch_jina_reader(session, url)

        tasks = [asyncio.create_task(guarded_fetch(r)) for r in top_candidates]
        results = await asyncio.gather(*tasks, return_exceptions=False)
    return results


# -------------------------
# Public tool: search_web
# -------------------------
@function_tool()
async def search_web(query: str) -> Dict[str, Any]:
    """
    Discover with DDGS -> select -> deep-fetch with Jina (bounded).
    Returns structured search_info:
      {"ok": bool, "query": str, "results": [...], "errors": [...]}
    Each result: {rank, title, link, snippet, reader: {ok, status, content, cached, error} | None}
    """
    log.info("✏️ search_web: searching for %s", query)
    last_exc: Optional[BaseException] = None
    raw_results: Optional[List[Dict[str, Any]]] = None

    # DDGS discovery with retries
    max_attempts = DDGS_FETCH_RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            raw_results = await asyncio.wait_for(
                asyncio.to_thread(lambda: _ddg_search(query)),
                timeout=DDGS_FETCH_TIMEOUT_S
            )

            if isinstance(raw_results, str):
                try:
                    parsed = json.loads(raw_results)
                except Exception:
                    parsed = [{"title": query, "link": "", "snippet": raw_results}]
                raw_results = parsed

            # format and select
            formatted = _format_ddgs_search_results(raw_results)
            top_results = _extract_ddgs_top_results(query, formatted, k=DDGS_TOP_K_RESULTS)
            break  # successful discovery

        except asyncio.TimeoutError as te:
            last_exc = te
            log.warning("✏️ search_web: DDGS timeout (attempt %d/%d): %s", attempt, max_attempts, te)
            if attempt < max_attempts:
                await asyncio.sleep(0.2 * attempt)
                continue
            else:
                break

        except Exception as e:
            last_exc = e
            log.exception("✏️ search_web: unexpected error calling DDGS: %s", e)
            raise ToolError("Unexpected error searching web") from e

    if not raw_results:
        err = f"ddgs failed after attempts: {repr(last_exc)}"
        log.error("✏️ search_web: no ddgs results for '%s': %s", query, err)
        return {"ok": False, "query": query, "results": [], "errors": [err]}

    # We have formatted results; pick top K and fetch via Jina
    formatted_results = _format_ddgs_search_results(raw_results)

    # Deep-fetch selected pages with Jina (bounded concurrency)
    try:
        jina_fetch_results = await _select_and_fetch_with_jina(query, formatted_results, k=DDGS_TOP_K_RESULTS)
    except Exception as e:
        log.exception("✏️ search_web: jina fetch phase failed: %s", e)
        jina_fetch_results = []

    # Map jina results by URL for easy enrichment
    indepth_results: Dict[str, Dict[str, Any]] = {}
    for r in jina_fetch_results:
        if isinstance(r, dict):
            indepth_results[r.get("url")] = r

    enriched_results = []
    for result in formatted_results:
        link = result.get("link")
        indepth_result = indepth_results.get(link)
        built_result = dict(result)
        if indepth_result:
            built_result["indepth"] = {
                "ok": indepth_result.get("ok", False),
                "status": indepth_result.get("status"),
                "content": indepth_result.get("content"),
                "error": indepth_result.get("error"),
                "cached": indepth_result.get("cached", False)
            }
        else:
            built_result["indepth"] = None
        enriched_results.append(built_result)

    log.info("✏️ search_web: completed search for '%s' with %d results (%d fetched in-depth)", query, len(enriched_results), len(jina_fetch_results))
    return {"ok": True, "query": query, "results": enriched_results, "errors": []}


# -------------------------
# Optional local test harness
# -------------------------
# if __name__ == "__main__":
#     async def main():
#         q = "What happened in the AP assembly yesterday? what did Balakrishna say about Chiranjeevi and Jagan?"
#         try:
#             result = await search_web(q)
#             log.debug(json.dumps(result, indent=2, ensure_ascii=False)[:100000])
#         except Exception as e:
#             log.exception("Error:", e)

#     asyncio.run(main())
