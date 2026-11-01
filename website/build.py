# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown>=3.7", "pygments>=2.18", "pyyaml>=6.0"]
# ///
"""Build the documentation website (GitHub Pages) into ``website/_site``.

Pages are Markdown files in ``website/pages`` with a front matter (``title``, ``description``);
``website/nav.yml`` orders them into tabs and groups. The decision records come straight from
``docs/adr``, and the Settings reference from ``website/data/settings.json``.

    uv run website/build.py            # build
    uv run website/build.py --serve    # build, then serve on http://localhost:8000
    uv run website/build.py --strict   # fail on a broken internal link (CI)

Besides plain Markdown (tables, fenced code, attribute lists), a page can use these blocks:

    :::note Optional title      callouts: note, tip, info, warning, danger, privacy
    ...
    :::

    :::steps                    numbered steps; each starts with "@step Title"
    @step Install
    ...
    :::

    :::tabs                     tabbed panels; each starts with "@tab Label"
    @tab Dashboard
    ...
    :::

    :::cards 2                  a grid of link cards, one per line: icon | [Title](/link) | text
    rocket | [Quickstart](/quickstart) | From a fresh clone to a first reminder.
    :::

    ::video src=/assets/media/x.webm poster=/assets/media/x.webp caption="..." url=localhost:8501
    ::image src=/assets/media/x.webp alt="..." caption="..." url=localhost:8501/reminders
    ::settings groups=privacy,reminder
    ::pipeline
    ::adr-list
    ::thesis-banner · ::thesis-facts · ::thesis-logos    (from the thesis block in nav.yml)

Links that start with ``/`` point at pages or assets from the site root and are made relative,
so the site works under any base path; ``gh:path`` links to a file in the repository.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shlex
import shutil
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import markdown
import yaml
from pygments.formatters import HtmlFormatter
from pygments.styles import get_all_styles

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PAGES = HERE / "pages"
ASSETS = HERE / "assets"
OUT = HERE / "_site"

NAV = yaml.safe_load((HERE / "nav.yml").read_text(encoding="utf-8"))
SITE: dict[str, Any] = NAV["site"]
THESIS: dict[str, Any] = NAV["thesis"]
ICONS: dict[str, str] = yaml.safe_load((HERE / "icons.yml").read_text(encoding="utf-8"))
CALLOUTS = {"note", "tip", "info", "warning", "danger", "privacy"}
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
OPEN = re.compile(r"^:::([a-z-]+)\s*(.*)$")
DIRECTIVE = re.compile(r"^::([a-z-]+)\s*(.*)$")


def icon(name: str, cls: str = "icon") -> str:
    body = ICONS.get(name) or ICONS["circle"]
    return (
        f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{body}</svg>"
    )


@dataclass
class Page:
    slug: str
    title: str
    description: str
    source: str
    edit_path: str
    nav_title: str
    badge: str = ""
    tab: str = ""
    group: str = ""
    html: str = ""
    toc: list[dict[str, Any]] = field(default_factory=list)
    uses_mermaid: bool = False

    @property
    def url(self) -> str:
        return f"{self.slug}.html"


# ---------------------------------------------------------------------------------------------
# Loading


def front_matter(text: str) -> tuple[dict[str, str], str]:
    """``key: value`` lines between ``---`` lines; a value is the rest of its line, as written."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}, text
    meta = dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)
    return {key.strip(): value.strip() for key, value in meta.items()}, text[match.end() :]


def load_pages() -> dict[str, Page]:
    pages: dict[str, Page] = {}
    for path in sorted(PAGES.rglob("*.md")):
        meta, body = front_matter(path.read_text(encoding="utf-8"))
        slug = path.relative_to(PAGES).with_suffix("").as_posix()
        pages[slug] = Page(
            slug=slug,
            title=meta.get("title", slug),
            description=meta.get("description", ""),
            source=body,
            edit_path=path.relative_to(REPO).as_posix(),
            nav_title=meta.get("nav", meta.get("title", slug)),
        )
    for page in adr_pages():
        pages[page.slug] = page
    return pages


