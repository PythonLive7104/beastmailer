"""Tests for the protected-content gate and the encrypted export.

The export is the part worth pinning down: it is the only place where protected
content leaves this server as a file, so a regression there silently ships
plaintext. Each test that claims something is encrypted proves it by decrypting
the result the same way the browser does, and by asserting the plaintext canary
is absent from the delivered bytes.
"""
import base64
import gzip
import json
import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.test import TestCase
from django.utils import timezone

from apps.workspaces.models import Workspace

from .export import build_protected_export, is_html_payload, parse_domains
from .gate import check_access
from .models import ProtectedAccessLog, ProtectedDocument

CANARY = b"%PDF-1.4 TOP-SECRET-CANARY confidential contents " + bytes(range(256)) * 4


def extract_config(html: str) -> dict:
    """Pull the embedded CFG object out of an exported file."""
    return json.loads(re.search(r"const CFG = (\{.*\});", html).group(1))


def browser_decrypt(cfg: dict, passcode: str) -> bytes:
    """Do exactly what the exported file's inline script does."""
    salt = base64.b64decode(cfg["salt"])
    if cfg["keyless"]:
        key = base64.b64decode(cfg["keyless"])
    else:
        key = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=cfg["iter"]
        ).derive(passcode.encode())
    plain = AESGCM(key).decrypt(base64.b64decode(cfg["iv"]), base64.b64decode(cfg["ct"]), None)
    return gzip.decompress(plain) if cfg["gz"] else plain


class ExportEncryptionTests(TestCase):
    """A downloaded export must never contain the payload in the clear."""

    @classmethod
    def setUpTestData(cls):
        cls.ws = Workspace.objects.create(name="W")

    def _file_doc(self, **kw):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_FILE, name="Quarterly Report",
            slug=kw.pop("slug", "filedoc"), content_type="application/pdf",
            original_filename="q3-report.pdf", **kw,
        )
        doc.set_payload(CANARY)
        doc.save()
        return doc

    def test_file_export_is_encrypted_and_round_trips(self):
        html = build_protected_export(self._file_doc(), passcode="hunter2")

        # The regression this guards: the payload used to be handed over in the clear.
        self.assertNotIn(CANARY, html.encode("latin-1", "replace"))
        self.assertNotIn("hunter2", html)

        cfg = extract_config(html)
        self.assertEqual(cfg["kind"], "file")
        self.assertEqual(cfg["fname"], "q3-report.pdf")
        self.assertEqual(cfg["mime"], "application/pdf")
        self.assertEqual(cfg["keyless"], "")  # key is not in the file
        self.assertEqual(browser_decrypt(cfg, "hunter2"), CANARY)

    def test_wrong_passcode_cannot_decrypt(self):
        cfg = extract_config(build_protected_export(self._file_doc(), passcode="right"))
        with self.assertRaises(Exception):
            browser_decrypt(cfg, "wrong")

    def test_page_export_is_encrypted(self):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_PAGE, name="Page", slug="pagedoc",
        )
        doc.set_payload(b"<h1>Hi</h1><p>page-canary</p>")
        doc.save()

        html = build_protected_export(doc, passcode="pw")
        self.assertNotIn("page-canary", html)
        cfg = extract_config(html)
        self.assertEqual(cfg["kind"], "page")
        self.assertIn(b"page-canary", browser_decrypt(cfg, "pw"))

    def test_keyless_export_embeds_the_key(self):
        """No passcode is obfuscation only — assert that, so nobody mistakes it."""
        cfg = extract_config(build_protected_export(self._file_doc(), passcode=""))
        self.assertNotEqual(cfg["keyless"], "")
        self.assertEqual(browser_decrypt(cfg, ""), CANARY)

    def test_restrictions_are_embedded(self):
        doc = self._file_doc(
            allowed_domains="example.com, https://www.partner.net/x",
            block_offline=True, break_frames=True,
        )
        cfg = extract_config(build_protected_export(doc, passcode="pw"))
        self.assertEqual(cfg["domains"], ["example.com", "partner.net"])
        self.assertTrue(cfg["offline"])
        self.assertTrue(cfg["frames"])


class ParseDomainsTests(TestCase):
    def test_strips_scheme_port_path_and_www(self):
        self.assertEqual(
            parse_domains("https://www.Example.com:8443/a/b, partner.net , "),
            ["example.com", "partner.net"],
        )

    def test_blank_means_no_lock(self):
        self.assertEqual(parse_domains(""), [])
        self.assertEqual(parse_domains("  ,  "), [])


