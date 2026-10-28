"""Keep source text intact; field selections are evidence-backed candidates."""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .person_names import HAN_CHARS, clean_name, is_person_name
from .profile_layouts import structured_profile
from .quality_fields import TITLE, fields_from_text, profile_card, profile_label_name

SECTION_KINDS = {
    "research": ("研究方向", "研究领域", "研究兴趣", "研究内容", "research interests", "research areas"),
    "publications": ("发表论文", "学术论文", "论文和专著", "代表性论文", "科研成果", "研究成果", "主要成果", "发表信息", "论文著作", "publications", "selected publications"),
}
GENERIC = re.compile(r"简介|简历|大学|学院|学校|师资|教师|教授|研究|论文|成果|联系|个人|团队|新闻|首页|主页|教育|教学|荣誉|奖励|项目|专利|课程|信息|学术|兼职|概况|内容|\bresearch\s+(?:group|team)\b|\b(?:news|university|college|department|faculty)\b", re.I)
PERSONAL_SECTIONS = {"个人简介", "个人信息", "基本信息", "联系方式", "联系信息", "教育经历", "工作经历", "教学工作", "contact", "contact information", "biography"}
TITLE_SEPARATOR = re.compile(
    r"\s*(?:[|｜—–]|-{2,}|(?<=\s)-(?=\s)|"
    r"(?<=[" + HAN_CHARS + r"])-|-(?=[" + HAN_CHARS + r"]))\s*"
)
PERSONAL_TITLE_SUFFIX = re.compile(r"(?:['’]s|['’])?\s+(?:personal\s+)?(?:home\s*page|website)$", re.I)


def text_of(node):
    return node.get_text("\n", strip=True) if node else ""


def matches_label(text, labels):
    value = text.strip().rstrip(":：").casefold()
    return any(value == label or value.startswith(label + ":") or value.startswith(label + "：") for label in labels)


def content_container(soup):
    for pattern in ("main, [role=main]", "article", "#vsb_content, .wp_articlecontent, .v_news_content, .article-content"):
        matches = soup.select(pattern)
        if matches:
            return matches[0] if len(matches) == 1 else None
    return None


def name_candidates(soup, identity_scope=None):
    candidates = []
    for node in soup.select("h1, h2, .arti_title, .news_title, .jsbt, title"):
        label = text_of(node).strip()
        chunks = TITLE_SEPARATOR.split(label) if node.name == "title" else [label]
        for chunk in chunks:
            if node.name == "title":
                chunk = PERSONAL_TITLE_SUFFIX.sub("", chunk)
                school_name = re.fullmatch(r".+(?:大学|学院)\s+(.+)", chunk)
                if school_name and re.search(r"(?:中文|英文|个人)主页", label):
                    visible = identity_scope if identity_scope is not None else soup
                    person = clean_name(school_name[1])
                    if any(clean_name(value) == person for value in visible.stripped_strings):
                        chunk = person
            chunk = re.sub(r"^姓名\s*[:：]\s*", "", chunk)
            chunk = re.sub(r"\s*[（(]?(?:" + TITLE.pattern + r")[）)]?$", "", chunk)
            candidate = clean_name(profile_label_name(chunk))
            if is_person_name(candidate) and not GENERIC.search(candidate):
                candidates.append({"value": candidate, "evidence": label,
                                   "rule": "page_title" if node.name == "title" else "person_heading",
                                   "score": 80 if node.name == "title" else 100})
    for match in re.finditer(r"姓名\s*[:：]\s*([^\n:：,，;；]{2,80})", text_of(soup)):
        candidate = clean_name(match[1])
        if is_person_name(candidate) and not GENERIC.search(candidate):
            candidates.append({"value": candidate, "evidence": match[0], "rule": "labelled_name", "score": 110})
    return sorted(candidates, key=lambda item: -item["score"])


def section_text(body):
    """Retain original section strings. A heading begins a new section."""
    result = {key: [] for key in SECTION_KINDS}
    active = None
    for line in text_of(body).splitlines():
        matched = next((kind for kind, labels in SECTION_KINDS.items()
                        if matches_label(line, labels)), None)
        if matched:
            active = matched
        elif line in {text_of(h) for h in body.select("h1,h2,h3,h4,h5,h6")}:
            active = None
        if active:
            result[active].append(line)
    return {key: "\n".join(lines) for key, lines in result.items()}


