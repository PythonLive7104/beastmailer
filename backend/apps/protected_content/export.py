"""Build a standalone, protected .html file the user can host anywhere.

This is the Protware deliverable done properly. The page's HTML is encrypted
with AES-256-GCM; the key is derived from a passcode with PBKDF2-HMAC-SHA256.
The exported file embeds only the ciphertext, salt and IV — never the passcode or
the key — so without the passcode the content is genuinely encrypted at rest, not
merely obfuscated. It decrypts in the browser with the native Web Crypto API, so
the file is self-contained and needs no server and no libraries.

If no passcode is given we fall back to embedding the key in the file (keyless
mode): the page opens with no prompt, but anyone can read the source — that is
obfuscation only, matching Protware's password-less pages. Prefer a passcode.
"""
import base64
import gzip
import json
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


def encrypt_html_document(plaintext: bytes, title: str, passcode: str = "",
                          expires_ms: int = 0, deterrents: str = "", compress: bool = True) -> str:
    """Core: wrap raw HTML bytes into a standalone, encrypted, self-contained file.

    Independent of any model, so it serves both single-page export and whole-site
    zip processing. HTML compresses well, so by default the payload is gzip'd
    before encryption (the browser inflates it after decrypting) — this usually
    makes the generated file smaller than the original despite base64 overhead.
    Compression is skipped when it would not actually reduce the payload.
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

    cfg = {
        "ct": _b64(ciphertext),
        "salt": _b64(salt),
        "iv": _b64(iv),
        "iter": PBKDF2_ITERATIONS,
        "keyless": keyless_key_b64,  # "" when a passcode is required
        "expires": int(expires_ms) if expires_ms else 0,  # client-side expiry (epoch ms)
        "gz": compressed,  # payload is gzip'd inside the ciphertext
        "deterrents": deterrents,
        "title": title,
    }
    return _TEMPLATE.replace("/*__CONFIG__*/", json.dumps(cfg))


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
    )


# The exported file. All logic is inline; no external requests, so it works
# offline and on any static host. Web Crypto (crypto.subtle) is available in
# every current browser over http(s) and file://.
_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Protected</title><style>
body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e8eb}
#gate{display:flex;min-height:100vh;align-items:center;justify-content:center}
.card{background:#171a21;border:1px solid #262b36;border-radius:12px;padding:32px;max-width:380px;width:90%}
h1{font-size:18px;margin:0 0 12px}p{color:#9aa4b2;margin:0 0 20px}
input{width:100%;box-sizing:border-box;padding:11px 12px;border-radius:8px;border:1px solid #30374a;background:#0f1115;color:#e6e8eb;font-size:15px}
button{margin-top:14px;width:100%;padding:11px;border:0;border-radius:8px;background:#4f7cff;color:#fff;font-size:15px;font-weight:600;cursor:pointer}
.err{color:#ff8080;margin:10px 0 0;font-size:13px;min-height:16px}
</style></head><body>
<div id="gate"><div class="card">
<h1>Protected content</h1><p>Enter the passcode to view this page.</p>
<form id="f"><input id="pc" type="password" autofocus autocomplete="off" placeholder="Passcode">
<div class="err" id="err"></div><button type="submit">Unlock</button></form>
</div></div>
<script>
const CFG = /*__CONFIG__*/;
const dec = (b64) => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
async function gunzip(bytes){
  const ds = new DecompressionStream('gzip');
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
async function reveal(bytes){
  if (CFG.gz) bytes = await gunzip(bytes);
  const html = new TextDecoder().decode(bytes);
  document.open(); document.write(html); document.close();
  if (CFG.deterrents) { const s=document.createElement('script'); s.textContent=CFG.deterrents; document.body.appendChild(s); }
}
async function keyFromPasscode(pc){
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pc), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2', salt:dec(CFG.salt), iterations:CFG.iter, hash:'SHA-256'},
    base, {name:'AES-GCM', length:256}, false, ['decrypt']);
}
async function tryDecrypt(key){
  const pt = await crypto.subtle.decrypt({name:'AES-GCM', iv:dec(CFG.iv)}, key, dec(CFG.ct));
  return new Uint8Array(pt);
}
async function unlock(pc){
  const key = CFG.keyless
    ? await crypto.subtle.importKey('raw', dec(CFG.keyless), 'AES-GCM', false, ['decrypt'])
    : await keyFromPasscode(pc);
  return tryDecrypt(key);
}
function expired(){
  document.querySelector('.card').innerHTML =
    '<h1>Expired</h1><p>This content has expired and can no longer be viewed.</p>';
}
(async () => {
  document.title = CFG.title || 'Protected';
  if (CFG.expires && Date.now() > CFG.expires) { expired(); return; }
  if (CFG.keyless) {            // no passcode required
    try { await reveal(await unlock('')); } catch(e){ document.getElementById('err').textContent='Could not load content.'; }
    return;
  }
  document.getElementById('f').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const err = document.getElementById('err'); err.textContent='';
    try { const d = await unlock(document.getElementById('pc').value); await reveal(d); }
    catch(e){ err.textContent='Incorrect passcode.'; }
  });
})();
</script></body></html>"""