class GateTests(TestCase):
    """The server-side gate is the real enforcement; each rule gets a case."""

    @classmethod
    def setUpTestData(cls):
        cls.ws = Workspace.objects.create(name="W")

    def _doc(self, **kw):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_PAGE,
            name="D", slug=kw.pop("slug", "gatedoc"), **kw,
        )
        doc.set_payload(b"<p>x</p>")
        doc.save()
        return doc

    def _request(self, host="example.com", referer=""):
        from django.test import RequestFactory

        return RequestFactory().get("/g/gatedoc/", HTTP_HOST=host, HTTP_REFERER=referer)

    def test_domain_lock_allows_listed_host_and_subdomain(self):
        doc = self._doc(allowed_domains="example.com")
        for host in ("example.com", "www.example.com", "docs.example.com"):
            granted, outcome = check_access(doc, self._request(host=host))
            self.assertTrue(granted, f"{host} should pass")

    def test_domain_lock_blocks_other_hosts(self):
        doc = self._doc(allowed_domains="example.com")
        granted, outcome = check_access(doc, self._request(host="evil.test"))
        self.assertFalse(granted)
        self.assertEqual(outcome, ProtectedAccessLog.OUTCOME_DENIED_DOMAIN)

    def test_blank_domain_lock_allows_anything(self):
        doc = self._doc(allowed_domains="")
        granted, _ = check_access(doc, self._request(host="anywhere.test"))
        self.assertTrue(granted)

    def test_expired_document_is_refused(self):
        doc = self._doc(expires_at=timezone.now() - timezone.timedelta(minutes=1))
        granted, outcome = check_access(doc, self._request())
        self.assertFalse(granted)
        self.assertEqual(outcome, ProtectedAccessLog.OUTCOME_EXPIRED)

    def test_revoked_document_is_refused(self):
        granted, outcome = check_access(self._doc(is_active=False), self._request())
        self.assertFalse(granted)
        self.assertEqual(outcome, ProtectedAccessLog.OUTCOME_INACTIVE)

    def test_wrong_passcode_is_refused_and_logged(self):
        doc = self._doc()
        doc.set_passcode("open-sesame")
        doc.save()
        granted, outcome = check_access(doc, self._request(), passcode="nope")
        self.assertFalse(granted)
        self.assertEqual(outcome, ProtectedAccessLog.OUTCOME_DENIED_PASSCODE)
        self.assertTrue(doc.access_logs.filter(
            outcome=ProtectedAccessLog.OUTCOME_DENIED_PASSCODE).exists())
        self.assertTrue(check_access(doc, self._request(), passcode="open-sesame")[0])

    def test_first_view_does_not_log_a_denial(self):
        """Merely opening the page and seeing the prompt is not an attempt."""
        doc = self._doc()
        doc.set_passcode("pw")
        doc.save()
        check_access(doc, self._request(), passcode=None)
        self.assertFalse(doc.access_logs.filter(
            outcome=ProtectedAccessLog.OUTCOME_DENIED_PASSCODE).exists())


class ViewCapTests(TestCase):
    """max_views must not be exceedable by concurrent requests."""

    @classmethod
    def setUpTestData(cls):
        cls.ws = Workspace.objects.create(name="W")

    def _doc(self):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_PAGE, name="D",
            slug="capdoc", max_views=1,
        )
        doc.set_payload(b"<p>x</p>")
        doc.save()
        return doc

    def test_only_one_claim_succeeds_for_a_single_view(self):
        from .public_views import _claim_view

        doc = self._doc()
        # Two requests that both passed check_access (both read view_count == 0).
        self.assertTrue(_claim_view(doc))
        self.assertFalse(_claim_view(doc), "the cap was already taken")
        doc.refresh_from_db()
        self.assertEqual(doc.view_count, 1)

    def test_unlimited_document_always_claims(self):
        from .public_views import _claim_view

        doc = self._doc()
        doc.max_views = None
        doc.save()
        for _ in range(3):
            self.assertTrue(_claim_view(doc))
        doc.refresh_from_db()
        self.assertEqual(doc.view_count, 3)


class HostedDownloadTests(TestCase):
    """The hosted gate decrypts for the visitor; that is the documented trade-off."""

    @classmethod
    def setUpTestData(cls):
        cls.ws = Workspace.objects.create(name="W")

    def test_file_download_through_the_gate_keeps_its_filename(self):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_FILE, name="Report",
            slug="hosted", content_type="application/pdf", original_filename="q3 report.pdf",
        )
        doc.set_payload(CANARY)
        doc.save()

        resp = self.client.get("/g/hosted/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("q3 report.pdf", resp["Content-Disposition"])
        # The gate's job is to hand the real file to an authorised visitor, so this
        # body IS the plaintext. Use an export when the file itself must stay sealed.
        self.assertEqual(resp.content, CANARY)

    def test_break_frames_sets_headers(self):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_PAGE, name="P",
            slug="framed", break_frames=True,
        )
        doc.set_payload(b"<p>hi</p>")
        doc.save()

        resp = self.client.get("/g/framed/")
        self.assertEqual(resp["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", resp["Content-Security-Policy"])

    def test_domain_lock_is_enforced_on_the_hosted_link(self):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_PAGE, name="P",
            slug="locked", allowed_domains="allowed.test",
        )
        doc.set_payload(b"<p>secret-body</p>")
        doc.save()

        denied = self.client.get("/g/locked/", HTTP_HOST="other.test")
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn(b"secret-body", denied.content)

        ok = self.client.get("/g/locked/", HTTP_HOST="allowed.test")
        self.assertEqual(ok.status_code, 200)
        self.assertIn(b"secret-body", ok.content)