def adr_pages() -> list[Page]:
    """The decision records in docs/adr, as they are (with their status as a badge)."""
    found = sorted((REPO / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    stems = {path.stem[:4]: path.stem for path in found}
    pages = []
    for path in found:
        first, _, body = path.read_text(encoding="utf-8").partition("\n")
        match = re.match(r"#\s*(\d{4})\s*[,:.-]?\s*(.+)", first)
        number, title = (
            (match.group(1), match.group(2).strip()) if match else (path.stem[:4], first)
        )
        body = body.replace(" , ", ", ")
        body = re.sub(
            r"(?m)^(?![ \t]*[-*] )(\S.*)\n(?=[ \t]*- )", r"\1\n\n", body
        )  # list after text
        status = ""
        if found_status := re.search(r"\*\*Status:\*\*\s*(.+)", body):
            status = found_status.group(1).strip()
            pill = status.split()[0].capitalize()
            rest = html.escape(status[len(status.split()[0]) :].strip(" ()"))
            body = body.replace(
                found_status.group(0),
                f'<p class="adr-status"><span class="pill pill-ok">{pill}</span>'
                f'<span class="adr-meta">ADR&nbsp;{number}'
                f"{' · ' + rest if rest else ''}</span></p>",
            )
        body = re.sub(
            r"(?<![\[/])ADR (\d{4})",
            lambda m: (
                f"[ADR {m.group(1)}](/decisions/{stems[m.group(1)]})"
                if m.group(1) in stems
                else m.group(0)
            ),
            body,
        )
        for doc, slug in {
            "docs/PRIVACY.md": "/reference/privacy",
            "docs/HARDWARE_SETUP.md": "/hardware/overview",
            "docs/ARCHITECTURE.md": "/reference/architecture",
        }.items():
            body = body.replace(f"({doc})", f"([{doc}]({slug}))").replace(
                f" {doc}", f" [{doc}]({slug})"
            )
        pages.append(
            Page(
                slug=f"decisions/{path.stem}",
                title=title,
                description=f"Architecture decision record {number}: {status or 'accepted'}.",
                source=body,
                edit_path=path.relative_to(REPO).as_posix(),
                nav_title=title,
                badge=number,
            )
        )
    return pages


def ordered(pages: dict[str, Page]) -> list[tuple[str, str, list[Page]]]:
    """(tab, group, pages) in navigation order; also stamps each page with its tab and group."""
    groups = []
    for tab in NAV["tabs"]:
        for group in tab["groups"]:
            members: list[Page] = []
            for slug in group["pages"]:
                if slug == "adr:*":
                    members += [p for s, p in sorted(pages.items()) if s.startswith("decisions/0")]
                elif slug in pages:
                    members.append(pages[slug])
                else:
                    sys.exit(f"nav.yml lists {slug!r}, but website/pages/{slug}.md does not exist")
            for page in members:
                page.tab, page.group = tab["name"], group["name"]
            groups.append((tab["name"], group["name"], members))
    return groups


# ---------------------------------------------------------------------------------------------
# Markdown with the extra blocks


def converter() -> markdown.Markdown:
    return markdown.Markdown(
        extensions=["extra", "toc", "codehilite", "sane_lists"],
        extension_configs={
            "toc": {"toc_depth": "2-3", "permalink": "#", "permalink_class": "anchor"},
            "codehilite": {"css_class": "highlight", "guess_lang": False},
        },
        output_format="html",
    )


def render_fragment(text: str, page: Page) -> str:
    """Markdown inside a block (callout, step, tab) rendered on its own."""
    return converter().convert(expand(text, page))


def inline(text: str) -> str:
    out = converter().convert(text)
    return re.sub(r"^<p>(.*)</p>$", r"\1", out.strip(), flags=re.S)


def attrs(text: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in shlex.split(text) if "=" in part)


def blocks(lines: list[str]) -> Iterator[tuple[str, Any]]:
    """Split lines into ("text", line), ("block", (name, arg, inner lines)) and fenced code."""
    i = 0
    while i < len(lines):
        line = lines[i]
        fence = FENCE.match(line)
        if fence:
            marker, info = fence.group(2), fence.group(3).strip()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(marker):
                j += 1
            if info == "mermaid":
                yield "mermaid", "\n".join(lines[i + 1 : j])
            elif info and not fence.group(1):  # rendered on its own, labelled with its language
                yield "code", (info.split()[0], "\n".join(lines[i : j + 1]))
            else:
                yield from (("text", raw) for raw in lines[i : j + 1])
            i = j + 1
            continue
        opened = OPEN.match(line)
        if opened:
            depth, j = 1, i + 1
            while j < len(lines):
                if FENCE.match(lines[j]):  # skip code inside the block
                    marker = FENCE.match(lines[j]).group(2)  # type: ignore[union-attr]
                    j += 1
                    while j < len(lines) and not lines[j].strip().startswith(marker):
                        j += 1
                elif OPEN.match(lines[j]):
                    depth += 1
                elif lines[j].strip() == ":::":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            yield "block", (opened.group(1), opened.group(2).strip(), lines[i + 1 : j])
            i = j + 1
            continue
        directive = DIRECTIVE.match(line)
        if directive:
            yield "directive", (directive.group(1), directive.group(2))
        else:
            yield "text", line
        i += 1


def split_on(lines: list[str], marker: str) -> list[tuple[str, list[str]]]:
    parts: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith(marker):
            parts.append((line[len(marker) :].strip(), []))
        elif parts:
            parts[-1][1].append(line)
    return parts


def expand(text: str, page: Page) -> str:
    out: list[str] = []
    for kind, value in blocks(text.split("\n")):
        if kind == "text":
            out.append(value)
        elif kind == "mermaid":
            page.uses_mermaid = True
            out.append(
                f'\n<div class="diagram"><pre class="mermaid">{html.escape(value)}</pre></div>\n'
            )
        elif kind == "code":
            lang, fenced = value
            rendered = converter().convert(fenced)
            out.append(
                f'\n<div class="code-block" data-lang="{html.escape(lang)}">{rendered}</div>\n'
            )
        elif kind == "directive":
            out.append("\n" + render_directive(*value) + "\n")
        else:
            out.append("\n" + render_block(*value, page=page) + "\n")
    return "\n".join(out)


def render_block(name: str, arg: str, lines: list[str], page: Page) -> str:
    body = "\n".join(lines)
    if name in CALLOUTS:
        title = f'<p class="callout-title">{inline(arg)}</p>' if arg else ""
        return (
            f'<div class="callout callout-{name}">{icon(callout_icon(name), "callout-icon")}'
            f'<div class="callout-body">{title}{render_fragment(body, page)}</div></div>'
        )
    if name == "steps":
        steps = "".join(
            f'<div class="step"><p class="step-title">{inline(title)}</p>'
            f'<div class="step-body">{render_fragment(chr(10).join(inner), page)}</div></div>'
            for title, inner in split_on(lines, "@step")
        )
        return f'<div class="steps">{steps}</div>'
    if name == "tabs":
        panels = split_on(lines, "@tab")
        buttons = "".join(
            f'<button class="tab" role="tab" aria-selected="{"true" if i == 0 else "false"}">'
            f"{html.escape(label)}</button>"
            for i, (label, _) in enumerate(panels)
        )
        bodies = "".join(
            f'<div class="tab-panel" role="tabpanel"{"" if i == 0 else " hidden"}>'
            f"{render_fragment(chr(10).join(inner), page)}</div>"
            for i, (_, inner) in enumerate(panels)
        )
        tab_list = f'<div class="tab-list" role="tablist">{buttons}</div>'
        return f'<div class="tabs" data-tabs>{tab_list}{bodies}</div>'
    if name == "cards":
        cols = arg or "2"
        cards = []
        for line in filter(str.strip, lines):
            glyph, link, text = (part.strip() for part in line.split("|", 2))
            match = re.match(r"\[(.+?)\]\((.+?)\)", link)
            if not match:
                sys.exit(f"{page.slug}: a card needs [Title](link): {line!r}")
            title, href = match.groups()
            external = href.startswith("http")
            cards.append(
                f'<a class="card" href="{href}"{" target=_blank rel=noopener" if external else ""}>'
                f'<span class="card-icon">{icon(glyph)}</span>'
                f'<span class="card-title">{inline(title)}</span>'
                f'<span class="card-text">{inline(text)}</span>'
                f"{icon('arrow-up-right', 'card-arrow')}</a>"
            )
        return f'<div class="cards cols-{cols}">{"".join(cards)}</div>'
    sys.exit(f"{page.slug}: unknown block :::{name}")


def callout_icon(name: str) -> str:
    return {
        "note": "info",
        "info": "info",
        "tip": "lightbulb",
        "warning": "triangle-alert",
        "danger": "octagon-x",
        "privacy": "shield-check",
    }[name]


def frame(url: str, inner: str, caption: str) -> str:
    bar = (
        '<div class="frame-bar"><span class="dots"><i></i><i></i><i></i></span>'
        f'<span class="frame-url">{icon("lock")}{html.escape(url)}</span></div>'
        if url
        else ""
    )
    cap = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
    return f'<figure class="media{" framed" if url else ""}">{bar}{inner}{cap}</figure>'


def render_directive(name: str, arg: str) -> str:
    a = attrs(arg)
    if name == "video":
        inner = (
            f'<video src="{a["src"]}" poster="{a.get("poster", "")}" muted loop playsinline '
            f'preload="metadata" controls data-autoplay '
            f'aria-label="{html.escape(a.get("caption", ""))}">'
            "</video>"
        )
        return frame(a.get("url", ""), inner, a.get("caption", ""))
    if name == "image":
        inner = (
            f'<img src="{a["src"]}" alt="{html.escape(a.get("alt", ""))}" loading="lazy" '
            f'data-zoom width="1512" height="794">'
        )
        return frame(a.get("url", ""), inner, a.get("caption", ""))
    if name == "settings":
        return settings_table([g.strip() for g in a.get("groups", "").split(",") if g.strip()])
    if name == "pipeline":
        return pipeline()
    if name == "adr-list":
        return adr_list()
    if name == "thesis-banner":
        return thesis_banner()
    if name == "thesis-facts":
        return thesis_facts()
    if name == "thesis-logos":
        return thesis_logos("logo-row")
    sys.exit(f"unknown directive ::{name}")


def thesis_logos(cls: str, *, linked: bool = True) -> str:
    """The university's, the faculty's and the research group's logos, each linking to them
    unless the logos sit inside another link."""
    tiles = []
    for logo in THESIS["logos"]:
        alt = html.escape(logo["alt"])
        img = f'<img src="{logo["src"]}" alt="{alt}" loading="lazy">'
        tiles.append(
            f'<a class="logo-tile" href="{logo["href"]}" target="_blank" rel="noopener" '
            f'title="{alt}">{img}</a>'
            if linked
            else f'<span class="logo-tile">{img}</span>'
        )
    return f'<div class="{cls}">{"".join(tiles)}</div>'


def thesis_banner() -> str:
    # A block card (a link around blocks would be split up inside a paragraph); its one link
    # stretches over the whole card in CSS.
    return (
        '<div class="thesis-banner">'
        f'<span class="thesis-kicker">{icon("book-open")}Master\'s thesis</span>'
        f"<p class=\"thesis-text\">PASR is the software of {THESIS['author']}'s Master's thesis "
        f"at the {THESIS['university'].split(',')[0]}, supervised by {supervisors()}.</p>"
        f"{thesis_logos('thesis-banner-logos', linked=False)}"
        f'<a class="thesis-more" href="/thesis">About the thesis{icon("chevron-right")}</a></div>'
    )


def supervisors() -> str:
    return " and ".join(person["name"] for person in THESIS["supervisors"])


def thesis_facts() -> str:
    rows = [
        ("Title", f"<em>{html.escape(THESIS['title'])}</em>"),
        ("Author", THESIS["author"]),
        ("Degree", THESIS["degree"]),
        ("University", THESIS["university"]),
        ("Faculty", THESIS["faculty"]),
        ("Department", THESIS["department"]),
        ("Research group", THESIS["group"]),
        *((person["role"], person["name"]) for person in THESIS["supervisors"]),
        ("Period", THESIS["period"]),
    ]
    body = "".join(f"<tr><th>{label}</th><td>{value}</td></tr>" for label, value in rows)
    return f'<table class="facts"><tbody>{body}</tbody></table>'


STAGES = [
    ("Schedule", "alarm-clock", "The reminder waits in the database until its wake-up time."),
    ("Wake", "zap", "7 min early if sensitive and checked, 2 min with the camera only."),
    ("Presence", "watch", "Ping the owner's watch. No answer: nothing is sensed or said."),
    ("Listen", "audio-lines", "Voices that are not the owner's mean a bystander."),
    ("Scan", "scan-face", "Look left, front and right for silent bystanders."),
    ("Decide", "scale", "One pure function: speak, ask, or send it to the watch."),
    ("Consent", "message-square", "Ask on the watch: Yes, No, or no answer (= No)."),
    ("Deliver", "volume-2", "At the due time: out loud, or privately on the watch."),
]


def pipeline() -> str:
    items = "".join(
        f'<li class="stage"><span class="stage-dot">{icon(glyph)}</span>'
        f'<span class="stage-num">{i}</span><span class="stage-name">{name}</span>'
        f'<span class="stage-text">{text}</span></li>'
        for i, (name, glyph, text) in enumerate(STAGES, 1)
    )
    return f'<ol class="pipeline">{items}</ol>'


SETTINGS_FILE = HERE / "data" / "settings.json"


def settings_table(groups: list[str]) -> str:
    rows = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    chosen = [r for r in rows if not groups or r["group"] in groups]
    body = []
    for row in chosen:
        default = row["default"]
        shown = json.dumps(default, ensure_ascii=False) if not isinstance(default, str) else default
        if shown in ("", "null"):
            shown = "—" if shown == "" else "null"
        limits = (
            f'<span class="limits">{html.escape(", ".join(row["limits"]))}</span>'
            if row["limits"]
            else ""
        )
        body.append(
            f'<tr id="{row["key"]}"><td><code>{row["key"]}</code>'
            f'<span class="pill pill-{row["tier"]}">{row["tier"]}</span></td>'
            f"<td><code>{html.escape(shown)}</code>{limits}</td>"
            f"<td>{inline(row['description'])}</td></tr>"
        )
    return (
        '<table class="settings"><thead><tr><th>Setting</th>'
        f"<th>Default</th><th>What it does</th></tr></thead><tbody>{''.join(body)}</tbody>"
        "</table>"
    )


ADR_ROWS: list[Page] = []


def adr_list() -> str:
    cards = "".join(
        f'<a class="card adr-card" href="/{p.slug}"><span class="adr-num">{p.badge}</span>'
        f'<span class="card-title">{html.escape(p.title)}</span>'
        f"{icon('arrow-up-right', 'card-arrow')}</a>"
        for p in ADR_ROWS
    )
    return f'<div class="cards cols-2">{cards}</div>'


def render(page: Page) -> None:
    md = converter()
    body = md.convert(expand(page.source, page))
    body = re.sub(r"<table([^>]*)>", r'<div class="table-wrap"><table\1>', body)
    page.html = body.replace("</table>", "</table></div>")
    page.toc = md.toc_tokens  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------------------------
# Links


def make_relative(text: str, page: Page, slugs: set[str], broken: list[str]) -> str:
    prefix = "../" * page.slug.count("/")
    repo = SITE["repo"]

    def fix(match: re.Match[str]) -> str:
        attr, target = match.group(1), match.group(2)
        if target.startswith("gh:"):
            return f'{attr}="{repo}/blob/{SITE["branch"]}/{target[3:]}"'
        if target.startswith("gh-tree:"):
            return f'{attr}="{repo}/tree/{SITE["branch"]}/{target[8:]}"'
        if not target.startswith("/") or target.startswith("//"):
            return match.group(0)
        path, _, anchor = target[1:].partition("#")
        if path.startswith("assets/") or path.endswith((".js", ".xml", ".json")):
            resolved = path
        else:
            path = path.rstrip("/") or "index"
            if path not in slugs:
                broken.append(f"{page.slug}: {target}")
            resolved = f"{path}.html"
        return f'{attr}="{prefix}{resolved}{"#" + anchor if anchor else ""}"'

    return re.sub(r'\b(href|src|poster)="([^"]*)"', fix, text)


# ---------------------------------------------------------------------------------------------
# Page template


def tab_links(page: Page, first_of_tab: dict[str, Page]) -> str:
    return "".join(
        f'<a class="tab-link{" is-active" if tab["name"] == page.tab else ""}" '
        f'href="/{first_of_tab[tab["name"]].slug}">{icon(tab["icon"])}'
        f"<span>{tab['name']}</span></a>"
        for tab in NAV["tabs"]
    )


def sidebar(
    page: Page, groups: list[tuple[str, str, list[Page]]], first_of_tab: dict[str, Page]
) -> str:
    mobile_tabs = "".join(
        f'<a class="drawer-tab{" is-active" if tab["name"] == page.tab else ""}" '
        f'href="/{first_of_tab[tab["name"]].slug}">{icon(tab["icon"])}{tab["name"]}</a>'
        for tab in NAV["tabs"]
    )
    parts = [f'<div class="drawer-tabs">{mobile_tabs}</div>']
    for tab, group, members in groups:
        if tab != page.tab:
            continue
        links = "".join(
            f'<li><a class="nav-link{" is-active" if p.slug == page.slug else ""}" href="/{p.slug}"'
            f"{' aria-current=page' if p.slug == page.slug else ''}>"
            f"{f'<span class=nav-badge>{p.badge}</span>' if p.badge else ''}"
            f"<span>{html.escape(p.nav_title)}</span></a></li>"
            for p in members
        )
        parts.append(
            f'<div class="nav-group"><p class="nav-group-title">{group}</p><ul>{links}</ul></div>'
        )
    nav = f'<nav aria-label="Pages">{"".join(parts)}</nav>'
    return f'<aside class="sidebar" id="sidebar">{nav}</aside>'


def toc_html(page: Page) -> str:
    items = []
    for h2 in page.toc:
        items.append(f'<li><a href="#{h2["id"]}" data-toc>{h2["name"]}</a></li>')
        for h3 in h2.get("children", []):
            items.append(
                f'<li class="toc-sub"><a href="#{h3["id"]}" data-toc>{h3["name"]}</a></li>'
            )
    if not items:
        return '<aside class="toc"></aside>'
    return (
        f'<aside class="toc"><p class="toc-title">{icon("align-left")}On this page</p>'
        f"<ul>{''.join(items)}</ul></aside>"
    )


def pager(page: Page, flat: list[Page]) -> str:
    i = flat.index(page)
    prev = flat[i - 1] if i > 0 else None
    nxt = flat[i + 1] if i + 1 < len(flat) else None
    out = []
    if prev:
        out.append(
            f'<a class="pager-link prev" href="/{prev.slug}"><span class="pager-label">'
            f"{icon('chevron-left')}Previous</span>"
            f'<span class="pager-title">{html.escape(prev.title)}</span></a>'
        )
    else:
        out.append("<span></span>")
    if nxt:
        out.append(
            f'<a class="pager-link next" href="/{nxt.slug}"><span class="pager-label">Next'
            f"{icon('chevron-right')}</span>"
            f'<span class="pager-title">{html.escape(nxt.title)}</span></a>'
        )
    return f'<nav class="pager" aria-label="Previous and next page">{"".join(out)}</nav>'


def footer_columns() -> str:
    return "".join(
        f'<div class="footer-col"><p>{col["name"]}</p><ul>'
        + "".join(f'<li><a href="{link["href"]}">{link["text"]}</a></li>' for link in col["links"])
        + "</ul></div>"
        for col in NAV["footer"]
    )


MERMAID = """
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";
window.PASR_MERMAID = mermaid;
document.dispatchEvent(new Event("pasr:mermaid"));
</script>"""


TEMPLATE = (HERE / "template.html").read_text(encoding="utf-8")
SLOT = re.compile(r"\{\{(icon:)?([\w-]+)(?::([\w -]+))?\}\}")


def document(page: Page, chrome: dict[str, str]) -> str:
    repo, branch = SITE["repo"], SITE["branch"]
    values = {
        "title": html.escape(page.title if page.slug == "index" else f"{page.title} · PASR docs"),
        "description": html.escape(page.description),
        "canonical": SITE["url"].rstrip("/") + "/" + page.url,
        "og_image": SITE["url"].rstrip("/") + "/assets/media/home.webp",
        "page_title": html.escape(page.title),
        "group": html.escape(page.group),
        "lead": f'<p class="lead">{inline(page.description)}</p>' if page.description else "",
        "body": page.html,
        "raw": html.escape(page.source),
        "view": f"{repo}/blob/{branch}/{page.edit_path}",
        "edit": f"{repo}/edit/{branch}/{page.edit_path}",
        "repo": repo,
        "repo_name": repo.removeprefix("https://github.com/"),
        "tagline": SITE["tagline"],
        "blurb": SITE["blurb"],
        "author": SITE["author"],
        "year": str(date.today().year),
        "mermaid": MERMAID if page.uses_mermaid else "",
        "thesis_logos": thesis_logos("footer-logos"),
        "thesis_line": html.escape(
            f"Master's thesis of {THESIS['author']}, {THESIS['university'].split(',')[0]}, "
            f"supervised by {supervisors()}"
        ),
        **chrome,
    }

    def fill(match: re.Match[str]) -> str:
        is_icon, name, cls = match.groups()
        return icon(name, cls or "icon") if is_icon else values[name]

    return SLOT.sub(fill, TEMPLATE)


# ---------------------------------------------------------------------------------------------
# Search index


def strip_tags(text: str) -> str:
    text = re.sub(r'<a class="anchor"[^>]*>.*?</a>', "", text)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def index_entries(page: Page) -> list[dict[str, str]]:
    parts = re.split(r'(<h[23][^>]*id="([^"]+)"[^>]*>(.*?)</h[23]>)', page.html, flags=re.S)
    entries = [
        {"t": page.title, "h": "", "u": page.url, "g": page.group, "x": strip_tags(parts[0])[:400]}
    ]
    for i in range(1, len(parts), 4):
        anchor, heading, content = parts[i + 1], strip_tags(parts[i + 2]), parts[i + 3]
        entries.append(
            {
                "t": page.title,
                "h": heading,
                "u": f"{page.url}#{anchor}",
                "g": page.group,
                "x": strip_tags(content)[:400],
            }
        )
    return entries


# ---------------------------------------------------------------------------------------------
# Build


def pygments_css() -> str:
    style = "github-dark" if "github-dark" in set(get_all_styles()) else "monokai"
    css = HtmlFormatter(style=style).get_style_defs(".highlight")
    return re.sub(
        r"\.highlight \{ background: [^;]+; \}", ".highlight { background: transparent; }", css
    )


def build(strict: bool) -> int:
    pages = load_pages()
    ADR_ROWS[:] = [p for s, p in sorted(pages.items()) if s.startswith("decisions/0")]
    groups = ordered(pages)
    flat = [p for _, _, members in groups for p in members]
    missing = set(pages) - {p.slug for p in flat}
    if missing:
        print(f"warning: not in nav.yml: {', '.join(sorted(missing))}")
    first_of_tab: dict[str, Page] = {}
    for tab, _, members in groups:
        first_of_tab.setdefault(tab, members[0])

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ASSETS, OUT / "assets")
    (OUT / "assets" / "pygments.css").write_text(pygments_css(), encoding="utf-8")

    slugs = set(pages)
    broken: list[str] = []
    search: list[dict[str, str]] = []
    for page in flat:
        render(page)
        search += index_entries(page)
        chrome = {
            "tabs": tab_links(page, first_of_tab),
            "sidebar": sidebar(page, groups, first_of_tab),
            "toc": toc_html(page),
            "pager": pager(page, flat),
            "footer_columns": footer_columns(),
        }
        text = document(page, chrome)
        text = make_relative(text, page, slugs, broken)
        root = "../" * page.slug.count("/") or "./"
        text = text.replace('data-root="/"', f'data-root="{root}"', 1)
        target = OUT / page.url
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    (OUT / "search-index.js").write_text(
        "window.PASR_SEARCH="
        + json.dumps(search, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    not_found = pages["index"]
    shutil.copy(OUT / not_found.url, OUT / "404.html")
    four = (OUT / "404.html").read_text(encoding="utf-8")
    base = SITE["url"].rstrip("/") + "/"
    four = four.replace("<head>", f'<head>\n<base href="{base}">', 1)
    (OUT / "404.html").write_text(four, encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    urls = "".join(f"<url><loc>{base}{p.url}</loc></url>" for p in flat)
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n',
        encoding="utf-8",
    )

    print(f"built {len(flat)} pages → {OUT.relative_to(REPO)}")
    for link in broken:
        print(f"broken link: {link}")
    return 1 if strict and broken else 0


def serve(port: int) -> None:
    handler: Callable[..., SimpleHTTPRequestHandler] = partial(
        SimpleHTTPRequestHandler, directory=str(OUT)
    )
    print(f"serving {OUT.relative_to(REPO)} on http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--serve", action="store_true", help="serve the site after building it")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--strict", action="store_true", help="fail on a broken internal link")
    args = parser.parse_args()
    status = build(args.strict)
    if status:
        sys.exit(status)
    if args.serve:
        serve(args.port)


if __name__ == "__main__":
    main()
