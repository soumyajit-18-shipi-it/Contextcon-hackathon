"""Small, deterministic helpers for untrusted website text."""
import ipaddress
import re
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit


def public_url(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("A public HTTP(S) website is required")
    if host == "localhost" or "." not in host or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("Local websites are not supported")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Private IP addresses are not supported")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag == "a" and not self.hidden:
            self.links.extend(v for k, v in attrs if k == "href" and v)
        if tag in {"p", "div", "br", "li", "footer", "h1", "h2"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li", "footer"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def page_text(content: str) -> tuple[str, list[str]]:
    parser = PageParser()
    parser.feed(content)
    text = "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return text.strip(), parser.links


def about_url(home: str, links: list[str]) -> str:
    for link in links:
        candidate = urljoin(home, link)
        parsed = urlsplit(candidate)
        if parsed.hostname == urlsplit(home).hostname and re.search(r"(?:^|/)about(?:-us)?/?$", parsed.path, re.I):
            return public_url(candidate)
    return urljoin(home, "/about")


def fragment_link(url: str, passage: str) -> str:
    return url.split("#", 1)[0] + "#:~:text=" + quote(" ".join(passage.split()[:8]), safe="")


def distinctive_sentences(text: str) -> list[str]:
    boilerplate = re.compile(r"cookies?|copyright|customer satisfaction|committed to quality|privacy policy|all rights reserved", re.I)
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    return list(dict.fromkeys(s.strip() for s in sentences
                             if 12 <= len(s.split()) <= 30 and not boilerplate.search(s)))[:3]