class ExportApiTests(TestCase):
    """The export endpoint used to reject file documents outright with a 400."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from rest_framework.authtoken.models import Token

        from apps.workspaces.services import ensure_personal_workspace

        user = get_user_model().objects.create_user(username="u", password="pw12345!x")
        cls.ws = ensure_personal_workspace(user)
        cls.token = Token.objects.create(user=user)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def _doc(self, kind, slug):
        doc = ProtectedDocument(
            workspace=self.ws, kind=kind, name="Doc", slug=slug,
            content_type="application/pdf", original_filename="doc.pdf",
        )
        doc.set_payload(CANARY)
        doc.save()
        return doc

    def test_export_of_a_file_returns_an_encrypted_wrapper(self):
        doc = self._doc(ProtectedDocument.KIND_FILE, "apifile")
        resp = self.client.post(
            f"/api/protected-content/{doc.id}/export/",
            {"passcode": "s3cret"}, content_type="application/json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(".html", resp["Content-Disposition"])

        body = resp.content.decode()
        self.assertNotIn(CANARY, resp.content)
        cfg = extract_config(body)
        self.assertEqual(cfg["kind"], "file")
        self.assertEqual(browser_decrypt(cfg, "s3cret"), CANARY)

    def test_batch_export_includes_files_and_pages(self):
        f = self._doc(ProtectedDocument.KIND_FILE, "batchfile")
        p = self._doc(ProtectedDocument.KIND_PAGE, "batchpage")
        resp = self.client.post(
            "/api/protected-content/export-batch/",
            {"ids": [f.id, p.id], "passcode": "pw"},
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)

        import io as _io
        import zipfile

        with zipfile.ZipFile(_io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 2, names)
            for name in names:
                self.assertNotIn(CANARY, zf.read(name))


class HtmlFileRendersTests(TestCase):
    """An uploaded .html file must render like the original page, not download.

    Someone protecting their own site uploads .html files and expects the
    protected copy to behave like the page it replaces. Handing them a download
    was the wrong deliverable and is the regression these tests pin down.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ws = Workspace.objects.create(name="W")

    PAGE = b"<!doctype html><h1>Heading</h1><script>var x=1;</script>"

    def _html_file(self, content_type, filename, slug):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_FILE, name="My Site",
            slug=slug, content_type=content_type, original_filename=filename,
        )
        doc.set_payload(self.PAGE)
        doc.save()
        return doc

    def test_detects_html_by_type_or_extension(self):
        self.assertTrue(is_html_payload("text/html", "x.bin"))
        self.assertTrue(is_html_payload("application/octet-stream", "index.html"))
        self.assertTrue(is_html_payload("", "page.HTM"))
        self.assertFalse(is_html_payload("application/pdf", "report.pdf"))
        self.assertFalse(is_html_payload("", "archive.zip"))

    def test_uploaded_html_exports_as_a_rendering_page(self):
        doc = self._html_file("text/html", "index.html", "htmlfile")
        cfg = extract_config(build_protected_export(doc, passcode="pw"))
        # "page" is what makes the wrapper render instead of save to disk.
        self.assertEqual(cfg["kind"], "page")
        self.assertEqual(browser_decrypt(cfg, "pw"), self.PAGE)

    def test_uploaded_html_without_a_content_type_still_renders(self):
        doc = self._html_file("application/octet-stream", "index.html", "htmlfile2")
        self.assertEqual(extract_config(build_protected_export(doc, passcode="pw"))["kind"], "page")

    def test_a_real_document_still_downloads(self):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_FILE, name="Report",
            slug="pdffile", content_type="application/pdf", original_filename="r.pdf",
        )
        doc.set_payload(CANARY)
        doc.save()
        cfg = extract_config(build_protected_export(doc, passcode="pw"))
        self.assertEqual(cfg["kind"], "file")
        self.assertEqual(cfg["fname"], "r.pdf")