def field_material(text):
    lines, publication = [], False
    for line in text.splitlines():
        if matches_label(line, SECTION_KINDS["publications"]):
            publication = True
        elif matches_label(line, PERSONAL_SECTIONS) or matches_label(line, SECTION_KINDS["research"]) or line.startswith(("[个人页附件原文：", "[OCR 待复核：")):
            publication = False
        if not publication:
            lines.append(line)
    return "\n".join(lines)


def refresh_fields(record):
    """Include attachment text without replacing raw text with model summaries."""
    fields = fields_from_text(record["name"], field_material(record["biography"]), identity_bound=bool(record["name"]))
    record["field_evidence"].update(fields)
    record["title"] = fields["title"]["value"] if record["name"] and fields["title"]["score"] >= 88 else ""
    if "同等依据的职称不一致" in fields["anomalies"]:
        record["title"] = ""
    record["email"] = fields["email"]["value"] if record["name"] else ""
    for key in ("title", "email"):
        record["field_status"][key] = "found" if record[key] else "not_confirmed"
    record["warnings"] = list(dict.fromkeys(record["warnings"] + fields["anomalies"]))


def extract_html(data, url, selector=None, expected_name=None):
    soup = BeautifulSoup(data, "html.parser")
    page_text = text_of(soup)
    # Apply one ownership boundary before name, layout, card and field recovery.
    # The unmodified HTML and whole-page text remain separate source evidence.
    for tag in soup.select("nav,footer,aside"):
        tag.decompose()
    seed = content_container(soup)
    if selector:
        bodies = soup.select(selector)
        if len(bodies) != 1:
            raise ValueError("--selector must match exactly one content container")
        seed = bodies[0]
    identity_scope = BeautifulSoup(str(seed or soup.body or soup), "html.parser")
    for tag in identity_scope.select("nav,footer,aside,script,style"):
        tag.decompose()
    candidates = name_candidates(identity_scope)
    # Preserve the existing WebPlus personal-card template while excluding
    # unrelated site contacts. This is a known card, not a page-wide label scan.
    for card in soup.select(".topleft"):
        if card.select_one("h1.arti_title") and not card.find_parent(["aside", "nav", "footer"]):
            candidates.extend({**candidate, "rule": "known_profile_card"} for candidate in name_candidates(card))
    if soup.title:
        candidates += name_candidates(BeautifulSoup(str(soup.title), "html.parser"), identity_scope)
    candidates.sort(key=lambda item: -item["score"])
    warnings = []
    strong = {c["value"] for c in candidates if c["score"] >= 100}
    top = strong or ({c["value"] for c in candidates if c["score"] == candidates[0]["score"]} if candidates else set())
    name = next(iter(top)) if len(top) == 1 else ""
    name_state = "found" if name else ("conflict" if top else "not_stated")
    if expected_name and clean_name(expected_name) != name:
        warnings.append("expected_name_not_confirmed")
        name_state = "conflict"
        name = ""
    layout = structured_profile(soup, {name}) if name else None
    if selector:
        body, selection = seed, "explicit_selector"
    elif layout:
        body, selection = layout["body"], layout["rule"]
    else:
        body = seed
        selection = "content_container" if body else "whole_page_fallback"
        body = body or soup.body or soup
    card = layout["card"] if layout else profile_card(soup, body, {name} if name else set())
    body_copy = BeautifulSoup(str(body), "html.parser")
    for tag in body_copy.select("script,style,nav,footer,aside,template,svg"):
        tag.decompose()
    biography = text_of(body_copy)
    if card and re.sub(r"\s+", "", card) not in re.sub(r"\s+", "", biography):
        biography = card + "\n\n" + biography
    fields = fields_from_text(name, field_material(biography), identity_bound=bool(name))
    title = fields["title"]["value"] if name else ""
    email = fields["email"]["value"] if name else ""
    if fields["title"]["score"] < 88 or "同等依据的职称不一致" in fields["anomalies"]:
        title = ""
    if not name:
        warnings.append("identity_unresolved")
    if selection == "whole_page_fallback":
        warnings.append("content_boundary_needs_review")
    if not biography:
        warnings.append("no_readable_text")
    warnings.extend(fields["anomalies"])
    return {
        "name": name, "title": title, "email": email, "biography": biography,
        **section_text(body_copy), "content_selection": selection,
        "field_status": {"name": name_state, "title": "found" if title else "not_confirmed",
                         "email": "found" if email else "not_confirmed"},
        "field_evidence": {"name_candidates": candidates, **fields},
        "warnings": warnings, "review_required": True,
        "related_links": [{"text": text_of(a), "url": urljoin(url, a["href"])}
                          for a in body.select("a[href]")],
        "page_text": page_text, "content_html": str(body),
    }
