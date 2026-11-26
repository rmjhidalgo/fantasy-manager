"""Read a saved web page file into (url, saved_at, html).

Supports the two ways browsers save a page:
- "Webpage, Single File" (.mhtml/.mht): a MIME archive with the page URL and save time in its headers.
- "Webpage, HTML only" / "Complete" (.html/.htm): the URL is in a "saved from url" comment;
  the save time comes from the file's modified time, passed in by the caller.
"""

import email
import email.policy
import email.utils
import re
from dataclasses import dataclass
from datetime import UTC, datetime

SUPPORTED_EXTENSIONS = (".mhtml", ".mht", ".html", ".htm")


class NotAWebPage(ValueError):
    pass


@dataclass
class PageSource:
    url: str | None
    saved_at: datetime | None  # UTC, naive
    html: str


def _utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def read_page(data: bytes, filename: str, fallback_saved_at: datetime | None) -> PageSource:
    name = filename.lower()
    if name.endswith((".mhtml", ".mht")) or data.lstrip()[:200].lower().startswith(b"from:"):
        return _read_mhtml(data, fallback_saved_at)
    if name.endswith((".html", ".htm")):
        return _read_html(data, fallback_saved_at)
    raise NotAWebPage(f"{filename}: not a saved web page (expected .mhtml or .html)")


def _read_mhtml(data: bytes, fallback_saved_at: datetime | None) -> PageSource:
    msg = email.message_from_bytes(data, policy=email.policy.compat32)
    url = msg.get("Snapshot-Content-Location")
    saved_at = fallback_saved_at
    if msg.get("Date"):
        try:
            saved_at = _utc_naive(email.utils.parsedate_to_datetime(msg["Date"]))
        except (TypeError, ValueError):
            pass
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            # Blink doesn't state a charset on the part; Yahoo pages are UTF-8.
            charset = part.get_content_charset() or "utf-8"
            html = payload.decode(charset, errors="replace")
            url = url or part.get("Content-Location")
            return PageSource(url=url, saved_at=saved_at and _utc_naive(saved_at), html=html)
    raise NotAWebPage("The .mhtml file has no web page inside it")


_SAVED_FROM = re.compile(r"<!--\s*saved from url=\(\d+\)(\S+?)\s*-->", re.I)
_CANONICAL = re.compile(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', re.I)


def _read_html(data: bytes, fallback_saved_at: datetime | None) -> PageSource:
    html = data.decode("utf-8", errors="replace")
    head = html[:5000]
    m = _SAVED_FROM.search(head) or _CANONICAL.search(html)
    url = m.group(1) if m else None
    return PageSource(
        url=url,
        saved_at=fallback_saved_at and _utc_naive(fallback_saved_at),
        html=html,
    )
