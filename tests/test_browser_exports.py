"""SYNTHETIC saved-export fixtures. No real student or institutional records."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from campuspilot.official_knowledge import extract

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_URL = (
    "https://bsdt.cdut.edu.cn/EIP/nonlogin/elobby/service/introduction/synthetic-guide.htm"
)
SYNTHETIC_IMAGE = (
    "https://bsdt.cdut.edu.cn/EIP/nonlogin/fileupload/downloadfile.htm"
    "?id=synthetic-image.png&path=SYNTHETIC&name=SYNTHETIC.png"
)


def importer() -> ModuleType:
    name = "synthetic_browser_export_importer"
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/import_browser_exports.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def guide(body: str = "SYNTHETIC 适用于测试学生。这是合成步骤，不是大学事实。",
          image_url: bool = False) -> str:
    reference = f' data-original-src="{SYNTHETIC_IMAGE}"' if image_url else ""
    return f"""<!-- saved from url=(0100){SYNTHETIC_URL}?_t=123&_winid=SYNTHETIC -->
    <html><head><title>SYNTHETIC wrapper</title></head><body>
    <p class="content-header-text-title">SYNTHETIC general guide</p>
    <div id="serviceCode">事项编号：synthetic</div>
    <div id="count">SYNTHETIC visits must not be copied</div>
    <aside>SYNTHETIC_ACCOUNT_NAME must not be copied</aside>
    <div class="service-guide-item" id="basicContent"><h2>基本信息</h2>
      <table><tr><td>办理方式</td><td>SYNTHETIC online</td>
      <td>咨询电话</td><td>SYNTHETIC_PHONE</td></tr></table></div>
    <div class="service-guide-item" id="proceduresContent"><h2>办理流程</h2><p>{body}</p>
    <script>var token = 'SYNTHETIC_SESSION_SECRET';</script>
    <input value="SYNTHETIC_FORM_SECRET"><div style="display:none">SYNTHETIC_HIDDEN</div>
    <a onclick="SYNTHETIC_MUTATION()" href="javascript:SYNTHETIC_MUTATION()">SYNTHETIC text</a>
    <img src="./synthetic-image.png"{reference} onload="SYNTHETIC_EXEC()"></div>
    <dl><dt>所属部门：</dt><dd>SYNTHETIC publisher</dd></dl>
    <dl><dt>服务人群：</dt><dd>SYNTHETIC students</dd></dl>
    <dl style="display:none"><dt>服务仅限：</dt><dd>SYNTHETIC_HIDDEN_SCOPE</dd></dl>
    <script>var privateAccount='SYNTHETIC_ACCOUNT_SECRET';</script></body></html>"""


def fixture(tmp_path: Path, *, second: str | None = None,
            image_url: bool = False) -> tuple[Path, Path]:
    source = tmp_path / "source"
    assets = source / "SYNTHETIC_files"
    assets.mkdir(parents=True)
    (source / "SYNTHETIC.html").write_text(
        '<html><body><div>SYNTHETIC_PERSONAL_SHELL</div><script>SYNTHETIC_TOKEN</script>'
        '<iframe src="./SYNTHETIC_files/guide.html"></iframe>'
        '<iframe src="./SYNTHETIC_files/application.html"></iframe></body></html>',
        encoding="utf-8",
    )
    (assets / "guide.html").write_text(guide(image_url=image_url), encoding="utf-8")
    (assets / "application.html").write_text(
        '<!-- saved from url=(0070)https://bsdt.cdut.edu.cn/EIP/flow/SYNTHETIC-form.htm'
        '?session=SYNTHETIC_FORM_SESSION -->'
        '<html><form><input value="SYNTHETIC_PERSONAL_APPLICATION"></form></html>',
        encoding="utf-8",
    )
    (assets / "synthetic-image.png").write_bytes(b"\x89PNG\r\n\x1a\nSYNTHETIC image payload")
    # Unreferenced files must never be discovered, parsed or copied.
    (assets / "unreferenced.html").write_text("SYNTHETIC_PRIVATE_PROFILE", encoding="utf-8")
    if second is not None:
        (assets / "second.html").write_text(second, encoding="utf-8")
        with (source / "SYNTHETIC.html").open("a", encoding="utf-8") as handle:
            handle.write('<iframe src="./SYNTHETIC_files/second.html"></iframe>')
    return source, tmp_path / "package"


def test_preserves_guide_tables_and_local_images_without_private_shell(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    manifest = module.import_exports(source, output, "2026-10-14")
    assert len(manifest["documents"]) == 1
    document = manifest["documents"][0]
    assert document["url"] == SYNTHETIC_URL
    assert document["publisher"] == "SYNTHETIC publisher"
    assert document["item_code"] == "synthetic"
    assert document["complete"] is True
    assert document["channel"] == "browser_dom"
    assert document["collection_precision"] == "day"
    assert document["published_on"] is None
    assert document["attachments"] == []
    assert document["capture_assets"][0]["source_url"] is None
    assert document["capture_assets"][0]["asset_id"].startswith("image-")
    text = (output / document["body_file"]).read_text(encoding="utf-8")
    assert "办理方式\tSYNTHETIC online\t咨询电话\tSYNTHETIC_PHONE" in text
    original = (output / document["original_file"]).read_text(encoding="utf-8")
    assert "<table>" in original and '<img src="assets/' in original
    all_text = text + original + (output / "manifest.json").read_text(encoding="utf-8")
    for forbidden in ("ACCOUNT_NAME", "SESSION_SECRET", "FORM_SECRET", "HIDDEN_SCOPE",
                      "SYNTHETIC_HIDDEN", "PRIVATE_PROFILE", "PRIVATE_APPLICATION",
                      "PERSONAL_SHELL", "SYNTHETIC_TOKEN", "onclick", "onload", "javascript:",
                      "visits must not be copied", "<script", "<input", "<iframe"):
        assert forbidden not in all_text
    assert "SYNTHETIC_PERSONAL_SHELL" in (source / "SYNTHETIC.html").read_text(encoding="utf-8")
    report = extract(output)
    assert report["documents"][0]["status"] == "extracted"


def test_explicit_image_url_becomes_attachment(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path, image_url=True)
    document = module.import_exports(source, output, "2026-10-14")["documents"][0]
    assert document["attachments"][0]["url"] == SYNTHETIC_IMAGE
    assert document["attachments"][0]["text_verified"] is False
    assert document["capture_assets"] == []


def test_duplicate_urls_deduplicate_but_differing_bodies_fail(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path, second=guide())
    manifest = module.import_exports(source, output, "2026-10-14")
    assert len(manifest["documents"]) == 1
    assert manifest["discovery"]["duplicate_captures_deduplicated"] == 1
    (source / "SYNTHETIC_files/second.html").write_text(
        guide("SYNTHETIC changed procedure cannot silently overwrite earlier evidence."),
        encoding="utf-8",
    )
    with pytest.raises(module.InvalidExport, match="conflicting_duplicate_url"):
        module.import_exports(source, tmp_path / "conflict", "2026-10-14")
    assert not (tmp_path / "conflict").exists()


@pytest.mark.parametrize("reference", ["../SYNTHETIC.html", "%2e%2e/SYNTHETIC.html",
                                        "C:/SYNTHETIC.html", "/SYNTHETIC.html"])
def test_local_path_escape_rejected(tmp_path: Path, reference: str) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    (source / "SYNTHETIC.html").write_text(f'<iframe src="{reference}"></iframe>', encoding="utf-8")
    with pytest.raises(module.InvalidExport, match="unsafe_local_path"):
        module.import_exports(source, output, "2026-10-14")
    assert not output.exists()


def test_image_path_escape_is_rejected(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    page = source / "SYNTHETIC_files/guide.html"
    page.write_text(guide().replace("./synthetic-image.png", "../../SYNTHETIC.png"),
                    encoding="utf-8")
    with pytest.raises(module.InvalidExport, match="unsafe_local_path"):
        module.import_exports(source, output, "2026-10-14")


def test_unavailable_image_marks_capture_incomplete(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    (source / "SYNTHETIC_files/synthetic-image.png").write_bytes(b"")
    document = module.import_exports(source, output, "2026-10-14")["documents"][0]
    assert document["complete"] is False
    assert document["capture_issues"][0]["reason"] == "missing_or_invalid_image"
    assert extract(output)["documents"][0]["reason"] == "incomplete_document"


@pytest.mark.parametrize("mapping", [None, {"schema_version": 1, "documents": {}},
    {"schema_version": 1, "documents": [{"file": "../SYNTHETIC.html", "document_id": "test"}]},
    {"schema_version": 1, "documents": [{"file": "SYNTHETIC_files/guide.html",
                                         "document_id": "test", "url": "SYNTHETIC"}]},
    {"schema_version": 1, "documents": [{"file": "SYNTHETIC_files/guide.html",
                                         "document_id": "test", "access_scope": "private"}]}])
def test_malformed_maps_are_rejected(tmp_path: Path, mapping: object) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps(mapping), encoding="utf-8")
    with pytest.raises(module.InvalidExport):
        module.import_exports(source, output, "2026-10-14", map_file)
    assert not output.exists()


def test_map_can_bind_id_but_not_change_source_facts(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({"schema_version": 1, "documents": [{
        "file": "SYNTHETIC_files/guide.html", "document_id": "synthetic-stable-id",
        "access_scope": "public"}]}), encoding="utf-8")
    document = module.import_exports(source, output, "2026-10-14", map_file)["documents"][0]
    assert document["document_id"] == "synthetic-stable-id"
    assert document["access_scope"] == "public"
    assert document["url"] == SYNTHETIC_URL


def test_private_source_url_is_rejected(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    page = source / "SYNTHETIC_files/guide.html"
    page.write_text(guide().replace("?_t=123&_winid=SYNTHETIC", "?token=SYNTHETIC_SECRET"),
                    encoding="utf-8")
    with pytest.raises(module.InvalidExport, match="private_url_parameter"):
        module.import_exports(source, output, "2026-10-14")


def test_duplicate_map_and_unreferenced_map_are_rejected(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    map_file = tmp_path / "map.json"
    row = {"file": "SYNTHETIC_files/guide.html", "document_id": "synthetic-stable-id"}
    map_file.write_text(json.dumps({"schema_version": 1, "documents": [row, row]}),
                        encoding="utf-8")
    with pytest.raises(module.InvalidExport, match="duplicate_import_map"):
        module.import_exports(source, output, "2026-10-14", map_file)
    row["file"] = "SYNTHETIC_files/unreferenced.html"
    map_file.write_text(json.dumps({"schema_version": 1, "documents": [row]}), encoding="utf-8")
    with pytest.raises(module.InvalidExport, match="mapped_file_not_referenced_guide"):
        module.import_exports(source, output, "2026-10-14", map_file)


def test_direct_saved_guide_and_existing_output_guard(tmp_path: Path) -> None:
    module = importer()
    source = tmp_path / "source"
    source.mkdir()
    (source / "SYNTHETIC.html").write_text(guide(), encoding="utf-8")
    (source / "synthetic-image.png").write_bytes(b"\x89PNG\r\n\x1a\nSYNTHETIC")
    output = tmp_path / "package"
    assert len(module.import_exports(source, output, "2026-10-14")["documents"]) == 1
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(module.InvalidExport, match="output_must_be_new_and_separate"):
        module.import_exports(source, output, "2026-10-14")
    assert (output / "manifest.json").read_bytes() == before


def test_explicit_image_reference_in_original_description_is_preserved(tmp_path: Path) -> None:
    module = importer()
    source, output = fixture(tmp_path)
    page = source / "SYNTHETIC_files/guide.html"
    script = f'<script>var SYNTHETIC_ORIGINAL_DESCRIPTION = \'<img src="{SYNTHETIC_IMAGE}">\';'
    script += "var token='SYNTHETIC_NEVER_SAVE';</script>"
    page.write_text(guide().replace("</body>", script + "</body>"), encoding="utf-8")
    document = module.import_exports(source, output, "2026-10-14")["documents"][0]
    assert document["attachments"][0]["url"] == SYNTHETIC_IMAGE
    assert "SYNTHETIC_NEVER_SAVE" not in (output / document["original_file"]).read_text(
        encoding="utf-8")
