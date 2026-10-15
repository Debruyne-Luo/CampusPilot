"""Import saved portal guide DOMs without browser access or personal-center data.

Only local HTML frames explicitly referenced by a top-level saved page are traversed.
The output preserves visible guide sections, table rows and available guide images;
scripts, form values, navigation and personal shells are never copied. Image source
URLs must be explicitly present in the saved document, never guessed from filenames.
This produces an unannotated local package, not an approval or publication.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

MAX_HTML = 2_000_000
MAX_ASSET = 20_000_000
MAX_PAGES = 200
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}
DROP = {"script", "style", "iframe", "form", "input", "textarea", "select", "button",
        "nav", "footer", "noscript", "object", "embed", "template"}
BLOCK = {"div", "p", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
         "section", "article", "dl", "dt", "dd", "blockquote", "table"}
SAFE_TAGS = BLOCK | {"a", "span", "strong", "b", "em", "i", "u", "br", "hr", "img",
                     "tbody", "thead", "tfoot", "tr", "td", "th", "sup", "sub"}
SOURCE = re.compile(r"<!--\s*saved from url=\(\d+\)(.*?)\s*-->", re.IGNORECASE)
GUIDE_PATH = re.compile(r"^/EIP/nonlogin/elobby/service/introduction/([a-z0-9_-]+)\.htm$")
LIST_PATH = "/EIP/nonlogin/serviceGuide/serviceGuideToPage.htm"
REMOTE_IMG = re.compile(r"<img\b[^>]*\bsrc\s*=\s*[\"'](https://[^\"'<>]+)[\"']",
                        re.IGNORECASE)
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")
UI_IMAGES = {"service-description-default-icon.png", "icon-flow-preview.png",
             "docx.gif", "xlsx.gif", "pdf.gif", "doc.gif"}


class InvalidExport(ValueError):
    """Stable reason codes deliberately omit source bodies and account material."""


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)


class DOM(HTMLParser):
    def __init__(self, raw: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]
        self.feed(raw)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {key: value or "" for key, value in attrs})
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


def _hidden(node: Node) -> bool:
    style = re.sub(r"\s+", "", node.attrs.get("style", "")).lower()
    return node.tag in DROP or "hidden" in node.attrs or any(
        marker in style for marker in ("display:none", "visibility:hidden")
    )


def _nodes(node: Node) -> list[Node]:
    if _hidden(node):
        return []
    return [node] + [item for child in node.children if isinstance(child, Node)
                     for item in _nodes(child)]


def _frames(node: Node) -> list[Node]:
    if node.tag in {"script", "style", "form", "template"}:
        return []
    return ([node] if node.tag == "iframe" else []) + [
        item for child in node.children if isinstance(child, Node) for item in _frames(child)
    ]


def _text(node: Node) -> str:
    if _hidden(node):
        return ""
    if node.tag == "br":
        return "\n"
    if node.tag == "tr":
        return "\n" + "\t".join(
            _inline(child) for child in node.children
            if isinstance(child, Node) and child.tag in {"td", "th"}
        ) + "\n"
    text = "".join(_text(c) if isinstance(c, Node) else c for c in node.children)
    return "\n" + text + "\n" if node.tag in BLOCK else text


def _inline(node: Node) -> str:
    return re.sub(r"\s+", " ", _text(node)).strip()


def _visible(node: Node) -> str:
    lines = [re.sub(r"[^\S\t]+", " ", line).strip() for line in _text(node).splitlines()]
    return "\n\n".join(line for line in lines if line)


def _url(value: str) -> str:
    parsed = urlsplit(html.unescape(value))
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or not (host == "cdut.edu.cn" or host.endswith(".cdut.edu.cn"))):
        raise InvalidExport("unsafe_source_url")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(re.search(r"token|ticket|session|cookie|password|username|student|account|auth",
                     key, re.IGNORECASE) for key, _ in query):
        raise InvalidExport("private_url_parameter")
    query = [(key, value) for key, value in query if key not in {"_t", "_winid"}]
    return urlunsplit(("https", host, parsed.path, urlencode(query), ""))


def _source(raw: str) -> str | None:
    match = SOURCE.search(raw[:4000])
    return _url(match[1].strip()) if match else None


def _file(root: Path, relative: str, *, base: Path | None = None, limit: int = MAX_HTML) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise InvalidExport("unsafe_local_path")
    parsed = urlsplit(relative)
    parts = PurePosixPath(unquote(parsed.path)).parts
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or ":" in relative
            or PurePosixPath(unquote(parsed.path)).is_absolute()
            or ".." in parts):
        raise InvalidExport("unsafe_local_path")
    path = (base or root).joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise InvalidExport("unsafe_local_path")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise InvalidExport("symlink_local_path")
    if not path.is_file() or path.stat().st_size > limit:
        raise InvalidExport("missing_or_large_local_file")
    return path


def _read(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_HTML:
        raise InvalidExport("large_html")
    try:
        return data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise InvalidExport("html_must_be_utf8") from exc


def _mapping(path: Path | None, root: Path) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_bytes())
        if (not isinstance(data, dict) or set(data) != {"schema_version", "documents"}
                or data["schema_version"] != 1 or not isinstance(data["documents"], list)):
            raise InvalidExport("invalid_import_map")
        result: dict[str, dict[str, str]] = {}
        ids: set[str] = set()
        for row in data["documents"]:
            if (not isinstance(row, dict) or set(row) - {"file", "document_id", "access_scope"}
                    or not all(isinstance(v, str) for v in row.values())
                    or not {"file", "document_id"} <= set(row)
                    or not ID.fullmatch(row["document_id"])
                    or row.get("access_scope", "authenticated_general")
                    not in {"public", "authenticated_general"}):
                raise InvalidExport("invalid_import_map")
            relative = _file(root, row["file"]).relative_to(root).as_posix()
            if relative in result or row["document_id"] in ids:
                raise InvalidExport("duplicate_import_map")
            result[relative] = row
            ids.add(row["document_id"])
        return result
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        raise InvalidExport("invalid_import_map") from exc


def _discover(root: Path) -> list[tuple[Path, Path, str, DOM]]:
    """Never enumerate arbitrary asset files or traverse application-form frames."""
    found: dict[Path, tuple[Path, Path, str, DOM]] = {}
    examined: set[Path] = set()

    def visit(path: Path, boundary: Path, top: bool = False) -> None:
        if path in examined:
            return
        examined.add(path)
        if len(examined) > MAX_PAGES:
            raise InvalidExport("too_many_saved_pages")
        raw = _read(path)
        top_source = SOURCE.search(raw[:4000]) if top else None
        top_is_guide = bool(top_source and GUIDE_PATH.fullmatch(
            urlsplit(top_source[1].strip()).path))
        if not top or top_is_guide:
            source_match = SOURCE.search(raw[:4000])
            source_path = urlsplit(source_match[1].strip()).path if source_match else ""
            if not (GUIDE_PATH.fullmatch(source_path) or source_path == LIST_PATH):
                return
            source = _source(raw)
            if not source:
                return
            parsed = urlsplit(source)
            if parsed.hostname != "bsdt.cdut.edu.cn":
                return
            if GUIDE_PATH.fullmatch(parsed.path):
                found[path] = (path, boundary, source, DOM(raw))
                return
            if parsed.path != LIST_PATH:
                return
        dom = DOM(raw)
        for frame in _frames(dom.root):
            # Frames are excluded from visible extraction but used for local discovery.
            source = frame.attrs.get("src", "")
            if urlsplit(source).scheme in {"https", "http"} or source.startswith("//"):
                continue
            candidate = _file(boundary, source, base=path.parent)
            candidate_boundary = boundary
            if top:
                relative = candidate.relative_to(root)
                if len(relative.parts) < 2 or not relative.parts[0].endswith("_files"):
                    raise InvalidExport("frame_outside_saved_assets")
                candidate_boundary = root / relative.parts[0]
            visit(candidate, candidate_boundary)

    for path in sorted(root.glob("*.html")):
        if path.is_symlink():
            raise InvalidExport("symlink_local_path")
        visit(path, root, True)
    return list(found.values())


def _format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def _remote_images(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    ambiguous: set[str] = set()
    for match in REMOTE_IMG.finditer(raw.replace('\\"', '"')):
        try:
            url = _url(match[1])
        except ValueError:
            continue
        parsed = urlsplit(url)
        ident = dict(parse_qsl(parsed.query)).get("id") or PurePosixPath(parsed.path).name
        if ident in result and result[ident] != url:
            ambiguous.add(ident)
        result[ident] = url
    return {key: value for key, value in result.items() if key not in ambiguous}


def _safe_html(node: Node, images: dict[int, str]) -> str:
    if _hidden(node):
        return ""
    if node.tag == "img":
        path = images.get(id(node))
        return f'<img src="{html.escape(path, quote=True)}">' if path else ""
    inner = "".join(_safe_html(child, images) if isinstance(child, Node) else html.escape(child)
                    for child in node.children)
    if node.tag not in SAFE_TAGS:
        return inner
    attrs: dict[str, str] = {}
    if node.tag == "a" and node.attrs.get("href"):
        try:
            attrs["href"] = _url(node.attrs["href"])
        except ValueError:
            pass
    for key in ("rowspan", "colspan"):
        if node.tag in {"td", "th"} and re.fullmatch(r"[1-9]\d?", node.attrs.get(key, "")):
            attrs[key] = node.attrs[key]
    rendered = "".join(f' {key}="{html.escape(value, quote=True)}"' for key, value in attrs.items())
    return f"<{node.tag}{rendered}>{inner}</{node.tag}>" if node.tag not in VOID else (
        f"<{node.tag}{rendered}>"
    )


def _guide(path: Path, boundary: Path, url: str, dom: DOM, collected: str,
           mapping: dict[str, str], root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    nodes = _nodes(dom.root)
    titles = [node for node in nodes
              if "content-header-text-title" in node.attrs.get("class", "").split()]
    sections = [node for node in nodes
                if "service-guide-item" in node.attrs.get("class", "").split()]
    codes = [node for node in nodes if node.attrs.get("id") == "serviceCode"]
    metadata: list[Node] = []
    publisher = ""
    for node in nodes:
        if node.tag != "dl":
            continue
        terms = [c for c in node.children if isinstance(c, Node) and c.tag == "dt"]
        definitions = [c for c in node.children if isinstance(c, Node) and c.tag == "dd"]
        if len(terms) != 1 or len(definitions) != 1:
            continue
        term = _inline(terms[0]).rstrip("：:")
        if term in {"服务人群", "服务仅限", "所属部门", "服务日期"}:
            metadata.append(node)
            if term == "所属部门":
                publisher = _inline(definitions[0])
    if len(titles) != 1 or not sections or not publisher:
        raise InvalidExport("missing_general_guide_identity")
    title = _inline(titles[0])
    item_code = _inline(codes[0]).removeprefix("事项编号：").strip() if codes else ""
    source_id = GUIDE_PATH.fullmatch(urlsplit(url).path)
    assert source_id is not None
    document_id = mapping.get("document_id", f"portal-{item_code or source_id[1]}")
    if not ID.fullmatch(document_id):
        raise InvalidExport("invalid_document_id")
    entrances: list[dict[str, str]] = []
    entrance_nodes: list[Node] = []
    for node in nodes:
        if "bl-item" not in node.attrs.get("class", "").split():
            continue
        name = node.attrs.get("data-blname") or _inline(node)
        reference = node.attrs.get("data-blpcurl", "")
        if not name:
            continue
        entrance_nodes.append(Node("p", children=[name]))
        if reference:
            try:
                entrances.append({"title": name, "url": _url(reference)})
            except ValueError:
                continue
    selected = titles + codes + sections + metadata
    if entrance_nodes:
        selected.append(Node("section", children=[Node("h2", children=["办理入口"]),
                                                  *entrance_nodes]))
    text = "\n\n".join(filter(None, (_visible(node) for node in selected))) + "\n"
    if len(text) < 40:
        raise InvalidExport("empty_guide_body")
    prefix = f"documents/{document_id}"
    files: dict[str, bytes] = {f"{prefix}/body.txt": text.encode("utf-8")}
    image_paths: dict[int, str] = {}
    attachments: list[dict[str, Any]] = []
    capture_assets: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    remote_images = _remote_images(_read(path))
    used: set[str] = set()
    for section in sections:
        for node in (n for n in _nodes(section) if n.tag == "img"):
            local_ref = node.attrs.get("src", "")
            if not local_ref or PurePosixPath(local_ref).name in UI_IMAGES:
                continue
            if urlsplit(local_ref).scheme:
                missing.append({"reason": "image_not_saved_locally"})
                continue
            try:
                image = _file(boundary, local_ref, base=path.parent, limit=MAX_ASSET)
            except InvalidExport as exc:
                if str(exc) != "missing_or_large_local_file":
                    raise
                missing.append({"local_ref": local_ref, "reason": "image_missing_or_large"})
                continue
            data = image.read_bytes()
            fmt = _format(data)
            if fmt is None:
                missing.append({"local_ref": local_ref, "reason": "missing_or_invalid_image"})
                continue
            hash_value = hashlib.sha256(data).hexdigest()
            filename = f"{prefix}/assets/{hash_value[:24]}.{'jpg' if fmt == 'jpeg' else fmt}"
            files[filename] = data
            image_paths[id(node)] = "assets/" + PurePosixPath(filename).name
            if filename in used:
                continue
            used.add(filename)
            explicit = node.attrs.get("data-original-src") or node.attrs.get("data-src")
            source_url = _url(explicit) if explicit else remote_images.get(image.name)
            record = {"attachment_id": "image-" + hash_value[:24], "file": filename,
                      "format": fmt, "sha256": hash_value, "text_verified": False,
                      "local_ref": local_ref}
            if source_url:
                attachments.append(record | {"url": source_url,
                    "url_evidence": "explicit_image_reference_in_saved_guide"})
            else:
                capture_record = {key: value for key, value in record.items()
                                  if key != "attachment_id"}
                capture_assets.append(capture_record | {"asset_id": record["attachment_id"],
                    "source_url": None,
                    "url_evidence": "browser_rewritten_local_reference_only"})
    external_references: list[str] = []
    for section in sections:
        for node in _nodes(section):
            if node.tag == "a" and node.attrs.get("href"):
                try:
                    external_references.append(_url(node.attrs["href"]))
                except ValueError:
                    continue
    safe = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>'
    safe += html.escape(title) + "</title></head><body><main>"
    safe += "".join(_safe_html(node, image_paths) for node in selected)
    safe += "</main></body></html>\n"
    files[f"{prefix}/original.html"] = safe.encode("utf-8")
    document = {
        "document_id": document_id, "url": url, "title": title, "publisher": publisher,
        "collected_at": collected, "collection_precision": "day", "channel": "browser_dom",
        "body_file": f"{prefix}/body.txt", "original_file": f"{prefix}/original.html",
        "body_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "published_on": None, "signed_on": None,
        "access_scope": mapping.get("access_scope", "authenticated_general"),
        "complete": not missing, "content_kind": "guide", "contains_personal_data": False,
        "legacy_source_ids": [], "attachments": attachments, "capture_assets": capture_assets,
        "clauses": [], "item_code": item_code or None, "external_references": sorted(
            set(external_references)), "service_entrances": entrances, "capture_issues": missing,
        "collection_note": "用户保存的渲染 DOM；日期按日记载，不推测发布时间或采集时分。"
            "仅保留指南正文、公开通用服务元数据和指南图片；移除个人中心、表单与脚本。",
        "provenance": {"original_kind": "rendered_dom", "saved_file": path.relative_to(root)
                       .as_posix(), "guide_source": "iframe_saved_from_url",
                       "retained_nodes": "title, item code, service-guide-item, service metadata",
                       "original_file_kind": "sanitized_guide_subtree",
                       "publication_date_known": False},
    }
    return document, files


def import_exports(source: Path, output: Path, collected_on: str,
                   map_file: Path | None = None) -> dict[str, Any]:
    """Read supplied exports and create a new immutable, unannotated package."""
    date.fromisoformat(collected_on)
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise InvalidExport("source_directory_missing")
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output):
        raise InvalidExport("output_must_be_new_and_separate")
    mapping = _mapping(map_file, source)
    documents: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    identities: dict[str, dict[str, Any]] = {}
    mapped: set[str] = set()
    duplicates = 0
    for path, boundary, url, dom in _discover(source):
        relative = path.relative_to(source).as_posix()
        document, document_files = _guide(path, boundary, url, dom, collected_on,
                                         mapping.get(relative, {}), source)
        if relative in mapping:
            mapped.add(relative)
        if url in identities:
            previous = identities[url]
            if (previous["body_sha256"] != document["body_sha256"]
                    or previous["title"] != document["title"]
                    or previous["publisher"] != document["publisher"]
                    or previous["document_id"] != document["document_id"]
                    or previous["attachments"] != document["attachments"]
                    or previous["capture_assets"] != document["capture_assets"]
                    or previous["complete"] != document["complete"]):
                raise InvalidExport("conflicting_duplicate_url")
            duplicates += 1
            continue
        if any(d["document_id"] == document["document_id"] for d in documents):
            raise InvalidExport("duplicate_document_id")
        identities[url] = document
        documents.append(document)
        files.update(document_files)
    if not documents:
        raise InvalidExport("no_general_guides_found")
    if set(mapping) != mapped:
        raise InvalidExport("mapped_file_not_referenced_guide")
    manifest = {"schema_version": 1, "documents": documents,
                "discovery": {"method": "referenced_saved_iframes_only",
                              "duplicate_captures_deduplicated": duplicates,
                              "browser_access": False, "personal_shell_retained": False}}
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="browser-import-", dir=output.parent) as temporary:
        staged = Path(temporary) / "package"
        staged.mkdir()
        for name, content in files.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        staged.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collected-on", required=True)
    parser.add_argument("--map", dest="map_file", type=Path)
    args = parser.parse_args()
    try:
        manifest = import_exports(args.source, args.output, args.collected_on, args.map_file)
        print(json.dumps({"documents": len(manifest["documents"]),
                          "complete": sum(d["complete"] for d in manifest["documents"]),
                          "annotated": False, "published": False}, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        reason = str(exc) if isinstance(exc, InvalidExport) else type(exc).__name__
        parser.exit(2, f"Saved HTML import failed ({reason}); no package written.\n")


if __name__ == "__main__":
    main()
