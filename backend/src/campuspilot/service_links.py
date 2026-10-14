"""Program-resolved official service links; model text never supplies a destination.

Read only the hash-bound captures of the request's immutable knowledge version. Old
captures, unadopted documents, login credentials and search snippets are not a link registry.
Reachability is deliberately separate: a recorded official link is not a completed service.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Self
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

from pydantic import Field, JsonValue, ValidationError, model_validator

from campuspilot.contracts import Contract
from campuspilot.knowledge import official_url

if TYPE_CHECKING:
    from campuspilot.rag import KnowledgeSnapshot, RagSource, RetrievalHit

SECRET_KEYS = frozenset({
    "token", "access_token", "refresh_token", "id_token", "ticket", "password",
    "passwd", "cookie", "session", "sessionid", "jsessionid", "api_key", "apikey", "key",
    "username", "user_id", "userid", "student_id", "studentid", "account", "authorization",
    "auth_token", "code", "credential",
})
REDIRECT_KEYS = frozenset({
    "service", "redirect", "redirect_uri", "redirect_url", "returnurl", "return_url",
    "callback", "callback_url", "url", "target", "next",
})
URL_TEXT = re.compile(r"https://[^\s<>\"'，。；）)\u4e00-\u9fff→]+")
ACTION_WORDS = re.compile(r"办理|申请|预约|平台|系统|登录|访问|缴费|VPN|vpn")
GUIDE_TITLE = re.compile(r"指南|指引|手册|常见问题|操作说明")


def safe_service_url(value: str, depth: int = 0) -> str:
    """Campus HTTPS only, including nested authentication return destinations."""
    if not isinstance(value, str) or len(value) > 2048 or depth > 3:
        raise ValueError("Invalid service URL")
    decoded = value
    for _ in range(3):
        decoded = unquote(decoded)
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in decoded):
        raise ValueError("Invalid service URL characters")
    official_url(value)
    parsed = urlsplit(value)
    if ";jsessionid" in parsed.path.casefold() or "\\" in decoded or any(
        mark in unquote(parsed.path) for mark in ("*", "{", "}")
    ):
        raise ValueError("Session-bound service URL")
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        for _ in range(3):
            key = unquote(key)
        if key.casefold() in SECRET_KEYS:
            raise ValueError("Service URL contains credentials")
        if key.casefold() in REDIRECT_KEYS and not item:
            raise ValueError("Incomplete authentication destination")
        target = item
        for _ in range(3):
            target = unquote(target)
        if key.casefold() in REDIRECT_KEYS and target:
            safe_service_url(urljoin(value, target), depth + 1)
    return value


class ServiceLink(Contract):
    id: str
    title: Annotated[str, Field(min_length=1, max_length=160)]
    url: str
    kind: Literal["online", "platform", "guide"]
    source_id: str
    source_title: str
    source_url: str
    requires_login: bool | None = None
    network_requirement: Literal["campus_or_vpn", "unknown"] = "unknown"
    checked_at: date | None = None
    availability: Literal["not_checked"] = "not_checked"

    @model_validator(mode="after")
    def official_destination(self) -> Self:
        safe_service_url(self.url)
        safe_service_url(self.source_url)
        if not all((self.id, self.source_id, self.source_title)):
            raise ValueError("Missing service link provenance")
        return self


LinkCatalog = dict[str, tuple[ServiceLink, ...]]


def _link(
    source_id: str, source_title: str, source_url: str, checked_at: date | None,
    url: str, title: str, kind: Literal["online", "platform", "guide"],
    body: str = "",
) -> ServiceLink | None:
    from campuspilot.rag import digest

    try:
        safe_service_url(url)
        return ServiceLink(
            id="service-link:" + digest((source_id + "\n" + url).encode())[:20],
            title=title.strip()[:160], url=url, kind=kind, source_id=source_id,
            source_title=source_title, source_url=source_url, checked_at=checked_at,
            requires_login=True if kind != "guide" and (
                "登录" in body or "/cas/login" in urlsplit(url).path
            ) else None,
            network_requirement="campus_or_vpn" if kind != "guide" and re.search(
                r"校外.{0,30}(?:VPN|vpn|校园网)", body
            ) else "unknown",
        )
    except (ValueError, ValidationError):
        return None


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, str]] = []
        self.href: str | None = None
        self.label: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.label.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href is not None:
            self.items.append((self.href, "".join(self.label).strip()))
            self.href = None


def _read_bound(root: Path, name: str, hashes: dict[str, str], limit: int = 4_000_000) -> bytes:
    from campuspilot.rag import digest

    path = root / name
    if name not in hashes or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Unbound service link capture")
    if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise ValueError("Unsafe service link capture")
    if path.stat().st_size > limit:
        raise ValueError("Service link capture too large")
    content = path.read_bytes()
    if digest(content) != hashes[name]:
        raise ValueError("Service link capture checksum mismatch")
    return content


def load_link_catalog(
    root: Path, snapshot: KnowledgeSnapshot, manifest: dict[str, object],
) -> LinkCatalog:
    """An additive view of adopted raw evidence; does not change snapshot/vector hashes."""
    from campuspilot.rag import canonical, digest

    catalog: LinkCatalog = {}
    hashes = manifest.get("files_sha256")
    if not isinstance(hashes, dict) or "raw/official/provenance.json" not in hashes:
        return catalog
    try:
        history = json.loads(_read_bound(root, "raw/official/provenance.json", hashes))
        documents = history["documents"]
        sources_by_url: dict[str, list[RagSource]] = {}
        for source in snapshot.sources:
            if source.verification_status == "official_document":
                sources_by_url.setdefault(source.url, []).append(source)
        # Each captured manifest remains archived, even after a later package is adopted.
        names = sorted(n for n in hashes if re.fullmatch(
            r"raw/official/captures/[a-f0-9]{64}/manifest\.json", n
        ))
        for name in names:
            capture = json.loads(_read_bound(root, name, hashes))
            for doc in capture.get("documents", []):
                if not isinstance(doc, dict):
                    continue
                prior = documents.get(doc.get("document_id"))
                sources = sources_by_url.get(str(doc.get("url", "")), [])
                if not isinstance(prior, dict) or not sources:
                    continue
                source = next((s for s in sources if s.source_id == (
                    "cdut:source:official:" + str(doc.get("document_id"))
                )), sources[0])
                version = prior["versions"][prior["current_revision"]]
                files = version["files"]
                revision = digest(canonical({
                    "document": doc,
                    "files_sha256": {n: entry["sha256"] for n, entry in files.items()},
                }))
                if revision != prior["current_revision"]:
                    continue  # Never recover a destination from a superseded capture.
                body_entry = files.get(doc.get("body_file"))
                if body_entry is None:
                    continue
                body = _read_bound(root, "raw/" + body_entry["path"], hashes).decode("utf-8")
                links: list[ServiceLink] = []
                for entry in doc.get("service_entrances", [])[:8]:
                    if not isinstance(entry, dict) or entry.get("title", "") not in body:
                        continue
                    link = _link(
                        source.source_id, source.title, source.url, source.verified_at,
                        entry.get("url", ""), entry.get("title", ""), "online", body,
                    )
                    if link:
                        links.append(link)
                original = files.get(doc.get("original_file"))
                is_guide = doc.get("content_kind") == "guide" or bool(
                    GUIDE_TITLE.search(source.title)
                )
                if original and is_guide:
                    parser = _Anchors()
                    parser.feed(_read_bound(root, "raw/" + original["path"], hashes).decode(
                        "utf-8"
                    ))
                    for href, label in parser.items:
                        if not ACTION_WORDS.search(label) or not label or len(label) > 160:
                            continue
                        target = urljoin(source.url, href)
                        kind: Literal["platform", "guide"] = (
                            "guide" if urlsplit(target).path.lower().endswith(
                                (".pdf", ".doc", ".docx", ".xlsx")
                            ) else "platform"
                        )
                        link = _link(
                            source.source_id, source.title, source.url, source.verified_at,
                            target, label, kind, body,
                        )
                        if link:
                            links.append(link)
                # The recorded guide remains useful when a specific application URL is absent.
                if is_guide and ACTION_WORDS.search(body):
                    guide = _link(
                        source.source_id, source.title, source.url, source.verified_at,
                        source.url, source.title, "guide",
                    )
                    if guide:
                        links.append(guide)
                unique = {link.url: link for link in reversed(links)}
                catalog[source.source_id] = tuple(reversed(list(unique.values())))[:5]
                # Stable legacy clause IDs can still reference the same adopted source URL.
                for alias in sources:
                    if alias.source_id == source.source_id:
                        continue
                    catalog[alias.source_id] = tuple(
                        link.model_copy(update={
                            "id": "service-link:" + digest(
                                (alias.source_id + "\n" + link.url).encode()
                            )[:20], "source_id": alias.source_id,
                        }) for link in catalog[source.source_id]
                    )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}  # Link metadata failures must not break ordinary knowledge retrieval.
    return catalog


def hit_service_links(hit: RetrievalHit, catalog: LinkCatalog) -> list[JsonValue]:
    """Only this hit's adopted, applicable evidence can contribute a destination."""
    source, chunk = hit.source, hit.chunk
    if source.verification_status == "pending" or chunk.verification_status == "pending":
        return []
    if chunk.kind in {"historical", "index_only", "deprecated"} or chunk.stale or (
        source.temporal_status in {"historical", "superseded"}
    ):
        return []
    links = list(catalog.get(source.source_id, ()))
    # Literal official entry URLs in an adopted clause need no new model inference.
    if ACTION_WORDS.search(chunk.text):
        for url in URL_TEXT.findall(chunk.text):
            if url == source.url:
                continue
            # A department homepage is evidence/discovery, not an application platform.
            if urlsplit(url).hostname in {"jcc.cdut.edu.cn", "www.jcc.cdut.edu.cn"} and (
                urlsplit(url).path in {"", "/"}
            ):
                continue
            link = _link(
                source.source_id, source.title, source.url, source.verified_at,
                url, "官方办事平台", "platform", chunk.text,
            )
            if link:
                links.append(link)
    unique = {link.url: link for link in links}
    return [link.model_dump(mode="json") for link in list(unique.values())[:5]]


def answer_service_links(
    hits: list[dict[str, JsonValue]], cited: tuple[str, ...], status: str,
) -> list[JsonValue]:
    """Intersect with cited and grounded hits, rather than all retrieved source cards."""
    if status not in {"success", "limited"} or not cited:
        return []
    selected: dict[str, dict[str, JsonValue]] = {}
    for hit in hits:
        sid = str(hit.get("source_id"))
        if not ({sid, str(hit.get("chunk_id"))} & set(cited)) or hit.get("grounded") is False:
            continue
        if hit.get("web") or hit.get("stale"):
            continue
        values = hit.get("service_links")
        if not isinstance(values, list):
            continue
        for value in values:
            try:
                link = ServiceLink.model_validate_json(json.dumps(value, ensure_ascii=False))
            except (ValidationError, ValueError, TypeError):
                continue
            if link.source_id != sid or link.source_url != hit.get("url"):
                continue
            if hit.get("verification_status") not in {"verified", "official_document"}:
                continue
            selected.setdefault(link.url, link.model_dump(mode="json"))
    return [value for value in list(selected.values())[:5]]
