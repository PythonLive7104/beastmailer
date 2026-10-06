"""Build standalone, protected files the user can host or send anywhere.

This is the Protware deliverable done properly. The payload is encrypted with
AES-256-GCM; the key is derived from a passcode with PBKDF2-HMAC-SHA256. The
exported file embeds only the ciphertext, salt and IV — never the passcode or the
key — so without the passcode the content is genuinely encrypted at rest, not
merely obfuscated. It decrypts in the browser with the native Web Crypto API, so
the file is self-contained and needs no server and no libraries.

Two deliverables, one crypto core:

* **Pages** (`build_protected_html`) decrypt and render in place.
* **Files** (`build_protected_file_html`) decrypt to a Blob and hand the original
  file to the visitor. A PDF, docx or zip cannot decrypt itself, so the wrapper
  is an .html file — that is the only way to ship an encrypted document the
  recipient can open with nothing installed.

If no passcode is given we fall back to embedding the key in the file (keyless
mode): it opens with no prompt, but anyone can read the source — that is
obfuscation only, matching Protware's password-less pages. Prefer a passcode.

Usage restrictions (domain lock, offline-use blocking, frame breaking, expiry)
are enforced by the embedded script, so they are *licensing* controls rather than
cryptography: with a passcode the content stays unreadable regardless, but in
keyless mode a determined reader can lift the key and ignore them. The hosted
gate in gate.py is where these same rules are enforced for real, server-side.
"""
import base64
import gzip
import json
import mimetypes
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .htmlmin import minify_html

