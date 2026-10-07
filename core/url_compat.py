from __future__ import annotations
from urllib.parse import urlparse

def origin(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(str(url).strip())
    if not p.scheme or not p.netloc:
        return None
    return f"{p.scheme.lower()}://{p.netloc.lower()}"

def hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return (urlparse(str(url).strip()).hostname or "").lower() or None
    except Exception:
        return None

def registrable_host(host: str | None) -> str | None:
    if not host:
        return None
    h = host.lower().strip(".")
    if h.startswith("www."):
        return h[4:]
    return h

def same_site(a: str | None, b: str | None) -> bool:
    ha = registrable_host(hostname(a))
    hb = registrable_host(hostname(b))
    return bool(ha and hb and ha == hb)
