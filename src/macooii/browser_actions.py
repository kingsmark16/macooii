"""Visible, Macooii-owned browser workflows, isolated from the user's normal Chrome profile."""
from __future__ import annotations

import queue
import re
import threading
from pathlib import Path
from urllib.parse import quote_plus

from .browser import public_url
from .privacy import Cancelled, TaskContext


class ActionBrowser:
    def __init__(self, root: Path):
        self.profile = root / "browser-profile"
        self.jobs = queue.Queue()
        self.thread = None
        self.lock = threading.Lock()
        self.context = self.page = self.playwright = None

    def call(self, action: str, arguments: dict, task: TaskContext) -> dict:
        task.check()
        with self.lock:
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, daemon=True, name="Macooii browser")
                self.thread.start()
        event, box = threading.Event(), {}
        self.jobs.put((action, arguments, task, event, box))
        while not event.wait(0.1):
            task.check()
        task.check()
        if "error" in box:
            raise box["error"]
        return box["result"]

    def _run(self):
        try:
            while True:
                try:
                    job = self.jobs.get(timeout=0.05)
                except queue.Empty:
                    if self.page is not None:
                        try:
                            # Pump Playwright events so routed streaming requests keep flowing while idle.
                            self.page.wait_for_timeout(75)
                        except Exception:
                            self.page = self.context = None
                    continue
                if job is None:
                    break
                action, arguments, task, event, box = job
                try:
                    task.check()
                    if action not in {"open", "play", "control"}:
                        raise ValueError("Unsupported browser action")
                    box["result"] = getattr(self, "_" + action)(arguments, task)
                except Cancelled as exc:
                    if self.page:
                        try:
                            self.page.evaluate("document.querySelector('video')?.pause()")
                        except Exception:
                            pass
                    box["error"] = exc
                except Exception as exc:
                    box["error"] = exc if isinstance(exc, ValueError) else ValueError(
                        "Browser action failed. Check the Macooii browser window for a consent or human-check screen.")
                    if box["error"] is not exc:
                        box["error"].__cause__ = exc
                finally:
                    event.set()
        finally:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()

    def _ensure(self):
        from playwright.sync_api import Error, sync_playwright
        if self.page is not None and not self.page.is_closed():
            return self.page
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        self.profile.mkdir(parents=True, exist_ok=True)
        options = {"user_data_dir": str(self.profile), "headless": False, "locale": "en-US",
                   "accept_downloads": False, "args": ["--autoplay-policy=no-user-gesture-required"]}
        try:
            self.context = self.playwright.chromium.launch_persistent_context(channel="chrome", **options)
        except Error:
            self.context = self.playwright.chromium.launch_persistent_context(channel="msedge", **options)
        self.context.set_default_timeout(20_000)

        def guard(route):
            try:
                public_url(route.request.url)
                if route.request.method not in {"GET", "HEAD", "POST", "OPTIONS"}:
                    route.abort()
                else:
                    route.continue_()
            except Exception:
                route.abort()

        self.context.route("**/*", guard)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.on("dialog", lambda dialog: dialog.dismiss())
        self.page.on("download", lambda download: download.cancel())
        return self.page

    def _open(self, args, task):
        url = public_url(args["url"])
        page = self._ensure()
        task.check()
        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        task.check()
        public_url(page.url)
        if response and response.status >= 400:
            raise ValueError(f"The website returned HTTP {response.status}.")
        page.bring_to_front()
        # Do not send page contents, account names, or redirected OAuth URLs to the model.
        return {"opened": True, "url": url}

    def _play(self, args, task):
        query = args.get("query") or "relaxing music"
        self._open({"url": "https://www.youtube.com/results?search_query=" + quote_plus(query)}, task)
        page = self.page
        reject = page.get_by_role("button", name=re.compile(r"^Reject all$", re.I))
        if reject.count() and reject.first.is_visible():
            task.check()
            reject.first.click()
        first = page.locator('ytd-video-renderer a#video-title[href*="/watch"] ').first
        first.wait_for(state="visible", timeout=25_000)
        task.check()
        first.click()
        page.wait_for_url(re.compile(r"youtube\.com/watch\?"), timeout=25_000)
        page.locator("video").first.wait_for(state="attached")
        task.check()
        page.locator("video").first.evaluate("v => { v.muted = false; v.volume = 0.35; v.play().catch(() => {}); }")
        page.wait_for_function("(() => { const v=document.querySelector('video'); return v && !v.paused && v.readyState >= 2; })()", timeout=20_000)
        task.check()
        title = page.title().removesuffix(" - YouTube")
        return {"playing": True, "title": title, "url": page.url,
                "ad_playing": page.locator("#movie_player.ad-showing").count() > 0}

    def _control(self, args, task):
        if self.page is None or self.page.is_closed() or "youtube.com/watch" not in self.page.url:
            raise ValueError("There is no active YouTube player in the Macooii browser.")
        task.check()
        action = args["action"]
        if action not in {"pause", "resume", "stop"}:
            raise ValueError("Choose pause, resume, or stop.")
        state = self.page.locator("video").first.evaluate("""(v, action) => {
            if (action === 'resume') return v.play().then(() => ({paused:v.paused}));
            v.pause(); if (action === 'stop') v.currentTime = 0;
            return {paused:v.paused};
        }""", action)
        task.check()
        if state["paused"] != (action != "resume"):
            raise ValueError("The player did not confirm the requested playback change.")
        return {"success": True, "action": action}

    def close(self):
        if self.thread and self.thread.is_alive():
            self.jobs.put(None)
            self.thread.join(timeout=3)
