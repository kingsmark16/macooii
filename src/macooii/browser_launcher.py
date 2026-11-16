"""Open the user's regular browser without attaching to its authenticated session."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from .browser import public_url
from .privacy import TaskContext


def youtube_target(query: str, task: TaskContext) -> dict:
    """Resolve a public video link without opening an extra browser or reading account data."""
    search = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    task.check()
    try:
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            with client.stream("GET", search, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US"}) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    task.check()
                    size += len(chunk)
                    if size > 4_000_000:
                        raise ValueError("Search response too large")
                    chunks.append(chunk)
        return youtube_result(b"".join(chunks).decode("utf-8", errors="replace"), search, query)
    except (httpx.HTTPError, ValueError):
        task.check()
        return {"url": search, "title": query, "search_only": True}


def youtube_result(html: str, search: str, query: str) -> dict:
    match = re.search(r'(?:var\s+)?ytInitialData\s*=\s*', html)
    if match:
        data, _ = json.JSONDecoder().raw_decode(html[match.end():])
        primary = data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {})

        def videos(item):
            if isinstance(item, dict):
                if any(key in item for key in ("adSlotRenderer", "promotedSparklesWebRenderer", "promotedVideoRenderer")):
                    return
                video = item.get("videoRenderer", {})
                identity = video.get("videoId", "")
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", identity):
                    title = "".join(run.get("text", "") for run in video.get("title", {}).get("runs", [])) or query
                    yield {"url": "https://www.youtube.com/watch?v=" + identity + "&autoplay=1", "title": title, "search_only": False}
                for value in item.values():
                    yield from videos(value)
            elif isinstance(item, list):
                for value in item:
                    yield from videos(value)

        result = next(videos(primary), None)
        if result:
            return result
    return {"url": search, "title": query, "search_only": True}


def launch_regular_browser(apps: dict, url: str | None = None, executable: Path | None = None):
    if url:
        url = public_url(url)
    if executable is None:
        for name, value in apps.items():
            if name.casefold() in {"chrome", "google chrome", "edge", "microsoft edge"}:
                candidate = Path(value)
                if candidate.is_file() and candidate.suffix.casefold() == ".exe":
                    executable = candidate.resolve()
                    break
    if executable:
        # Omitting user-data-dir delegates profile/account selection to the regular browser.
        arguments = [str(executable), url] if url else [str(executable), "--new-window"]
        subprocess.Popen(arguments, shell=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    elif url and os.name == "nt":
        os.startfile(url)
    else:
        raise ValueError("Register Chrome or Edge in Settings first.")

