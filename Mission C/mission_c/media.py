"""Read linked PDF material, retaining every unread medium as an explicit gap."""
from datetime import datetime, timezone
import hashlib
import io
import re
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .fetch import SourceError


def referenced_media(content, page_url):
    soup = BeautifulSoup(content, "html.parser")
    found = {}
    for tag in soup.select("[href], [src], [pdfsrc], [data-src], object[data]"):
        value = tag.get("pdfsrc") or tag.get("data-src") or tag.get("href") or tag.get("src") or tag.get("data")
        if not isinstance(value, str) or not value.strip():
            continue
        nested = parse_qs(urlsplit(value).query).get("file", [])
        target = urljoin(page_url, unquote(nested[0] if nested else value))
        if re.search(r"\.pdf(?:[?#]|$)", target, re.I):
            found[target] = "pdf"
        elif tag.name == "img":
            found[target] = "image"
        elif tag.name in {"iframe", "embed", "object"}:
            found[target] = "embedded_page"
    for value in re.findall(r'''["']([^"'<>\s]+\.pdf(?:\?[^"'<>\s]*)?)["']''', "\n".join(str(s) for s in soup.select("script")), re.I):
        found[urljoin(page_url, value)] = "pdf"
    return [{"url": url, "kind": kind} for url, kind in found.items()]


def pdf_text(data):
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > 200:
        raise SourceError("pdf_page_limit", "PDF 超过 200 页，保留原件，未将前段视为全文")
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        resources = page.get("/Resources", {})
        resources = resources.get_object() if hasattr(resources, "get_object") else resources
        objects = resources.get("/XObject", {})
        objects = objects.get_object() if hasattr(objects, "get_object") else objects
        has_images = any(obj.get_object().get("/Subtype") in {"/Image", "/Form"} for obj in objects.values())
        pages.append({"page": number, "text": text, "needs_ocr": not text.strip() or has_images})
    return {"pages": pages, "text": "\n\n".join(f"[page {p['page']}]\n{p['text']}" for p in pages),
            "status": "ocr_needed" if any(p["needs_ocr"] for p in pages) else "text_saved"}


def collect_media(content, page_url, folder, fetcher, ocr=False):
    records = []
    for index, reference in enumerate(referenced_media(content, page_url), 1):
        item = {**reference, "status": "not_read", "text": "", "review_required": True}
        records.append(item)
        if fetcher is None:
            item["reason"] = "offline_replay"
            continue
        if reference["kind"] != "pdf" and not (ocr and reference["kind"] == "image"):
            item["reason"] = "image_or_embedded_content_needs_review"
            continue
        if index > 100:
            item["reason"] = "attachment_limit"
            continue
        asset_folder = folder / "media" / f"{index:03d}"
        asset_folder.mkdir(parents=True)
        try:
            data, metadata = fetcher.get(reference["url"], allowed_host=urlsplit(page_url).netloc)
            source = asset_folder / ("source.pdf" if reference["kind"] == "pdf" else "source.bin")
            source.write_bytes(data)
            item.update(metadata, observed_at=datetime.now(timezone.utc).isoformat(),
                        sha256=hashlib.sha256(data).hexdigest(), source_file=source.relative_to(folder.parent).as_posix())
            if ocr:
                from .ocr_media import read_image, read_pdf
                if reference["kind"] == "pdf":
                    parsed = read_pdf(data, asset_folder, max_pages=200)
                    item.update(parsed, status="ocr_candidate" if parsed["ocr_pages"] else "text_saved")
                else:
                    parsed = read_image(data, asset_folder, reference["url"])
                    item.update(parsed)
                    item["source_file"] = (asset_folder / parsed["source_file"]).relative_to(folder.parent).as_posix()
            else:
                item.update(pdf_text(data))
            (asset_folder / "text.txt").write_text(item["text"], encoding="utf-8")
        except Exception as error:
            item.update(status="read_failed", reason=getattr(error, "code", type(error).__name__))
    return records