PBKDF2_ITERATIONS = 200_000


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _derive_key(passcode: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return kdf.derive(passcode.encode("utf-8"))


def deterrents_js(disable_right_click=False, disable_copy=False, disable_print=False,
                  block_shortcuts=False) -> str:
    bits = []
    if disable_right_click:
        bits.append("document.addEventListener('contextmenu',e=>e.preventDefault());")
    if disable_copy:
        bits.append("document.addEventListener('copy',e=>e.preventDefault());")
        bits.append("document.addEventListener('selectstart',e=>e.preventDefault());")
    if disable_print:
        bits.append("window.addEventListener('beforeprint',()=>{document.body.style.display='none';});")
        bits.append("window.addEventListener('afterprint',()=>{document.body.style.display='';});")
    if block_shortcuts:
        # F12, Ctrl+U (view source), Ctrl+S (save), Ctrl+Shift+I/J/C (devtools).
        bits.append(
            "document.addEventListener('keydown',e=>{var k=(e.key||'').toLowerCase();"
            "if(k==='f12'||(e.ctrlKey&&(k==='u'||k==='s'))||(e.ctrlKey&&e.shiftKey&&"
            "(k==='i'||k==='j'||k==='c'))){e.preventDefault();e.stopPropagation();}});"
        )
    return "".join(bits)


def _deterrent_js(doc) -> str:
    return deterrents_js(doc.disable_right_click, doc.disable_copy, doc.disable_print,
                         doc.block_shortcuts)


def parse_domains(raw: str) -> list[str]:
    """Normalise a comma-separated domain list for the domain lock.

    Strips scheme, port, path and a leading "www." so a user can paste either
    "example.com" or "https://www.example.com/page" and get the same lock.
    """
    out = []
    for part in (raw or "").split(","):
        d = part.strip().lower()
        if not d:
            continue
        d = d.split("//")[-1].split("/")[0].split(":")[0]
        if d.startswith("www."):
            d = d[4:]
        if d:
            out.append(d)
    return out


def _build_config(plaintext: bytes, title: str, passcode: str, expires_ms: int,
                  deterrents: str, compress: bool, kind: str,
                  domains: list[str] | None, block_offline: bool, break_frames: bool,
                  filename: str = "", mime: str = "") -> dict:
    """Encrypt `plaintext` and return the config dict the templates embed.

    Shared by both deliverables so the crypto, compression and guard settings can
    never drift apart between pages and files.
    """
    compressed = False
    if compress:
        gz = gzip.compress(plaintext, 9)
        if len(gz) < len(plaintext):
            plaintext = gz
            compressed = True

    salt = os.urandom(16)
    iv = os.urandom(12)

    if passcode:
        key = _derive_key(passcode, salt)
        keyless_key_b64 = ""
    else:
        # Keyless mode: random key embedded in the file (obfuscation only).
        key = AESGCM.generate_key(bit_length=256)
        keyless_key_b64 = _b64(key)

    ciphertext = AESGCM(key).encrypt(iv, plaintext, None)  # tag appended, Web-Crypto compatible

    return {
        "ct": _b64(ciphertext),
        "salt": _b64(salt),
        "iv": _b64(iv),
        "iter": PBKDF2_ITERATIONS,
        "keyless": keyless_key_b64,  # "" when a passcode is required
        "expires": int(expires_ms) if expires_ms else 0,  # client-side expiry (epoch ms)
        "gz": compressed,  # payload is gzip'd inside the ciphertext
        "deterrents": deterrents,
        "title": title,
        "kind": kind,  # "page" | "file"
        # Usage restrictions (see module docstring: licensing, not cryptography).
        "domains": domains or [],
        "offline": bool(block_offline),
        "frames": bool(break_frames),
        # File deliverable only.
        "fname": filename,
        "mime": mime,
    }


def encrypt_html_document(plaintext: bytes, title: str, passcode: str = "",
                          expires_ms: int = 0, deterrents: str = "", compress: bool = True,
                          domains: list[str] | None = None, block_offline: bool = False,
                          break_frames: bool = False) -> str:
    """Wrap raw HTML bytes into a standalone, encrypted, self-contained page.

    Independent of any model, so it serves both single-page export and whole-site
    zip processing. HTML compresses well, so by default the payload is gzip'd
    before encryption (the browser inflates it after decrypting) — this usually
    makes the generated file smaller than the original despite base64 overhead.
    Compression is skipped when it would not actually reduce the payload.
    """
    cfg = _build_config(
        plaintext, title, passcode, expires_ms, deterrents, compress, "page",
        domains, block_offline, break_frames,
    )
    return _render(_PAGE_BODY, cfg)


def encrypt_file_document(payload: bytes, title: str, filename: str, mime: str,
                          passcode: str = "", expires_ms: int = 0, deterrents: str = "",
                          compress: bool = True, domains: list[str] | None = None,
                          block_offline: bool = False, break_frames: bool = False) -> str:
    """Wrap arbitrary file bytes into a standalone, self-decrypting .html wrapper.

    The visitor opens the .html, enters the passcode, and the browser decrypts in
    memory and hands over the original file under its real name and media type.
    The plaintext file never exists on disk or on any server in between.

    Already-compressed formats (pdf, docx, zip, jpg, png…) need no special case:
    `_build_config` keeps gzip only when it actually shrinks the payload.
    """
    cfg = _build_config(
        payload, title, passcode, expires_ms, deterrents, compress, "file",
        domains, block_offline, break_frames, filename=filename, mime=mime,
    )
    return _render(_FILE_BODY, cfg)


def _inline_assets(doc, html: str) -> str:
    """Replace this page's gated asset URLs with embedded data: URIs.

    The exported file carries its images inside the ciphertext, so it needs no
    server for them and the images are encrypted alongside the page — cleaner and
    stronger than shipping separate protected image files.
    """
    for asset in doc.assets.all():
        gated = f"/g/{doc.slug}/asset/{asset.id}/"
        if gated in html:
            uri = f"data:{asset.content_type or 'application/octet-stream'};base64,{_b64(asset.get_payload())}"
            html = html.replace(gated, uri)
    return html


def _doc_restrictions(doc) -> dict:
    """The usage restrictions configured on a document, as kwargs for the builders."""
    return {
        "domains": parse_domains(getattr(doc, "allowed_domains", "")),
        "block_offline": getattr(doc, "block_offline", False),
        "break_frames": getattr(doc, "break_frames", False),
    }


def export_filename(doc) -> str:
    """The original filename to restore on the visitor's machine for a file doc."""
    name = os.path.basename(doc.original_filename or doc.name or "download").replace('"', "")
    if not os.path.splitext(name)[1]:
        ext = mimetypes.guess_extension((doc.content_type or "").split(";")[0].strip() or "")
        if ext:
            name += ext
    return name


def build_protected_html(doc, passcode: str = "", expires_ms: int = 0, inline_assets: bool = True) -> str:
    """Return a self-contained protected HTML document for `doc` (a page).

    expires_ms: optional client-side expiry (epoch milliseconds); 0 = none.
    inline_assets: embed the page's gated assets as data: URIs before encrypting.
    """
    html = doc.get_payload().decode("utf-8", errors="replace")
    if inline_assets:
        html = _inline_assets(doc, html)
    if doc.minify:
        html = minify_html(html)
    return encrypt_html_document(
        html.encode("utf-8"), doc.name, passcode=passcode,
        expires_ms=expires_ms, deterrents=_deterrent_js(doc),
        **_doc_restrictions(doc),
    )


def is_html_payload(content_type: str, filename: str) -> bool:
    """Whether an uploaded file is a web page rather than a document to save."""
    if "html" in (content_type or "").lower():
        return True
    return os.path.splitext((filename or "").lower())[1] in (".html", ".htm", ".xhtml")


def build_protected_file_html(doc, passcode: str = "", expires_ms: int = 0) -> str:
    """Return a self-decrypting .html wrapper around `doc`'s file payload.

    This closes the obvious hole: a file document used to be encrypted at rest but
    handed over in plaintext, and could not be exported at all. Now the portable
    deliverable is encrypted end to end exactly as a page is.

    An uploaded **HTML** file is rendered, not downloaded. Someone protecting their
    own site uploads .html files and expects the protected copy to behave like the
    original page; handing them a download instead was the wrong deliverable. The
    payload goes through the same renderer as an inline page, so its CSS, scripts,
    images and event handlers all work.
    """
    payload = doc.get_payload()
    filename = export_filename(doc)
    if is_html_payload(doc.content_type, filename):
        return encrypt_html_document(
            payload, doc.name, passcode=passcode, expires_ms=expires_ms,
            deterrents=_deterrent_js(doc), **_doc_restrictions(doc),
        )
    return encrypt_file_document(
        payload, doc.name, filename,
        (doc.content_type or "application/octet-stream"),
        passcode=passcode, expires_ms=expires_ms, deterrents=_deterrent_js(doc),
        **_doc_restrictions(doc),
    )


def build_protected_export(doc, passcode: str = "", expires_ms: int = 0) -> str:
    """Export `doc` whatever its kind — page or file."""
    from .models import ProtectedDocument

    if doc.kind == ProtectedDocument.KIND_FILE:
        return build_protected_file_html(doc, passcode=passcode, expires_ms=expires_ms)
    return build_protected_html(doc, passcode=passcode, expires_ms=expires_ms)


# --------------------------------------------------------------------------- #
# The exported file
# --------------------------------------------------------------------------- #
# All logic is inline; no external requests, so it works offline and on any
# static host. Web Crypto (crypto.subtle) is available in every current browser
# over http(s) and file://.

_SHELL = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Protected</title><style>
body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e8eb}
/* Hidden until something actually needs asking or reporting. A file with no
   passcode must go straight to its content, with no card flashing up first —
   so the gate is opt-in, not opt-out, and cannot paint before the script runs. */
