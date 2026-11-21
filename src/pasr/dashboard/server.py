"""The dashboard's web server, which ``pasr dashboard`` runs with ``streamlit run``: the pages
(``app.py``), and PASR's icon at ``/favicon.png``.

Streamlit's page names ``/favicon.png`` as its tab icon before the app has loaded, and only then
swaps in the app's; some browsers keep the first one (Safari always), so the address itself
gives PASR's icon instead of Streamlit's logo. So do the addresses browsers try on their own
(``/favicon.ico``, Safari's ``apple-touch-icon``), which would otherwise get Streamlit's page.
"""

from pathlib import Path

import streamlit as st
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route

from pasr.dashboard import ICON

ICON_PATHS = (
    "/favicon.png",
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
)


async def favicon(request: Request) -> FileResponse:
    return FileResponse(ICON, media_type="image/png", headers={"Cache-Control": "no-cache"})


app = st.App(Path(__file__).parent / "app.py", routes=[Route(path, favicon) for path in ICON_PATHS])
