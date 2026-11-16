from __future__ import annotations

import ipaddress
import socket
from urllib.parse import quote_plus, urlparse

from .privacy import TaskContext


def public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP/HTTPS pages without embedded credentials are supported.")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Only standard public web ports are allowed.")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Local, private, and reserved network addresses cannot be browsed.")
    return url


class Browser:
    """Short-lived, unauthenticated Chrome contexts. No personal browser profile is read."""

    def _visit(self, url: str, task: TaskContext, search: bool = False) -> dict:
        from playwright.sync_api import Error, TimeoutError, sync_playwright

        task.check()
        public_url(url)
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel="chrome", headless=True,
                                                      args=["--disable-features=Translate"])
            except Error:
                try:
                    browser = playwright.chromium.launch(channel="msedge", headless=True)
                except Error as exc:
                    raise RuntimeError("Chrome or Edge is required for browser research.") from exc
            context = browser.new_context(accept_downloads=False, service_workers="block")
            context.set_default_timeout(15_000)

            def guard(route):
                try:
                    task.check()
                    if route.request.resource_type in {"image", "media", "font", "websocket"}:
                        route.abort()
                        return
                    public_url(route.request.url)
                    if route.request.method not in {"GET", "HEAD"}:
                        route.abort()
                    else:
                        route.continue_()
                except Exception:
                    route.abort()

            context.route("**/*", guard)
            page = context.new_page()
            page.on("dialog", lambda dialog: dialog.dismiss())
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                task.check()
                if response and response.status >= 400:
                    raise ValueError(f"The website returned HTTP {response.status}. Try another source.")
                text = page.locator("body").inner_text(timeout=15_000)
                if any(phrase in text[:3000].casefold() for phrase in
                       ("verify you are human", "unusual traffic", "complete the captcha", "challenge-platform")):
                    raise ValueError("This page needs a human check. Open it in your browser or choose another source.")
                final_url = public_url(page.url)
                if search:
                    links = page.locator("li.b_algo h2 a").evaluate_all(
                        "els => els.slice(0, 6).map(a => ({title: a.textContent, url: a.href}))")
                    if not links:
                        raise ValueError("Search returned no readable results. Try another query or provide a URL.")
                    return {"results": links, "url": final_url}
                # Remove navigation, scripts, forms and hidden boilerplate before extracting source text.
                page.locator("script,style,nav,footer,header,form,aside").evaluate_all("els => els.forEach(e => e.remove())")
                body = page.locator("main,article").first
                if body.count() == 0:
                    body = page.locator("body")
                text = body.inner_text()[:16_000]
                if not text.strip():
                    raise ValueError("This page has no readable text. Try another source.")
                return {"title": page.title(), "url": final_url, "text": text, "truncated": len(text) >= 16_000}
            except TimeoutError as exc:
                raise ValueError("The page timed out. Try again or provide a different URL.") from exc
            finally:
                context.close()
                browser.close()

    def search(self, query: str, task: TaskContext) -> dict:
        return self._visit("https://www.bing.com/search?q=" + quote_plus(query), task, search=True)

    def read(self, url: str, task: TaskContext) -> dict:
        return self._visit(url, task)
