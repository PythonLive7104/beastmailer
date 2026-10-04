"""A small, conservative HTML minifier.

Strips HTML comments and collapses whitespace to make the page source harder to
read and a little smaller. It preserves the contents of <pre>, <textarea>,
<script> and <style> so layout and code inside them are not mangled. This is
cosmetic obfuscation, not security — the decrypted DOM is still readable.
"""
import re

# Keep the inner text of these tags exactly as written.
_PRESERVE = re.compile(r"(<(pre|textarea|script|style)\b[^>]*>.*?</\2>)", re.IGNORECASE | re.DOTALL)
# Drop comments, but leave IE conditional comments (<!--[if ...]>) intact.
_COMMENT = re.compile(r"<!--(?!\[if).*?-->", re.DOTALL)
_BETWEEN_TAGS = re.compile(r">\s+<")
_WHITESPACE = re.compile(r"[ \t\r\n]+")
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")


def minify_html(html: str) -> str:
    blocks = []

    def stash(m):
        blocks.append(m.group(1))
        return f"\x00{len(blocks) - 1}\x00"

    out = _PRESERVE.sub(stash, html)
    out = _COMMENT.sub("", out)
    out = _BETWEEN_TAGS.sub("><", out)
    out = _WHITESPACE.sub(" ", out).strip()
    out = _PLACEHOLDER.sub(lambda m: blocks[int(m.group(1))], out)
    return out
