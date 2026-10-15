"""Discover actual official detail/pagination links from explicitly selected saved HTML.

This offline maintenance tool never opens browsers, requests URLs, evaluates JavaScript,
or adopts policy facts. Every supplied catalog is scanned without any date cutoff.
Unvisited pagination URLs are a manual collection frontier, not fabricated saved pages.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import posixpath
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

MAX_HTML = 2_000_000
MAX_CATALOGS = 200
SOURCE = re.compile(r"<!--\s*saved from url=\(\d+\)(.*?)\s*-->", re.IGNORECASE)
DEFAULT_DETAIL = (r"(?:^/info/[^/]+/[^/]+\.html?$"
                  r"|^/EIP/nonlogin/elobby/service/introduction/[^/]+\.htm$)")
PRIVATE_KEY = re.compile(r"ticket|token|session|cookie|password|username|student|account|auth",
                         re.IGNORECASE)
PAGER = re.compile(r"(?:^|[\s_-])(?:p_(?:no|next|last|prev|first|fun)|pages?|pagination|pager)",
                   re.IGNORECASE)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}
DROP = {"script", "style", "form", "input", "select", "textarea", "button", "iframe",
        "template", "noscript"}
NEXT = {"下页", "下一页", "下翻", "next", ">", "›", "»"}
PREV = {"上页", "上一页", "上翻", "previous", "prev", "<", "‹", "«"}
FIRST = {"首页", "第一页", "first"}
LAST = {"尾页", "末页", "最后一页", "last"}
DATE_TEXT = re.compile(r"\d{4}\s*(?:年|-|\.|/)\s*\d{1,2}\s*(?:月|-|\.|/)\s*\d{1,2}日?"
                       r"|\d{1,2}/\d{1,2}\s+\d{4}|\d{4}\s+\d{1,2}/\d{1,2}")


class InvalidDiscovery(ValueError):
    """Stable errors never include source HTML, account identifiers or URL credentials."""


@dataclass
class Element:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)
    parent: Element | None = field(default=None, repr=False)


class SavedHTML(HTMLParser):
    def __init__(self, raw: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("root")
        self.stack = [self.root]
        self.feed(raw)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Element(tag, {key: value or "" for key, value in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _hidden(node: Element) -> bool:
    style = re.sub(r"\s+", "", node.attrs.get("style", "")).lower()
    return node.tag in DROP or "hidden" in node.attrs or any(
        value in style for value in ("display:none", "visibility:hidden")
    )


def _elements(node: Element) -> list[Element]:
    if _hidden(node):
        return []
    return [node] + [n for c in node.children if isinstance(c, Element) for n in _elements(c)]


def _text(node: Element) -> str:
    if _hidden(node):
        return ""
    return re.sub(r"\s+", " ", " ".join(
        _text(child) if isinstance(child, Element) else child for child in node.children
    )).strip()


def _percent(match: re.Match[str]) -> str:
    char = chr(int(match[0][1:], 16))
    unreserved = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return char if char in unreserved else match[0].upper()


def normalize_url(reference: str, base: str = "") -> str:
    """Normalize link identity while rejecting private parameters and non-official hosts."""
    value = html.unescape(reference).strip()
    if not value or re.search(r"[\x00-\x20\x7f]", value):
        raise InvalidDiscovery("unsafe_link")
    parsed = urlsplit(urljoin(base, value))
    host = (parsed.hostname or "").lower()
    if (parsed.scheme not in {"http", "https"} or parsed.username or parsed.password
            or not (host == "cdut.edu.cn" or host.endswith(".cdut.edu.cn"))):
        raise InvalidDiscovery("unsafe_link")
    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidDiscovery("unsafe_link") from exc
    if port not in {None, 80 if parsed.scheme == "http" else 443}:
        raise InvalidDiscovery("unsafe_link")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    fragment_values = parse_qsl(parsed.fragment, keep_blank_values=True)
    if any(PRIVATE_KEY.search(key) for key, _ in [*query, *fragment_values]):
        raise InvalidDiscovery("private_url_parameter")
    query = sorted((key, value) for key, value in query
                   if key not in {"_t", "_winid"} and not key.lower().startswith("utm_"))
    path = re.sub(r"%[0-9a-fA-F]{2}", _percent, parsed.path or "/")
    path = posixpath.normpath(path)
    if parsed.path.endswith("/") and not path.endswith("/"):
        path += "/"
    return urlunsplit((parsed.scheme.lower(), host, path, urlencode(query), ""))


def _file(root: Path, name: str) -> Path:
    parts = PurePosixPath(unquote(name)).parts
    if (not name or "\\" in name or ":" in name or ".." in parts
            or PurePosixPath(unquote(name)).is_absolute()):
        raise InvalidDiscovery("unsafe_catalog_path")
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()) or any(
        p.is_symlink() for p in (path, *path.parents)
    ):
        raise InvalidDiscovery("unsafe_catalog_path")
    if not path.is_file() or path.stat().st_size > MAX_HTML:
        raise InvalidDiscovery("missing_or_large_catalog")
    return path


def _ancestors(node: Element) -> list[Element]:
    result = []
    parent = node.parent
    while parent:
        result.append(parent)
        parent = parent.parent
    return result


def _page_kind(node: Element) -> str | None:
    label = _text(node).lower()
    rel = node.attrs.get("rel", "").lower().split()
    context = " ".join(n.attrs.get("class", "") + " " + n.attrs.get("id", "")
                       for n in [node, *_ancestors(node)])
    if label in NEXT or "next" in rel:
        return "next"
    if label in PREV or "prev" in rel:
        return "previous"
    if not PAGER.search(context):
        return None
    if label in FIRST:
        return "first"
    if label in LAST:
        return "last"
    if re.fullmatch(r"\d+", label):
        return "number"
    return "page" if label else None


def _row_dates(node: Element) -> list[str]:
    row = next((n for n in _ancestors(node) if n.tag in {"li", "tr"}), node)
    return sorted(set(match[0] for match in DATE_TEXT.finditer(_text(row))))


def discover(root: Path, catalogs: list[str], collected_on: str,
             detail_pattern: str = DEFAULT_DETAIL) -> dict[str, Any]:
    """Scan every explicitly supplied catalog and deduplicate normalized actual links."""
    date.fromisoformat(collected_on)
    if not 0 < len(catalogs) <= MAX_CATALOGS:
        raise InvalidDiscovery("invalid_catalog_count")
    try:
        detail = re.compile(detail_pattern, re.IGNORECASE)
    except re.error as exc:
        raise InvalidDiscovery("invalid_detail_pattern") from exc
    root = root.resolve()
    pages: list[dict[str, Any]] = []
    documents: dict[str, dict[str, Any]] = {}
    ignored = 0
    for filename in catalogs:
        path = _file(root, filename)
        data = path.read_bytes()
        try:
            raw = data.decode("utf-8-sig")
        except UnicodeError as exc:
            raise InvalidDiscovery("catalog_must_be_utf8") from exc
        saved = SOURCE.search(raw[:4000])
        if not saved:
            raise InvalidDiscovery("missing_saved_source_url")
        source = normalize_url(saved[1].strip())
        if re.search(r"/EIP/(?:flow|cooperative|personal)|/jsxsd/|/xsfw/|/xsqj/",
                     urlsplit(source).path, re.IGNORECASE):
            raise InvalidDiscovery("personal_application_not_catalog")
        dom = SavedHTML(raw)
        nodes = _elements(dom.root)
        titles = [n for n in nodes if n.tag == "title"]
        page: dict[str, Any] = {
            "url": source, "title": _text(titles[0]) if titles else None,
            "saved_file": path.relative_to(root).as_posix(),
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "collected_at": collected_on, "collection_precision": "day",
            "channel": "browser_dom", "pagination": [], "detail_link_count": 0,
        }
        for ordinal, anchor in enumerate((n for n in nodes if n.tag == "a"), 1):
            reference = anchor.attrs.get("href", "")
            if not reference or reference.startswith("#"):
                continue
            try:
                url = normalize_url(reference, source)
            except InvalidDiscovery:
                ignored += 1
                continue
            # Parse no executable attributes; href is the only destination authority.
            kind = _page_kind(anchor)
            if kind and not detail.search(urlsplit(url).path):
                page["pagination"].append({"url": url, "label": _text(anchor), "kind": kind,
                                           "href": reference, "anchor_ordinal": ordinal})
                continue
            if not detail.search(urlsplit(url).path):
                continue
            image_alts = [n.attrs.get("alt", "") for n in _elements(anchor) if n.tag == "img"]
            title = anchor.attrs.get("title") or _text(anchor) or next(
                (value for value in image_alts if value), None
            )
            observation = {"catalog_url": source, "catalog_file": page["saved_file"],
                           "anchor_ordinal": ordinal, "href": reference,
                           "title": title, "date_text": _row_dates(anchor)}
            document = documents.setdefault(url, {
                "url": url, "title": title, "evidence_kind": "saved_catalog_href",
                "collected_at": collected_on, "collection_precision": "day",
                "body_collected": False, "adopted": False, "observations": [],
            })
            if not document["title"] and title:
                document["title"] = title
            document["observations"].append(observation)
            page["detail_link_count"] += 1
        pages.append(page)
    saved_urls = {page["url"] for page in pages}
    frontier: dict[str, dict[str, Any]] = {}
    for page in pages:
        for pagination in page["pagination"]:
            pagination["saved_catalog_supplied"] = pagination["url"] in saved_urls
            if not pagination["saved_catalog_supplied"]:
                entry = frontier.setdefault(pagination["url"], {
                    "url": pagination["url"], "discovered_from": [],
                    "action": "manually_save_catalog_page", "fetched": False,
                })
                if page["url"] not in entry["discovered_from"]:
                    entry["discovered_from"].append(page["url"])
    return {"schema_version": 1, "method": "explicit_saved_catalog_hrefs",
            "collected_at": collected_on, "collection_precision": "day", "catalogs": pages,
            "documents": list(documents.values()), "unvisited_pagination": list(frontier.values()),
            "all_supplied_pages_scanned": True, "date_cutoff_used": False,
            "full_column_coverage_claimed": False, "browser_access": False, "network_access": False,
            "ignored_nonofficial_or_unsafe_links": ignored, "authority": "discovery_only"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", action="append", required=True)
    parser.add_argument("--collected-on", required=True)
    parser.add_argument("--detail-pattern", default=DEFAULT_DETAIL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists() or args.output.resolve().is_relative_to(args.root.resolve()):
            raise InvalidDiscovery("output_must_be_new_and_outside_source")
        result = discover(args.root, args.catalog, args.collected_on, args.detail_pattern)
        payload = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="official-discovery-",
                                          dir=args.output.parent) as temporary:
            staged = Path(temporary) / "discovery.json"
            staged.write_bytes(payload)
            staged.rename(args.output)
        print(json.dumps({"catalogs": len(result["catalogs"]),
                          "unique_detail_links": len(result["documents"]),
                          "unvisited_pagination": len(result["unvisited_pagination"]),
                          "adopted": False, "network_access": False}, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        reason = str(exc) if isinstance(exc, InvalidDiscovery) else type(exc).__name__
        parser.exit(2, f"Official discovery failed ({reason}); no manifest written.\n")


if __name__ == "__main__":
    main()