class ExportedScriptTests(TestCase):
    """Guards inside the generated file that a browser test would otherwise own."""

    @classmethod
    def setUpTestData(cls):
        cls.ws = Workspace.objects.create(name="W")

    def _export(self, passcode):
        doc = ProtectedDocument(
            workspace=self.ws, kind=ProtectedDocument.KIND_PAGE, name="P", slug="scriptdoc",
        )
        doc.set_payload(b"<p>hi</p>")
        doc.save()
        return build_protected_export(doc, passcode=passcode)

    def test_insecure_context_is_reported_as_such_not_as_a_bad_passcode(self):
        """A plain http:// page used to say "Incorrect passcode" for a correct one."""
        html = self._export("pw")
        self.assertIn("!window.crypto || !crypto.subtle", html)
        self.assertIn("blocked the", html)

    def test_the_gate_is_hidden_until_something_needs_it(self):
        """A keyless file must go straight to its content - no card, no flash.

        The gate is hidden in CSS rather than hidden by script, so it cannot
        paint before the script runs. Only the passcode prompt and errors
        reveal it.
        """
        html = self._export("")
        self.assertIn("#gate{display:none", html)
        self.assertIn("function showGate()", html)

    def test_errors_are_shown_even_after_the_card_is_gone(self):
        html = self._export("")
        self.assertIn('<div id="gate" style="display:flex">', html)


class SiteZipAssetTests(TestCase):
    """Every local asset a page uses must end up inside the ciphertext.

    Anything left as a loose file is both unprotected and missing once only the
    protected HTML is shipped. CSS url() was the gap: background images and
    @font-face sources are referenced from stylesheet text, which the attribute
    pass never sees.
    """

    PNG = bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + b"fake-image-bytes" * 4

    def _zip(self, files):
        import io as _io
        import zipfile

        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
        return buf.getvalue()

    def _protect(self, files, **kw):
        import io as _io
        import zipfile

        from .site import process_site_zip

        out = process_site_zip(self._zip(files), passcode="pw", **kw)
        return zipfile.ZipFile(_io.BytesIO(out))

    def test_css_background_image_is_embedded(self):
        page = b"""<!doctype html><html><head><style>
            .hero{background-image:url('img/bg.png')}
            </style></head><body><p>hi</p></body></html>"""
        zf = self._protect({"index.html": page, "img/bg.png": self.PNG})
        html = zf.read("index.html").decode()
        cfg = extract_config(html)
        body = browser_decrypt(cfg, "pw").decode()
        self.assertIn("data:image/png;base64,", body)
        self.assertNotIn("img/bg.png", body)

    def test_url_in_a_linked_stylesheet_resolves_against_that_stylesheet(self):
        """css/site.css referencing ../img/bg.png must resolve from css/, not from /."""
        page = b'<!doctype html><html><head><link rel="stylesheet" href="css/site.css">'                b"</head><body><p>hi</p></body></html>"
        css = b".hero{background:url('../img/bg.png')}"
        zf = self._protect({"index.html": page, "css/site.css": css, "img/bg.png": self.PNG})
        body = browser_decrypt(extract_config(zf.read("index.html").decode()), "pw").decode()
        self.assertIn("data:image/png;base64,", body)
        self.assertNotIn("../img/bg.png", body)

    def test_img_tags_are_still_embedded(self):
        page = b'<!doctype html><html><body><img src="photo.png"></body></html>'
        zf = self._protect({"index.html": page, "photo.png": self.PNG})
        body = browser_decrypt(extract_config(zf.read("index.html").decode()), "pw").decode()
        self.assertIn("data:image/png;base64,", body)
        self.assertNotIn('src="photo.png"', body)

    def test_remote_and_data_urls_are_left_alone(self):
        page = b"""<!doctype html><html><head><style>
            .a{background:url('https://cdn.example.com/x.png')}
            .b{background:url('data:image/gif;base64,AAAA')}
            </style></head><body><p>hi</p></body></html>"""
        zf = self._protect({"index.html": page})
        body = browser_decrypt(extract_config(zf.read("index.html").decode()), "pw").decode()
        self.assertIn("https://cdn.example.com/x.png", body)
        self.assertIn("data:image/gif;base64,AAAA", body)

    def test_a_missing_asset_does_not_break_the_build(self):
        page = b"""<!doctype html><html><head><style>
            .a{background:url('nope.png')}</style></head><body><p>hi</p></body></html>"""
        zf = self._protect({"index.html": page})
        body = browser_decrypt(extract_config(zf.read("index.html").decode()), "pw").decode()
        self.assertIn("nope.png", body)   # left as-is rather than mangled

    def test_nothing_of_the_page_is_readable_in_the_protected_file(self):
        page = b'<!doctype html><html><body><h1>SECRET-HEADING</h1></body></html>'
        zf = self._protect({"index.html": page, "photo.png": self.PNG})
        html = zf.read("index.html").decode()
        self.assertNotIn("SECRET-HEADING", html)
