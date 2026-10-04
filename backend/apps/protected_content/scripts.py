"""Produce protected standalone .js / .css files.

A browser must run JavaScript synchronously in load order and CSS has no runtime,
so these protected files cannot wait on the async Web Crypto API without breaking
pages that depend on them. They therefore use a synchronous, self-decrypting
wrapper (XOR with an embedded key, then base64). The key ships inside the file, so
this is OBFUSCATION — it deters casual copying and hides the source from View
Source, but a determined reader can recover it. That is the same class of
protection Protware's script/CSS encryption provides; use it with that in mind.

- A .js file stays a .js file and keeps working via <script src="...">.
- A .css file becomes a .js loader (CSS can't self-decrypt); reference it with
  <script src="style.css.js"></script> in place of the <link> tag.
"""
import base64
import os


def _wrap(payload: bytes, kind: str) -> str:
    key = os.urandom(32)
    enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(payload))
    k_b64 = base64.b64encode(key).decode()
    d_b64 = base64.b64encode(enc).decode()
    run = "(0,eval)(src);" if kind == "js" else (
        "var st=document.createElement('style');st.textContent=src;"
        "document.head.appendChild(st);"
    )
    return (
        "(function(){"
        f'var K="{k_b64}",D="{d_b64}";'
        "function b(s){return Uint8Array.from(atob(s),function(c){return c.charCodeAt(0);});}"
        "var key=b(K),data=b(D),out=new Uint8Array(data.length);"
        "for(var i=0;i<data.length;i++){out[i]=data[i]^key[i%key.length];}"
        "var src=new TextDecoder().decode(out);"
        f"{run}"
        "})();"
    )


def protect_script(source: bytes, filename: str) -> tuple[str, str]:
    """Return (protected_js_text, suggested_filename) for a .js or .css upload."""
    name = (filename or "").lower()
    if name.endswith(".css"):
        return _wrap(source, "css"), f"{filename}.js"
    # default: treat as JavaScript
    out_name = filename if name.endswith(".js") else f"{filename or 'script'}.js"
    return _wrap(source, "js"), out_name
