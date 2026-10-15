"""Run bounded, isolated browser probes against public CDUT documents.

Install DrissionPage/Crawl4AI into a separate virtual environment first. This
script never reads a user's profile, cookies or login state. Every attempt owns
one fresh browser instance and closes it. A successful page requires an article
content element; navigation text, a blank page or a JS challenge is not success.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

SEEDS = [
    "https://lib.cdut.edu.cn/fw/qtfw/kgsj.htm",
    "https://wxc.cdut.edu.cn/info/1012/1165.htm",
    "https://wxc.cdut.edu.cn/info/1006/3954.htm",
]
EXTRA_SAMPLES = [
    "https://gra.cdut.edu.cn/info/1007/5283.htm",
    "https://jcc.cdut.edu.cn/info/1012/2724.htm",
    "https://wxc.cdut.edu.cn/info/1013/1241.htm",
    "https://wxc.cdut.edu.cn/info/1006/3960.htm",
    "https://wxc.cdut.edu.cn/info/1006/3864.htm",
    "https://aao.cdut.edu.cn/info/1187/6960.htm",
    "https://aao.cdut.edu.cn/info/1187/6963.htm",
]
BROWSERS = {
    "chrome": Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    "edge": Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
}
ARTICLE_SELECTORS = "#vsb_content, #vsb_content_2, #vsb_content_1021"
PORTAL_SELECTORS = ".service-guide-item"


def portal_reference(manifest_path: Path, url: str) -> dict[str, Any]:
    """Bind semantic checks to the approved saved guide, without account state."""
    manifest = json.loads(manifest_path.read_bytes())
    document = next(row for row in manifest["documents"] if row["url"] == url)
    body_path = manifest_path.parent / document["body_file"]
    if not body_path.resolve().is_relative_to(manifest_path.parent.resolve()):
        raise ValueError("Unsafe portal reference")
    body = body_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != document["body_sha256"]:
        raise ValueError("Portal reference checksum mismatch")
    return {"document_id": document["document_id"], "title": document["title"],
            "item_code": str(document["item_code"]), "body": body.decode("utf-8"),
            "body_sha256": document["body_sha256"]}


def classify_portal(html: str, url: str, reference: dict[str, Any]) -> dict[str, Any]:
    """Inspect only saved-guide structures; selector absence alone says nothing about access."""
    from import_browser_exports import DOM, _inline, _nodes, _visible

    dom = DOM(html)
    nodes = _nodes(dom.root)
    titles = [node for node in nodes
              if "content-header-text-title" in node.attrs.get("class", "").split()]
    sections = [node for node in nodes
                if "service-guide-item" in node.attrs.get("class", "").split()]
    codes = [node for node in nodes if node.attrs.get("id") == "serviceCode"]
    metadata = []
    metadata_fields = []
    entrances = []
    for node in nodes:
        if node.tag == "dl":
            terms = [child for child in node.children
                     if not isinstance(child, str) and child.tag == "dt"]
            if len(terms) == 1:
                name = _inline(terms[0]).rstrip("：:")
                if name in {"服务人群", "服务仅限", "所属部门", "服务日期"}:
                    metadata.append(node)
                    metadata_fields.append(name)
        if "bl-item" in node.attrs.get("class", "").split():
            name = node.attrs.get("data-blname") or _inline(node)
            if name:
                entrances.append(name)
    body = "\n\n".join(filter(None, (_visible(node) for node in
                                    [*titles, *codes, *sections, *metadata])))
    if entrances:
        body += "\n\n办理入口\n\n" + "\n\n".join(entrances)
    normalized = re.sub(r"\s+", "", body)
    expected_lines = [re.sub(r"\s+", "", line) for line in reference["body"].splitlines()
                      if line.strip()]
    matched = sum(line in normalized for line in expected_lines)
    title_matches = len(titles) == 1 and _inline(titles[0]) == reference["title"]
    code_matches = bool(codes) and reference["item_code"] == (
        _inline(codes[0]).removeprefix("事项编号：").strip()
    )
    headings = {"基本信息", "办理流程", "其它说明"}
    structure = bool(sections) and all(heading in body for heading in headings)
    identity = title_matches and code_matches and {"服务人群", "所属部门", "服务日期"} <= set(
        metadata_fields
    )
    semantic = bool(expected_lines) and matched == len(expected_lines)
    success = identity and structure and semantic and len(body) >= 80
    challenge = "$_ts" in html or "HTTP Status 412" in html or "412 Precondition" in html
    login = bool(re.search(r"/(?:cas/)?login(?:[./?]|$)", url, re.IGNORECASE)) or any(
        node.tag == "input" and node.attrs.get("type", "").lower() == "password"
        for node in nodes
    )
    reason = ("portal_guide_all_reference_text_verified" if success else
              "login_page_without_complete_guide" if login else
              "challenge_without_complete_guide" if challenge and not structure else
              "portal_guide_selector_missing_access_unresolved" if not sections else
              "portal_guide_identity_or_reference_text_mismatch")
    return {"url": url, "document_id": reference["document_id"],
            "classifier": "portal_service_guide", "guide_selector": PORTAL_SELECTORS,
            "guide_nodes": len(sections), "body_chars": len(body),
            "title_matches_reference": title_matches, "item_code_matches_reference": code_matches,
            "expected_text_lines": len(expected_lines), "matched_text_lines": matched,
            "semantic_check": "all_saved_visible_guide_lines_exact_after_whitespace_normalization",
            "reference_body_sha256": reference["body_sha256"],
            "challenge_marker_present": challenge, "login_page_detected": login,
            "full_body_candidate": success, "reason": reason}


def now() -> str:
    return datetime.now(UTC).isoformat()


def save_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def environment(
    urls: list[str], browser: str, proxy_mode: str, headless: bool,
) -> dict[str, Any]:
    dns: dict[str, list[str] | dict[str, str]] = {}
    hosts = {urlsplit(url).hostname for url in urls}
    for host in sorted(value for value in hosts if value is not None):
        try:
            dns[host] = sorted({str(result[4][0]) for result in socket.getaddrinfo(host, 443)})
        except OSError as exc:
            dns[host] = {"error": str(exc)}
    versions: dict[str, str | None] = {}
    for name in ("DrissionPage", "crawl4ai", "playwright"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    proxy: dict[str, Any] = {}
    if sys.platform == "win32":
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            for name in ("ProxyEnable", "ProxyServer", "AutoConfigURL"):
                try:
                    value = winreg.QueryValueEx(key, name)[0]
                    # Never put proxy authentication or query parameters in a report.
                    if isinstance(value, str) and ("@" in value or "?" in value):
                        value = "configured (redacted)"
                    proxy[name] = value
                except FileNotFoundError:
                    pass
    return {
        "recorded_at": now(),
        "python": sys.version,
        "platform": platform.platform(),
        "package_versions": versions,
        "dns": dns,
        "system_proxy": proxy,
        "environment_proxy_variable_names": [
            name for name in os.environ if "proxy" in name.lower()
        ],
        "browser": browser,
        "browser_path": str(BROWSERS[browser]),
        "proxy_mode": proxy_mode,
        "headless": headless,
        "fresh_profile_per_attempt": True,
        "user_profile_or_credentials_copied": False,
        "browser_download_required": False,
        "challenge_vendor": "unknown; not inferred",
    }


def classify(html: str, url: str, out: Path, visible_body: str | None = None,
             reference: dict[str, Any] | None = None,
             summary_only: bool = False) -> dict[str, Any]:
    if reference is not None:
        return classify_portal(html, url, reference)
    BeautifulSoup = importlib.import_module("bs4").BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    nodes = soup.select(ARTICLE_SELECTORS)
    article = max(nodes, key=lambda node: len(node.get_text()), default=None)
    body = (visible_body if visible_body is not None else
            article.get_text("\n", strip=True) if article else "")
    challenge = "$_ts" in html or "HTTP Status 412" in html
    # Some legitimate pages keep challenge bootstrap in their head after loading:
    # challenge markers alone are insufficient to reject a complete article node.
    success = article is not None and len(body) >= 80
    out.mkdir(parents=True, exist_ok=True)
    if not summary_only:
        (out / "rendered.html").write_text(html, encoding="utf-8")
    result = {
        "url": url,
        "title": title,
        "html_bytes": len(html.encode("utf-8")),
        "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "article_selectors": ARTICLE_SELECTORS,
        "article_node_found": article is not None,
        "article_chars": len(body),
        "challenge_marker_present": challenge,
        "full_body_candidate": success,
        "reason": "article_body_requires_semantic_review" if success else (
            "challenge_without_article" if challenge else "missing_or_empty_article"
        ),
        "artifact_dir": str(out),
    }
    if success:
        assert article is not None
        if not summary_only:
            (out / "body.txt").write_text(body + "\n", encoding="utf-8")
            (out / "body.html").write_text(str(article), encoding="utf-8")
        result["tables"] = len(article.select("table"))
        result["images"] = [image.get("src") for image in article.select("img")]
        result["links"] = [
            {"text": link.get_text(" ", strip=True), "href": link.get("href")}
            for link in article.select("a[href]")
        ]
        result["body_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        result["attachment_links"] = [
            {"text": link.get_text(" ", strip=True), "href": link.get("href")}
            for link in soup.select("a[href]")
            if "download.jsp" in link.get("href", "")
            or urlsplit(link.get("href", "")).path.lower().endswith((".pdf", ".xlsx"))
        ]
    return result


def capture_assets(page: Any, result: dict[str, Any], out: Path) -> None:
    """Download explicit official image/attachment URLs inside this fresh browser.

    The browser's own public-site challenge state stays in that instance. No
    cookies or authentication state are exported or reused elsewhere.
    """
    links = [*result.get("images", []),
             *[item["href"] for item in result.get("attachment_links", [])]]
    outcomes = []
    for index, href in enumerate(dict.fromkeys(links)):
        asset_url = urljoin(result["url"], href)
        hostname = urlsplit(asset_url).hostname or ""
        if not hostname.endswith(".cdut.edu.cn"):
            outcomes.append({"url": asset_url, "status": "skipped_nonofficial"})
            continue
        asset = {"url": asset_url}
        try:
            payload = page.run_js(
                """return fetch(arguments[0], {credentials:'same-origin'}).then(async response => {
                    const buffer = await response.arrayBuffer();
                    if(buffer.byteLength > 8000000) throw Error('attachment exceeds 8MB bound');
                    const bytes = new Uint8Array(buffer);
                    let binary = '';
                    for (let start=0;start<bytes.length;start+=8192)
                        binary += String.fromCharCode(...bytes.subarray(start,start+8192));
                    return {status:response.status, type:response.headers.get('content-type'),
                            data:btoa(binary)};
                })""",
                asset_url,
                timeout=20,
            )
            raw = base64.b64decode(payload["data"])
            extension = ("png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else
                         "jpeg" if raw.startswith(b"\xff\xd8\xff") else
                         "pdf" if raw.startswith(b"%PDF-") else
                         "xlsx" if raw.startswith(b"PK\x03\x04") else None)
            asset.update({"http_status": payload["status"], "content_type": payload["type"],
                          "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            if payload["status"] == 200 and extension:
                filename = f"asset-{index + 1}.{extension}"
                (out / filename).write_bytes(raw)
                asset.update({"status": "downloaded", "file": filename, "format": extension})
            else:
                asset["status"] = "rejected_not_verified_attachment"
        except Exception as exc:
            asset.update({"status": "failed", "error_type": type(exc).__name__,
                          "error": str(exc)[:400]})
        outcomes.append(asset)
        time.sleep(0.5)
    result["asset_downloads"] = outcomes


def drission(url: str, browser: str, proxy_mode: str, out: Path, headless: bool,
             assets: bool, reference: dict[str, Any] | None = None,
             summary_only: bool = False) -> dict[str, Any]:
    library = importlib.import_module("DrissionPage")
    ChromiumOptions, ChromiumPage = library.ChromiumOptions, library.ChromiumPage

    options = ChromiumOptions(read_file=False)
    options.set_browser_path(str(BROWSERS[browser]))
    out.mkdir(parents=True, exist_ok=True)
    profile = (tempfile.TemporaryDirectory(prefix=".owned-profile-", dir=out)
               if summary_only else None)
    options.set_tmp_path(profile.name if profile else str(out / "profile"))
    options.auto_port()
    options.headless(headless)
    if not headless:
        options.set_argument("--start-minimized")
    options.set_argument("--disable-extensions")
    options.set_argument("--disable-background-networking")
    options.set_argument("--no-first-run")
    options.set_timeouts(base=12, page_load=25, script=12)
    options.set_retry(times=0, interval=1)
    if proxy_mode == "direct":
        options.set_argument("--no-proxy-server")
    page = None
    try:
        page = ChromiumPage(options)
        page.listen.start(url, res_type="Document")
        page.get(url, retry=0, timeout=25)
        time.sleep(4)
        visible_body = page.run_js(
            "const node=document.querySelector(arguments[0]); return node ? node.innerText : null",
            ARTICLE_SELECTORS,
        )
        result = classify(page.html, page.url, out, visible_body, reference, summary_only)
        packet = page.listen.wait(timeout=1, raise_err=False)
        statuses = []
        while packet:
            statuses.append(packet.response.status)
            next_packet = page.listen.wait(timeout=0.2, raise_err=False)
            if not next_packet:
                break
            packet = next_packet
        result["observed_document_http_statuses"] = statuses
        result["initial_http_status"] = statuses[0] if statuses else None
        result["http_status"] = statuses[-1] if statuses else None
        if not summary_only and packet and isinstance(packet.response.body, (str, bytes)):
            response_body = packet.response.body
            response_bytes = (response_body.encode("utf-8")
                              if isinstance(response_body, str) else response_body)
            (out / "server-response.bin").write_bytes(response_bytes)
            result["server_response_bytes"] = len(response_bytes)
            result["server_response_sha256"] = hashlib.sha256(response_bytes).hexdigest()
            result["server_response_challenge_marker"] = b"$_ts" in response_bytes
        result["browser_user_agent"] = page.run_js("return navigator.userAgent")
        if assets and result["full_body_candidate"]:
            capture_assets(page, result, out)
        return result
    finally:
        try:
            if page is not None:
                page.quit()
        finally:
            if profile is not None:
                profile.cleanup()


async def crawl(url: str, browser: str, proxy_mode: str, out: Path, headless: bool,
                reference: dict[str, Any] | None = None,
                summary_only: bool = False) -> dict[str, Any]:
    library = importlib.import_module("crawl4ai")
    AsyncWebCrawler, BrowserConfig = library.AsyncWebCrawler, library.BrowserConfig
    CacheMode, CrawlerRunConfig = library.CacheMode, library.CrawlerRunConfig

    args = ["--disable-extensions", "--disable-background-networking", "--no-first-run"]
    if proxy_mode == "direct":
        args.append("--no-proxy-server")
    if not headless:
        args.append("--start-minimized")
    config = BrowserConfig(
        browser_type="chromium",
        chrome_channel="msedge" if browser == "edge" else "chrome",
        headless=headless,
        verbose=False,
        ignore_https_errors=False,
        user_agent="",
        enable_stealth=False,
        use_managed_browser=False,
        use_persistent_context=False,
        create_isolated_context=True,
        storage_state=None,
        cookies=None,
        extra_args=args,
    )
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="domcontentloaded",
        page_timeout=25000,
        delay_before_return_html=4,
        word_count_threshold=1,
        verbose=False,
    )
    async with AsyncWebCrawler(config=config, base_directory=str(out / "cache")) as crawler:
        document = await crawler.arun(url=url, config=run_config)
        result = classify(document.html or "", document.url or url, out,
                          reference=reference, summary_only=summary_only)
        result.update({
            # Crawl4AI reports the initial navigation response. JS challenge
            # completion can yield a real body despite that initial 412.
            "initial_http_status": document.status_code,
            "collector_reported_success": document.success,
            "collector_error": (bool(document.error_message) if summary_only
                                else document.error_message or None),
        })
        return result


def clean_child_tree(pid: int) -> None:
    """Only terminate descendants of the attempt owned by this script."""
    psutil = importlib.import_module("psutil")

    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        parent.terminate()
        _, alive = psutil.wait_procs([*children, parent], timeout=3)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", choices=BROWSERS, default="chrome")
    parser.add_argument("--proxy-mode", choices=("system", "direct"), default="system")
    parser.add_argument("--tool", choices=("drission", "crawl", "both"), default="both")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--url", action="append", dest="urls")
    parser.add_argument("--include-extra", action="store_true")
    parser.add_argument("--headful", action="store_true", help="Use a minimized visible window")
    parser.add_argument("--capture-assets", action="store_true",
                        help="Drission only: download explicit public images and attachments")
    parser.add_argument("--portal-reference", type=Path,
                        help="Saved portal manifest for exact complete-guide semantic checks")
    parser.add_argument("--summary-only", action="store_true",
                        help="Do not save returned HTML, response bodies or screenshots")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker:
        result = {"started_at": now(), "tool": args.tool}
        try:
            reference = portal_reference(args.portal_reference, args.urls[0]) \
                if args.portal_reference else None
            result.update(drission(args.urls[0], args.browser, args.proxy_mode, args.output,
                                  not args.headful, args.capture_assets, reference,
                                  args.summary_only)
                          if args.tool == "drission" else
                          asyncio.run(crawl(args.urls[0], args.browser, args.proxy_mode,
                                            args.output,
                                            not args.headful, reference, args.summary_only)))
        except Exception as exc:
            result.update({"full_body_candidate": False, "reason": "collector_exception",
                           "error_type": type(exc).__name__})
            if not args.summary_only:
                result["error"] = str(exc)[:3000]
        result["finished_at"] = now()
        save_json(args.output / "result.json", result)
        return 0
    urls = args.urls or SEEDS
    if args.include_extra:
        urls = list(dict.fromkeys([*urls, *EXTRA_SAMPLES]))
    if not 1 <= args.trials <= 3:
        parser.error("trials must be between 1 and 3")
    tools = ("drission", "crawl") if args.tool == "both" else (args.tool,)
    report: dict[str, Any] = {
        "environment": environment(urls, args.browser, args.proxy_mode, not args.headful),
        "attempts": [],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for trial in range(1, args.trials + 1):
        for tool in tools:
            for index, url in enumerate(urls):
                attempt = args.output / f"trial-{trial}-{tool}-{index + 1}"
                attempt.mkdir(parents=True, exist_ok=True)
                command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--tool",
                           tool, "--browser", args.browser, "--proxy-mode", args.proxy_mode,
                           "--output", str(attempt), "--url", url]
                if args.headful:
                    command.append("--headful")
                if args.capture_assets:
                    command.append("--capture-assets")
                if args.portal_reference:
                    command.extend(("--portal-reference", str(args.portal_reference.resolve())))
                if args.summary_only:
                    command.append("--summary-only")
                with (attempt / "console.log").open("w", encoding="utf-8") as log:
                    process = subprocess.Popen(
                        command, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    try:
                        process.wait(timeout=65)
                    except subprocess.TimeoutExpired:
                        clean_child_tree(process.pid)
                        save_json(attempt / "result.json", {"url": url, "tool": tool,
                                  "full_body_candidate": False, "reason": "worker_timeout"})
                result_path = attempt / "result.json"
                result = json.loads(result_path.read_text(encoding="utf-8")) \
                    if result_path.exists() else {
                    "url": url, "tool": tool, "full_body_candidate": False,
                    "reason": "worker_failed", "return_code": process.returncode,
                }
                result["trial"] = trial
                report["attempts"].append(result)
                save_json(args.output / "report.json", report)
                print(json.dumps({"trial": trial, "tool": tool, "url": url,
                                  "body": result["full_body_candidate"],
                                  "reason": result["reason"]}, ensure_ascii=False), flush=True)
                time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
