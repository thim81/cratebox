"""Google Images adapter using a dedicated local Chrome CDP session."""

import atexit
import json
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen
from threading import Lock

_SEARCH_LOCK = Lock()
_CHROME_PROFILE = Path("/tmp/cratedeck-chrome")
_DEVTOOLS_PORT_FILE = _CHROME_PROFILE / "DevToolsActivePort"
_CHROME_PROCESS: subprocess.Popen | None = None


def _stop_owned_chrome() -> None:
    if _CHROME_PROCESS and _CHROME_PROCESS.poll() is None:
        _CHROME_PROCESS.terminate()


atexit.register(_stop_owned_chrome)


def _web_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        parsed.port
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
        )
    except ValueError:
        return False


def search_google_images(query: str, *, limit: int = 24) -> list[dict[str, str]]:
    """Read Google Images results from a dedicated, visible Chrome CDP session."""
    from playwright.sync_api import sync_playwright

    search_url = "https://www.google.com/search?" + urlencode({"udm": "2", "q": query})
    results = []
    seen = set()
    with _SEARCH_LOCK, sync_playwright() as playwright:
        endpoint = _ensure_chrome()
        browser = playwright.chromium.connect_over_cdp(
            endpoint, no_defaults=True, timeout=10000
        )
        try:
            context = browser.contexts[0]
            page = next(
                (tab for tab in context.pages if urlsplit(tab.url).hostname == "www.google.com"),
                None,
            ) or next(
                (tab for tab in context.pages if tab.url in {"about:blank", "chrome://newtab/"}),
                None,
            ) or context.new_page()
            _minimize_chrome_window(browser, page)
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            reject_cookies = page.get_by_role("button", name="Reject all", exact=True)
            if reject_cookies.count() and reject_cookies.is_visible():
                reject_cookies.click(timeout=3000)

            cards = page.locator('[role="button"]:has(img[src*="encrypted-tbn"])')
            try:
                cards.first.wait_for(state="visible", timeout=12000)
            except Exception as exc:
                title = page.title()
                page_text = " ".join(page.locator("body").inner_text(timeout=2000).split())[:240]
                if (
                    "unusual traffic" in page_text.lower()
                    or page.locator('iframe[title="Captcha"]').count()
                ):
                    raise RuntimeError(
                        "Google requires a human verification for this search. The minimized "
                        "Chrome window has been left open for you to review."
                    ) from exc
                raise RuntimeError(
                    f"Google Images cards unavailable (title={title!r}, cards={cards.count()}, "
                    f"images={page.locator('img').count()}, page_text={page_text!r})"
                ) from exc

            for _ in range(3):
                if cards.count() >= limit:
                    break
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(400)

            for index in range(cards.count()):
                card = cards.nth(index)
                image = card.locator('img[src*="encrypted-tbn"]').first
                image_url = image.get_attribute("src") or ""
                title = (image.get_attribute("alt") or image.get_attribute("title") or "").strip()
                if not title or not _web_url(image_url) or urlsplit(image_url).scheme != "https":
                    continue
                if image_url in seen:
                    continue

                results.append({
                    "title": title[:300],
                    "image_url": image_url,
                    "thumbnail_url": image_url,
                    "source_url": search_url,
                    "source": "Google Images",
                })
                seen.add(image_url)
                if len(results) >= limit:
                    break
        finally:
            browser.close()
    return results


def _ensure_chrome() -> str:
    """Connect to the dedicated CDP profile, starting Chrome when needed."""
    global _CHROME_PROCESS

    endpoint = _existing_chrome_endpoint()
    if endpoint:
        return endpoint

    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.is_file():
        raise RuntimeError("Google Chrome is required for Google Images search")

    _CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
    _DEVTOOLS_PORT_FILE.unlink(missing_ok=True)
    _CHROME_PROCESS = subprocess.Popen(
        [
            str(chrome),
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={_CHROME_PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-startup-window",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(60):
        if _CHROME_PROCESS.poll() is not None:
            raise RuntimeError("Could not start the dedicated Google Chrome browser")
        endpoint = _existing_chrome_endpoint()
        if endpoint:
            return endpoint
        time.sleep(0.25)
    raise RuntimeError("Timed out starting the dedicated Google Chrome browser")


def _existing_chrome_endpoint() -> str | None:
    try:
        port = int(_DEVTOOLS_PORT_FILE.read_text(encoding="ascii").splitlines()[0])
        endpoint = f"http://127.0.0.1:{port}"
        with urlopen(f"{endpoint}/json/version", timeout=1) as response:
            details = json.loads(response.read(4096))
        return endpoint if str(details.get("Browser", "")).startswith("Chrome/") else None
    except (URLError, TimeoutError, OSError, ValueError, IndexError, json.JSONDecodeError):
        return None


def _minimize_chrome_window(browser, page) -> None:
    """Keep the dedicated search window out of the user's active workspace."""
    session = browser.new_browser_cdp_session()
    try:
        targets = session.send("Target.getTargets").get("targetInfos", [])
        target = next(
            (
                item
                for item in targets
                if item.get("type") == "page" and item.get("url") == page.url
            ),
            None,
        )
        if target:
            window = session.send(
                "Browser.getWindowForTarget", {"targetId": target["targetId"]}
            )
            session.send(
                "Browser.setWindowBounds",
                {"windowId": window["windowId"], "bounds": {"windowState": "minimized"}},
            )
    finally:
        session.detach()
