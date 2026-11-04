"""Google Images adapter using a local headless Chromium browser."""

from urllib.parse import parse_qs, urlencode, urlsplit
from threading import Lock

_SEARCH_LOCK = Lock()


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
    """Read image result URLs from Google Images without downloading the images."""
    from playwright.sync_api import sync_playwright

    search_url = "https://www.google.com/search?" + urlencode({"tbm": "isch", "q": query})
    results = []
    seen = set()
    with _SEARCH_LOCK, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chrome")
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            page.locator('a[href*="/imgres"]').first.wait_for(timeout=8000)
            for _ in range(3):
                if page.locator('a[href*="/imgres"]').count() >= limit:
                    break
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(500)

            for result in page.locator('a[href*="/imgres"]').all():
                href = result.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.google.com" + href
                params = parse_qs(urlsplit(href).query)
                image_url = next(iter(params.get("imgurl", [])), "")
                source_url = next(iter(params.get("imgrefurl", [])), "") or href
                image = result.locator("img").first
                title = image.get_attribute("alt") or image.get_attribute("title") or ""
                thumbnail_url = image.get_attribute("src") or image.get_attribute("data-src") or image_url
                if (
                    not _web_url(image_url)
                    or urlsplit(image_url).scheme != "https"
                    or len(image_url) > 2048
                    or not _web_url(source_url)
                    or image_url in seen
                ):
                    continue
                results.append({
                    "title": title[:300],
                    "image_url": image_url,
                    "thumbnail_url": thumbnail_url if _web_url(thumbnail_url) else image_url,
                    "source_url": source_url,
                    "source": "Google Images",
                })
                seen.add(image_url)
                if len(results) >= limit:
                    break
        finally:
            browser.close()
    return results
