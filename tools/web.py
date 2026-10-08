from urllib.parse import quote, urljoin, urlparse, parse_qs, unquote, urlunparse
from urllib.request import Request, urlopen
from html.parser import HTMLParser
import re


def normalize_url(url):
    url = str(url or "").strip()

    # Markdown link: [https://example.com](https://example.com)
    m = re.fullmatch(r"\[([^\]]+)\]\((https?://[^)]+)\)", url)
    if m:
        return m.group(2)

    # Plain bracketed URL.
    m = re.fullmatch(r"\[(https?://[^\]]+)\]", url)
    if m:
        return m.group(1)

    # urllib on Windows can fail on Arabic/non-ASCII URL characters.
    try:
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            path = quote(unquote(parsed.path), safe="/:@-._~!    return url


def unwrap_ddg'()*+,;=")
            query = quote(unquote(parsed.query), safe="=&/?@:+,;%-._~!(url):
    url = normalize_url(url)

    try:
        parsed = urlparse(url)
        if (
            "duckduckgo.com" in parsed.netloc
            and parsed.path.startswith("/l/")
        ):
            target = parse_qs(
                parsed.query
            ).get("uddg", [None])[0]

            if target:
                return unquote(target)

    except Exception:
        pass

    return url


class SearchParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.results = []

        self._href = None
        self._classes = set()
        self._text = []

        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "a":
            self._href = attrs.get("href")
            self._classes = set(
                (attrs.get("class") or "").split()
            )
            self._text = []

    def handle_endtag(self, tag):
        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag != "a" or not self._href:
            return

        text = re.sub(
            r"\s+",
            " ",
            " ".join(self._text),
        ).strip()

        if "result__a" in self._classes and text:
            self.results.append(
                {
                    "title": text,
                    "url": unwrap_ddg(
                        urljoin(
                            self.base_url,
                            self._href,
                        )
                    ),
                }
            )

        self._href = None
        self._classes = set()
        self._text = []

    def handle_data(self, data):
        if self._skip_depth:
            return

        if self._href is not None:
            self._text.append(data)


class PageParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url

        self.text_parts = []
        self.links = []

        self._href = None
        self._link_text = []

        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "a":
            self._href = attrs.get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag == "a" and self._href:
            self.links.append(
                {
                    "text": " ".join(
                        self._link_text
                    ).strip(),
                    "url": unwrap_ddg(
                        urljoin(
                            self.base_url,
                            self._href,
                        )
                    ),
                }
            )

            self._href = None
            self._link_text = []

    def handle_data(self, data):
        if self._skip_depth:
            return

        clean = re.sub(
            r"\s+",
            " ",
            data,
        ).strip()

        if not clean:
            return

        self.text_parts.append(clean)

        if self._href is not None:
            self._link_text.append(clean)


class WebTool:
    name = "web"
    description = (
        "Search and read public webpages and download public files. "
        "Extracted text excludes scripts and styles."
    )

    def _fetch(self, url, timeout=25):
        request = Request(
            normalize_url(url),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/154 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.8,ar;q=0.7",
            },
        )

        with urlopen(
            request,
            timeout=timeout,
        ) as response:
            charset = (
                response.headers.get_content_charset()
                or "utf-8"
            )

            return (
                response.read().decode(
                    charset,
                    errors="replace",
                ),
                response.geturl(),
            )

    def search(
        self,
        query,
        max_results=8,
    ):
        query = str(query).strip()

        if not query:
            return {
                "success": False,
                "error": "Search query is empty.",
            }

        url = (
            "https://html.duckduckgo.com/html/?q="
            + quote(query)
        )

        try:
            html, _ = self._fetch(url)

        except Exception as exc:
            return {
                "success": False,
                "error": f"Search failed: {exc}",
            }

        parser = SearchParser(url)
        parser.feed(html)

        results = parser.results[
            :int(max_results)
        ]

        if not results:
            return {
                "success": False,
                "query": query,
                "results": [],
                "error": (
                    "No parsable search result links were found."
                ),
            }

        return {
            "success": True,
            "query": query,
            "results": results,
        }

    def open_url(
        self,
        url,
        max_chars=12000,
    ):
        url = unwrap_ddg(url)

        if not url.startswith(
            ("http://", "https://")
        ):
            raise ValueError(
                "URL must start with http:// or https://"
            )

        try:
            html, final_url = self._fetch(url)

        except Exception as exc:
            return {
                "success": False,
                "url": url,
                "error": f"Open URL failed: {exc}",
            }

        # Follow JavaScript redirect shells.
        js_target = re.search(
            r"""(?:location\.replace|location\.href)\s*\(\s*["']([^"']+)["']\s*\)""",
            html,
            re.IGNORECASE,
        )

        if js_target:
            target = unwrap_ddg(
                js_target.group(1)
            )

            if (
                target.startswith(
                    ("http://", "https://")
                )
                and target != url
            ):
                return self.open_url(
                    target,
                    max_chars=max_chars,
                )

        parser = PageParser(final_url)
        parser.feed(html)

        text = re.sub(
            r"\s+",
            " ",
            " ".join(
                parser.text_parts
            ),
        ).strip()

        # A source is considered readable evidence only if it has
        # meaningful visible text, not merely CSS/JS/empty markup.
        meaningful = len(
            re.sub(
                r"[^A-Za-z\u0600-\u06FF0-9]+",
                "",
                text,
            )
        ) >= 80

        return {
            "success": True,
            "url": final_url,
            "title": (
                text[:160]
                if text
                else ""
            ),
            "text": text[
                :int(max_chars)
            ],
            "links": parser.links[:100],
            "meaningful_text": meaningful,
        }

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "search": {
                    "description": (
                        "Search the public web and return real destination URLs."
                    ),
                    "parameters": {
                        "query": {
                            "type": "string",
                            "required": True,
                        },
                        "max_results": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
                "open_url": {
                    "description": (
                        "Read a public webpage and return meaningful visible text and links."
                    ),
                    "parameters": {
                        "url": {
                            "type": "string",
                            "required": True,
                        },
                        "max_chars": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
            },
        }
()*")
            fragment = quote(unquote(parsed.fragment), safe="=&/?@:+,;%-._~!(url):
    url = normalize_url(url)

    try:
        parsed = urlparse(url)
        if (
            "duckduckgo.com" in parsed.netloc
            and parsed.path.startswith("/l/")
        ):
            target = parse_qs(
                parsed.query
            ).get("uddg", [None])[0]

            if target:
                return unquote(target)

    except Exception:
        pass

    return url


class SearchParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.results = []

        self._href = None
        self._classes = set()
        self._text = []

        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "a":
            self._href = attrs.get("href")
            self._classes = set(
                (attrs.get("class") or "").split()
            )
            self._text = []

    def handle_endtag(self, tag):
        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag != "a" or not self._href:
            return

        text = re.sub(
            r"\s+",
            " ",
            " ".join(self._text),
        ).strip()

        if "result__a" in self._classes and text:
            self.results.append(
                {
                    "title": text,
                    "url": unwrap_ddg(
                        urljoin(
                            self.base_url,
                            self._href,
                        )
                    ),
                }
            )

        self._href = None
        self._classes = set()
        self._text = []

    def handle_data(self, data):
        if self._skip_depth:
            return

        if self._href is not None:
            self._text.append(data)


class PageParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url

        self.text_parts = []
        self.links = []

        self._href = None
        self._link_text = []

        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "a":
            self._href = attrs.get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag == "a" and self._href:
            self.links.append(
                {
                    "text": " ".join(
                        self._link_text
                    ).strip(),
                    "url": unwrap_ddg(
                        urljoin(
                            self.base_url,
                            self._href,
                        )
                    ),
                }
            )

            self._href = None
            self._link_text = []

    def handle_data(self, data):
        if self._skip_depth:
            return

        clean = re.sub(
            r"\s+",
            " ",
            data,
        ).strip()

        if not clean:
            return

        self.text_parts.append(clean)

        if self._href is not None:
            self._link_text.append(clean)


class WebTool:
    name = "web"
    description = (
        "Search and read public webpages and download public files. "
        "Extracted text excludes scripts and styles."
    )

    def _fetch(self, url, timeout=25):
        request = Request(
            normalize_url(url),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/154 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.8,ar;q=0.7",
            },
        )

        with urlopen(
            request,
            timeout=timeout,
        ) as response:
            charset = (
                response.headers.get_content_charset()
                or "utf-8"
            )

            return (
                response.read().decode(
                    charset,
                    errors="replace",
                ),
                response.geturl(),
            )

    def search(
        self,
        query,
        max_results=8,
    ):
        query = str(query).strip()

        if not query:
            return {
                "success": False,
                "error": "Search query is empty.",
            }

        url = (
            "https://html.duckduckgo.com/html/?q="
            + quote(query)
        )

        try:
            html, _ = self._fetch(url)

        except Exception as exc:
            return {
                "success": False,
                "error": f"Search failed: {exc}",
            }

        parser = SearchParser(url)
        parser.feed(html)

        results = parser.results[
            :int(max_results)
        ]

        if not results:
            return {
                "success": False,
                "query": query,
                "results": [],
                "error": (
                    "No parsable search result links were found."
                ),
            }

        return {
            "success": True,
            "query": query,
            "results": results,
        }

    def open_url(
        self,
        url,
        max_chars=12000,
    ):
        url = unwrap_ddg(url)

        if not url.startswith(
            ("http://", "https://")
        ):
            raise ValueError(
                "URL must start with http:// or https://"
            )

        try:
            html, final_url = self._fetch(url)

        except Exception as exc:
            return {
                "success": False,
                "url": url,
                "error": f"Open URL failed: {exc}",
            }

        # Follow JavaScript redirect shells.
        js_target = re.search(
            r"""(?:location\.replace|location\.href)\s*\(\s*["']([^"']+)["']\s*\)""",
            html,
            re.IGNORECASE,
        )

        if js_target:
            target = unwrap_ddg(
                js_target.group(1)
            )

            if (
                target.startswith(
                    ("http://", "https://")
                )
                and target != url
            ):
                return self.open_url(
                    target,
                    max_chars=max_chars,
                )

        parser = PageParser(final_url)
        parser.feed(html)

        text = re.sub(
            r"\s+",
            " ",
            " ".join(
                parser.text_parts
            ),
        ).strip()

        # A source is considered readable evidence only if it has
        # meaningful visible text, not merely CSS/JS/empty markup.
        meaningful = len(
            re.sub(
                r"[^A-Za-z\u0600-\u06FF0-9]+",
                "",
                text,
            )
        ) >= 80

        return {
            "success": True,
            "url": final_url,
            "title": (
                text[:160]
                if text
                else ""
            ),
            "text": text[
                :int(max_chars)
            ],
            "links": parser.links[:100],
            "meaningful_text": meaningful,
        }

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "search": {
                    "description": (
                        "Search the public web and return real destination URLs."
                    ),
                    "parameters": {
                        "query": {
                            "type": "string",
                            "required": True,
                        },
                        "max_results": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
                "open_url": {
                    "description": (
                        "Read a public webpage and return meaningful visible text and links."
                    ),
                    "parameters": {
                        "url": {
                            "type": "string",
                            "required": True,
                        },
                        "max_chars": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
            },
        }
()*")
            return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, query, fragment))
    except Exception:
        pass
    return url


def unwrap_ddg(url):
    url = normalize_url(url)

    try:
        parsed = urlparse(url)
        if (
            "duckduckgo.com" in parsed.netloc
            and parsed.path.startswith("/l/")
        ):
            target = parse_qs(
                parsed.query
            ).get("uddg", [None])[0]

            if target:
                return unquote(target)

    except Exception:
        pass

    return url


class SearchParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.results = []

        self._href = None
        self._classes = set()
        self._text = []

        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "a":
            self._href = attrs.get("href")
            self._classes = set(
                (attrs.get("class") or "").split()
            )
            self._text = []

    def handle_endtag(self, tag):
        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag != "a" or not self._href:
            return

        text = re.sub(
            r"\s+",
            " ",
            " ".join(self._text),
        ).strip()

        if "result__a" in self._classes and text:
            self.results.append(
                {
                    "title": text,
                    "url": unwrap_ddg(
                        urljoin(
                            self.base_url,
                            self._href,
                        )
                    ),
                }
            )

        self._href = None
        self._classes = set()
        self._text = []

    def handle_data(self, data):
        if self._skip_depth:
            return

        if self._href is not None:
            self._text.append(data)


class PageParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url

        self.text_parts = []
        self.links = []

        self._href = None
        self._link_text = []

        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "a":
            self._href = attrs.get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in {
            "script",
            "style",
            "noscript",
            "template",
            "svg",
        }:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag == "a" and self._href:
            self.links.append(
                {
                    "text": " ".join(
                        self._link_text
                    ).strip(),
                    "url": unwrap_ddg(
                        urljoin(
                            self.base_url,
                            self._href,
                        )
                    ),
                }
            )

            self._href = None
            self._link_text = []

    def handle_data(self, data):
        if self._skip_depth:
            return

        clean = re.sub(
            r"\s+",
            " ",
            data,
        ).strip()

        if not clean:
            return

        self.text_parts.append(clean)

        if self._href is not None:
            self._link_text.append(clean)


class WebTool:
    name = "web"
    description = (
        "Search and read public webpages and download public files. "
        "Extracted text excludes scripts and styles."
    )

    def _fetch(self, url, timeout=25):
        request = Request(
            normalize_url(url),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/154 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.8,ar;q=0.7",
            },
        )

        with urlopen(
            request,
            timeout=timeout,
        ) as response:
            charset = (
                response.headers.get_content_charset()
                or "utf-8"
            )

            return (
                response.read().decode(
                    charset,
                    errors="replace",
                ),
                response.geturl(),
            )

    def search(
        self,
        query,
        max_results=8,
    ):
        query = str(query).strip()

        if not query:
            return {
                "success": False,
                "error": "Search query is empty.",
            }

        url = (
            "https://html.duckduckgo.com/html/?q="
            + quote(query)
        )

        try:
            html, _ = self._fetch(url)

        except Exception as exc:
            return {
                "success": False,
                "error": f"Search failed: {exc}",
            }

        parser = SearchParser(url)
        parser.feed(html)

        results = parser.results[
            :int(max_results)
        ]

        if not results:
            return {
                "success": False,
                "query": query,
                "results": [],
                "error": (
                    "No parsable search result links were found."
                ),
            }

        return {
            "success": True,
            "query": query,
            "results": results,
        }

    def open_url(
        self,
        url,
        max_chars=12000,
    ):
        url = unwrap_ddg(url)

        if not url.startswith(
            ("http://", "https://")
        ):
            raise ValueError(
                "URL must start with http:// or https://"
            )

        try:
            html, final_url = self._fetch(url)

        except Exception as exc:
            return {
                "success": False,
                "url": url,
                "error": f"Open URL failed: {exc}",
            }

        # Follow JavaScript redirect shells.
        js_target = re.search(
            r"""(?:location\.replace|location\.href)\s*\(\s*["']([^"']+)["']\s*\)""",
            html,
            re.IGNORECASE,
        )

        if js_target:
            target = unwrap_ddg(
                js_target.group(1)
            )

            if (
                target.startswith(
                    ("http://", "https://")
                )
                and target != url
            ):
                return self.open_url(
                    target,
                    max_chars=max_chars,
                )

        parser = PageParser(final_url)
        parser.feed(html)

        text = re.sub(
            r"\s+",
            " ",
            " ".join(
                parser.text_parts
            ),
        ).strip()

        # A source is considered readable evidence only if it has
        # meaningful visible text, not merely CSS/JS/empty markup.
        meaningful = len(
            re.sub(
                r"[^A-Za-z\u0600-\u06FF0-9]+",
                "",
                text,
            )
        ) >= 80

        return {
            "success": True,
            "url": final_url,
            "title": (
                text[:160]
                if text
                else ""
            ),
            "text": text[
                :int(max_chars)
            ],
            "links": parser.links[:100],
            "meaningful_text": meaningful,
        }

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "search": {
                    "description": (
                        "Search the public web and return real destination URLs."
                    ),
                    "parameters": {
                        "query": {
                            "type": "string",
                            "required": True,
                        },
                        "max_results": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
                "open_url": {
                    "description": (
                        "Read a public webpage and return meaningful visible text and links."
                    ),
                    "parameters": {
                        "url": {
                            "type": "string",
                            "required": True,
                        },
                        "max_chars": {
                            "type": "integer",
                            "required": False,
                        },
                    },
                },
            },
        }
