# Documentation website

The source of <https://aroosa-batool.github.io/privacy-aware-social-robot/>. A small Python
script turns the Markdown pages into a static site; `.github/workflows/docs.yml` builds it and
publishes it to GitHub Pages on every push to `main` that touches `website/` or `docs/adr/`.

```bash
uv run website/build.py --serve      # build, then http://localhost:8000
uv run website/build.py --strict     # what CI runs: fails on a broken internal link
```

The script declares its own dependencies (Markdown, Pygments, PyYAML) inline, so `uv run` needs
nothing from the project environment.

## Layout

```
build.py            the generator (components and syntax are listed in its docstring)
template.html       the page: top bar, sidebar, content, "On this page", footer, search
nav.yml             tabs, sidebar groups and page order, footer links, site settings
icons.yml           inline SVG icons (Lucide) used by name
pages/              one Markdown file per page; the path is its URL
assets/             site.css, site.js, logo, and media/ (screen recordings and screenshots)
data/settings.json  every setting, rendered on reference/settings (regenerate, see below)
tools/              export_settings.py
_site/              the built site (git-ignored)
```

The decision records are not copied: the Decisions tab renders `docs/adr/*.md` directly.

## Write a page

```markdown
---
title: Page title
nav: Shorter sidebar title (optional)
description: One or two sentences, shown under the title and in search results.
---

Text, tables and code as usual. Links starting with / point at other pages: [Setup](/dashboard/setup).

:::tip Optional title
A callout: note, tip, info, warning, danger or privacy.
:::

::image src=/assets/media/home.webp alt="…" url=localhost:8501 caption="…"
```

Add the page to `nav.yml`. Steps, tabs, cards, videos and the pipeline diagram are described at
the top of `build.py`.

## Screen recordings

The clips in `assets/media/` were recorded from the dashboard at 1512×794 and converted to WebM
(VP9) with ffmpeg; stills are WebP. Keep each file under the 500 KB pre-commit limit, for example:

```bash
ffmpeg -i recording.gif -c:v libvpx-vp9 -crf 40 -b:v 0 -pix_fmt yuv420p -an assets/media/clip.webm
```

They show the dashboard only: no camera frames and no people. Keep it that way.

## After changing a setting

```bash
uv run python website/tools/export_settings.py     # rewrites data/settings.json
```
