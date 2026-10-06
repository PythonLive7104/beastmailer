"""Protect a whole static website supplied as a .zip.

For each HTML file in the zip, local assets referenced by a relative path
(images, CSS, JS that are present in the zip) are inlined — images as data:
URIs, stylesheets as <style>, scripts as inline <script> — so each page becomes
self-contained. The page is then AES-encrypted into a standalone file written at
the same relative path, so links between pages keep working. Only the protected
HTML files are returned; the referenced assets are embedded, not shipped loose.
"""
import base64
import io
import mimetypes
import posixpath
import re
import zipfile

from .export import deterrents_js, encrypt_html_document, parse_domains
from .htmlmin import minify_html

_HTML_EXT = (".html", ".htm")
# src="..." / href="..." capturing the quote and the value.
_ATTR = re.compile(r"""(src|href)\s*=\s*(["'])(.*?)\2""", re.IGNORECASE)
_LINK_CSS = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["']?stylesheet["']?[^>]*\bhref\s*=\s*(["'])(.*?)\1[^>]*>""",
    re.IGNORECASE,
)
_SCRIPT_SRC = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*(["'])(.*?)\1[^>]*>\s*</script>""",
    re.IGNORECASE,
)
# url(...) inside CSS — background images and @font-face files, which the
# attribute pass above never sees because they live in stylesheet text.
_CSS_URL = re.compile(r"""url\(\s*(['"]?)(?!['"]?(?:data:|https?:|//))(.*?)\1\s*\)""", re.IGNORECASE)
# Existing inline <style> blocks in the page itself.
_STYLE_BLOCK = re.compile(r"""(<style\b[^>]*>)(.*?)(</style>)""", re.IGNORECASE | re.DOTALL)


def _is_local(ref: str) -> bool:
    ref = (ref or "").strip()
    if not ref:
        return False
    low = ref.lower()
    return not (
        low.startswith(("http://", "https://", "//", "data:", "mailto:", "tel:", "#", "javascript:"))
    )


def _resolve(base_dir: str, ref: str) -> str:
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    return posixpath.normpath(posixpath.join(base_dir, ref)).lstrip("/")


def _data_uri(path: str, data: bytes) -> str:
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return f"data:{ctype};base64,{base64.b64encode(data).decode()}"


def _inline_css_urls(css: str, base_dir: str, files: dict) -> str:
    """Embed url(...) targets inside stylesheet text.

    Background images and @font-face sources are referenced from CSS, not from an
    attribute, so without this pass they stayed as loose files next to the
    protected page — unencrypted, and missing entirely once only the protected
    HTML is shipped. `base_dir` is the directory of the stylesheet the rules came
    from, since a url() resolves relative to its own file, not to the page.
    """
    def sub(m):
        quote, ref = m.group(1), m.group(2)
        if not _is_local(ref):
            return m.group(0)
        data = files.get(_resolve(base_dir, ref))
        if data is None:
            return m.group(0)
        return f"url({quote}{_data_uri(ref, data)}{quote})"

    return _CSS_URL.sub(sub, css)


def _inline_site_assets(html: str, base_dir: str, files: dict) -> str:
    """Inline CSS, JS and image references that exist in the zip."""
    # Stylesheets written directly in the page resolve against the page's folder.
    html = _STYLE_BLOCK.sub(
        lambda m: m.group(1) + _inline_css_urls(m.group(2), base_dir, files) + m.group(3), html
    )
    # Stylesheets -> <style>…</style>
    def css_sub(m):
        path = _resolve(base_dir, m.group(2))
        data = files.get(path)
        if data is None:
            return m.group(0)
        # A url() in here is relative to the stylesheet's own folder, not the page's.
        css = _inline_css_urls(data.decode("utf-8", "replace"), posixpath.dirname(path), files)
        return f"<style>{css}</style>"
    html = _LINK_CSS.sub(css_sub, html)

    # External scripts -> inline <script>
    def js_sub(m):
        path = _resolve(base_dir, m.group(2))
        data = files.get(path)
        if data is None:
            return m.group(0)
        return f"<script>{data.decode('utf-8', 'replace')}</script>"
    html = _SCRIPT_SRC.sub(js_sub, html)

    # Remaining src/href pointing at local, non-HTML files -> data: URIs
    def attr_sub(m):
        attr, quote, ref = m.group(1), m.group(2), m.group(3)
        if not _is_local(ref):
            return m.group(0)
        path = _resolve(base_dir, ref)
        if path.lower().endswith(_HTML_EXT):
            return m.group(0)  # keep links between pages intact
        data = files.get(path)
        if data is None:
            return m.group(0)
        return f'{attr}={quote}{_data_uri(path, data)}{quote}'
    return _ATTR.sub(attr_sub, html)


def process_site_zip(zip_bytes: bytes, passcode: str = "", expires_ms: int = 0,
                     minify: bool = False, disable_right_click: bool = False,
                     disable_copy: bool = False, disable_print: bool = False,
                     allowed_domains: str = "", block_offline: bool = False,
                     break_frames: bool = False) -> bytes:
    """Return a .zip of protected HTML files built from an uploaded site .zip."""
    try:
        zin = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise ValueError("The uploaded file is not a valid .zip archive.")

    files = {}
    for name in zin.namelist():
        if name.endswith("/"):
            continue
        files[name] = zin.read(name)

    html_paths = [p for p in files if p.lower().endswith(_HTML_EXT)]
    if not html_paths:
        raise ValueError("The archive contains no .html files to protect.")

    det = deterrents_js(disable_right_click, disable_copy, disable_print)
    domains = parse_domains(allowed_domains)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for path in html_paths:
            base_dir = posixpath.dirname(path)
            html = files[path].decode("utf-8", "replace")
            html = _inline_site_assets(html, base_dir, files)
            if minify:
                html = minify_html(html)
            title = posixpath.basename(path)
            protected = encrypt_html_document(
                html.encode("utf-8"), title, passcode=passcode,
                expires_ms=expires_ms, deterrents=det,
                domains=domains, block_offline=block_offline, break_frames=break_frames,
            )
            zout.writestr(path, protected)  # same relative path keeps inter-page links valid
    return out.getvalue()