#gate{display:none;min-height:100vh;align-items:center;justify-content:center}
.card{background:#171a21;border:1px solid #262b36;border-radius:12px;padding:32px;max-width:380px;width:90%}
h1{font-size:18px;margin:0 0 12px}p{color:#9aa4b2;margin:0 0 20px}
input{width:100%;box-sizing:border-box;padding:11px 12px;border-radius:8px;border:1px solid #30374a;background:#0f1115;color:#e6e8eb;font-size:15px}
button{margin-top:14px;width:100%;padding:11px;border:0;border-radius:8px;background:#4f7cff;color:#fff;font-size:15px;font-weight:600;cursor:pointer}
.err{color:#ff8080;margin:10px 0 0;font-size:13px;min-height:16px}
.meta{font-size:13px;color:#9aa4b2;word-break:break-all}
</style></head><body>
<div id="gate"><div class="card">
<h1 id="hd">Protected content</h1><p id="sub">Enter the passcode to continue.</p>
<form id="f"><input id="pc" type="password" autofocus autocomplete="off" placeholder="Passcode">
<div class="err" id="err"></div><button type="submit">Unlock</button></form>
</div></div>
<script>
const CFG = /*__CONFIG__*/;
const dec = (b64) => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
const $ = (id) => document.getElementById(id);
const clean = (s) => String(s || '').replace(/[<>&"]/g, '');
function human(n){
  const u = ['B','KB','MB','GB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(1) : n) + ' ' + u[i];
}
function showGate(){
  const g = $('gate');
  if (g) g.style.display = 'flex';
}
function fail(msg){
  showGate();
  // The card is gone once a page has been written in, so fall back to the body:
  // an error must always be visible, never swallowed into a blank screen.
  const html = '<h1>Unavailable</h1><p>' + clean(msg) + '</p>';
  const card = document.querySelector('.card');
  if (card) { card.innerHTML = html; return; }
  try {
    document.body.innerHTML =
      '<div id="gate" style="display:flex"><div class="card">' + html + '</div></div>';
  }
  catch (e) { /* nothing left to render into */ }
}
// Usage restrictions. See the module docstring: these are licensing controls,
// not the cryptography — a passcode is what keeps the payload unreadable.
function guard(){
  // Web Crypto only exists in a secure context: https, file:// or localhost. On a
  // plain http:// address crypto.subtle is undefined, decryption throws, and the
  // visitor used to be told "Incorrect passcode" for a passcode that was correct.
  if (!window.crypto || !crypto.subtle)
    return 'This page was opened over plain http://, so the browser blocked the ' +
           'decryption it needs. Open the file directly from disk, or serve it over ' +
           'https:// (http://localhost works too).';
  if (CFG.frames) {
    try {
      if (window.top !== window.self) { window.top.location = window.self.location; return null; }
    } catch (e) { return 'This content cannot be displayed inside a frame.'; }
  }
  if (CFG.offline && (location.protocol === 'file:' || !location.host))
    return 'This content must be opened from a web server, not from a local copy.';
  if (CFG.domains && CFG.domains.length) {
    const h = (location.hostname || '').toLowerCase().replace(/^www\./, '');
    const ok = CFG.domains.some((d) => h === d || h.endsWith('.' + d));
    if (!ok) return 'This content is not licensed to run on this domain.';
  }
  if (CFG.expires && Date.now() > CFG.expires)
    return 'This content has expired and can no longer be viewed.';
  return null;
}
async function gunzip(bytes){
  const ds = new DecompressionStream('gzip');
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
async function keyFromPasscode(pc){
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pc), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2', salt:dec(CFG.salt), iterations:CFG.iter, hash:'SHA-256'},
    base, {name:'AES-GCM', length:256}, false, ['decrypt']);
}
async function unlock(pc){
  const key = CFG.keyless
    ? await crypto.subtle.importKey('raw', dec(CFG.keyless), 'AES-GCM', false, ['decrypt'])
    : await keyFromPasscode(pc);
  const pt = await crypto.subtle.decrypt({name:'AES-GCM', iv:dec(CFG.iv)}, key, dec(CFG.ct));
  let bytes = new Uint8Array(pt);
  if (CFG.gz) bytes = await gunzip(bytes);
  return bytes;
}
function applyDeterrents(){
  if (!CFG.deterrents) return;
  const s = document.createElement('script');
  s.textContent = CFG.deterrents;
  document.body.appendChild(s);
}
/*__REVEAL__*/
(async () => {
  document.title = CFG.title || 'Protected';
  const blocked = guard();
  if (blocked) { fail(blocked); return; }
  if (CFG.keyless) {
    // No passcode was set, so never show a passcode box — not even for the
    // moment it takes to decrypt. The visitor should just see their content.
    // Nothing is rendered while this runs: the visitor sees their page appear,
    // not a loading card. The watchdog only ever fires if something is wrong —
    // an 8 MB file decrypts in under three seconds.
    const slow = setTimeout(() => {
      $('hd').textContent = 'Opening…';
      $('sub').textContent = 'Decrypting ' + human(CFG.ct.length * 0.75) + '…';
      $('f').style.display = 'none';
      showGate();
    }, 10000);
    try { await reveal(await unlock('')); }
    catch (e) { fail('Could not open this content. ' + (e && e.message ? e.message : e)); }
    finally { clearTimeout(slow); }
    return;
  }
  prime();
  showGate();
  $('f').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    $('err').textContent = '';
    try { await reveal(await unlock($('pc').value)); }
    catch (e) { $('err').textContent = 'Incorrect passcode.'; }
  });
})();
</script></body></html>"""

# Pages replace the whole document with the decrypted HTML.
_PAGE_BODY = r"""
function prime(){}
async function reveal(bytes){
  const html = new TextDecoder().decode(bytes);
  document.open(); document.write(html); document.close();
  applyDeterrents();
}
"""

# Files are shown where the browser can show them, and saved otherwise.
_FILE_BODY = r"""
function viewable(){
  const m = (CFG.mime || '').toLowerCase();
  if (m.startsWith('image/')) return 'image';
  if (m === 'application/pdf') return 'pdf';
  if (m.startsWith('text/') || m === 'application/json') return 'text';
  return '';
}
function prime(){
  $('hd').textContent = 'Protected file';
  const verb = viewable() ? 'view' : 'download';
  $('sub').innerHTML = 'Enter the passcode to ' + verb + ' <span class="meta">' +
    clean(CFG.fname) + '</span>.';
}
async function reveal(bytes){
  const blob = new Blob([bytes], {type: CFG.mime || 'application/octet-stream'});
  const url = URL.createObjectURL(blob);
  const save = () => {
    const a = document.createElement('a');
    a.href = url; a.download = CFG.fname || 'download';
    document.body.appendChild(a); a.click(); a.remove();
  };
  const kind = viewable();
  if (kind) {
    // Show it in the page rather than dropping it on the visitor's disk; the
    // Save button is there for when they do want to keep a copy.
    document.body.innerHTML =
      '<div style="padding:12px 16px;display:flex;gap:12px;align-items:center;' +
      'background:#171a21;border-bottom:1px solid #262b36">' +
      '<span class="meta" style="flex:1">' + clean(CFG.fname) + ' · ' + human(bytes.length) + '</span>' +
      '<button id="dl" style="margin:0;width:auto;padding:8px 14px">Save a copy</button></div>' +
      '<div id="view"></div>';
    const view = $('view');
    if (kind === 'image') {
      view.innerHTML = '<img style="max-width:100%;display:block;margin:0 auto">';
      view.firstChild.src = url;
    } else if (kind === 'pdf') {
      view.innerHTML = '<embed type="application/pdf" style="width:100%;height:calc(100vh - 53px)">';
      view.firstChild.src = url;
    } else {
      const pre = document.createElement('pre');
      pre.style.cssText = 'padding:16px;white-space:pre-wrap;word-break:break-word';
      pre.textContent = new TextDecoder().decode(bytes);
      view.appendChild(pre);
    }
    $('dl').addEventListener('click', save);
    applyDeterrents();
    return;
  }
  document.querySelector('.card').innerHTML =
    '<h1>Unlocked</h1><p><span class="meta">' + clean(CFG.fname) + '</span><br>' +
    human(bytes.length) + '</p><button id="dl">Download again</button>';
  $('dl').addEventListener('click', save);
  applyDeterrents();
  save();   // nothing to show it with, so hand the file over
}
"""


def _render(reveal_body: str, cfg: dict) -> str:
    return _SHELL.replace("/*__REVEAL__*/", reveal_body).replace("/*__CONFIG__*/", json.dumps(cfg))
