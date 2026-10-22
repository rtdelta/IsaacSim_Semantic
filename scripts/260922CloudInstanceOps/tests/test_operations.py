import hashlib
import contextlib
import io
import json
import socket
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from cloud_ops.audit import Audit, verify_file
from cloud_ops.download import download, validate_url
from cloud_ops.security import PolicyError, Redactor, load_policy
from cloud_ops.ssh import OutcomeUnknown, check_fingerprint, check_identity, collect, key_fingerprint


def public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class RedactionTests(unittest.TestCase):
    def test_known_secret_and_url_encoding_removed_before_log(self):
        from urllib.parse import quote
        secret = "TestOnly&demo)!42"
        r = Redactor([secret])
        for text in ("failure: " + secret, quote(secret, safe="")):
            self.assertNotIn(secret, r.text(text))
            self.assertNotIn(quote(secret, safe=""), r.text(text))

    def test_structured_raw_json_headers_keys_and_query(self):
        r = Redactor()
        values = [
            ('{"Authorization": "Basic abcdefghij"}', "abcdefghij"),
            ('password="not a real password"', "not a real password"),
            ("Cookie: session=privatevalue\n", "privatevalue"),
            ("https://user:pass@example.org/a?X-Amz-Signature=abc#private", "abc"),
            ("-----BEGIN OPENSSH PRIVATE KEY-----\nabcde\n-----END OPENSSH PRIVATE KEY-----", "abcde"),
            ("Bearer abcdef", "abcdef"),
        ]
        for raw, value in values:
            with self.subTest(raw=raw):
                self.assertNotIn(value, r.text(raw))
        self.assertEqual(r.clean({"client_secret": "hello"})["client_secret"], "[REDACTED]")

    def test_minimal_script_allowed_secret_script_rejected(self):
        r = Redactor()
        r.reject_sensitive_text("print('hello')\n", "script")
        with self.assertRaises(PolicyError):
            r.reject_sensitive_text("password='example-only'", "script")


class AuditTests(unittest.TestCase):
    def test_logs_and_artifacts_redacted_and_tamper_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = Audit(d, Redactor(["SyntheticSecret91"]), "test", "validation", "probe", "abc")
            a.event("output", stdout="SyntheticSecret91")
            artifact = a.snapshot("script", "password='synthetic-not-real'")
            a.finish("succeeded")
            self.assertEqual(verify_file(a.path)["integrity"], "valid")
            self.assertNotIn("SyntheticSecret91", a.path.read_text())
            self.assertNotIn("synthetic-not-real", artifact.read_text())
            artifact.write_text("changed")
            self.assertEqual(verify_file(a.path)["integrity"], "invalid")

    def test_missing_completion_is_unknown_and_line_edit_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            a = Audit(d, Redactor(), "test", "validation", "probe", "abc")
            a.file.close()
            self.assertEqual(verify_file(a.path)["completion"], "unknown")
            a.path.write_text(a.path.read_text().replace('"purpose": "validation"', '"purpose": "changed"'))
            self.assertEqual(verify_file(a.path)["integrity"], "invalid")

    def test_operation_files_do_not_collide(self):
        with tempfile.TemporaryDirectory() as d:
            a = Audit(d, Redactor(), "a", "validation", "probe", "abc")
            b = Audit(d, Redactor(), "b", "validation", "probe", "abc")
            a.finish("succeeded")
            b.finish("failed")
            self.assertNotEqual(a.path, b.path)
            self.assertEqual(verify_file(b.path)["integrity"], "valid")

    def test_audit_start_failure_prevents_network_operation(self):
        from cloud_ops.cli import main
        with tempfile.TemporaryDirectory() as d, patch("cloud_ops.cli.private_directory", return_value=Path(d)), \
                patch("cloud_ops.cli.Audit", side_effect=OSError("synthetic disk failure")), \
                patch("cloud_ops.cli.download") as transport, contextlib.redirect_stderr(io.StringIO()) as err:
            config = Path(d) / "config.json"
            config.write_text(json.dumps({"schema": 1, "targets": {}, "downloads": {}}), encoding="utf-8")
            code = main(["--config", str(config), "download", "--task", "test", "--purpose", "fail closed",
                         "--url", "https://example.org/a", "--filename", "a.txt", "--observe-hash"])
            self.assertEqual(code, 2)
            transport.assert_not_called()
            self.assertTrue(json.loads(err.getvalue())["audit_write_failed"])


class SSHTests(unittest.TestCase):
    def test_host_pin_and_instance_identity_must_match(self):
        class Key:
            def asbytes(self):
                return b"synthetic-key"
        key = Key()
        check_fingerprint(key, key_fingerprint(key))
        with self.assertRaises(PolicyError):
            check_fingerprint(key, "SHA256:wrong")
        expected = {"machine_id_sha256": "a" * 64, "hostname": "test"}
        check_identity(dict(expected), expected)
        with self.assertRaises(PolicyError):
            check_identity({"machine_id_sha256": "b" * 64, "hostname": "test"}, expected)

    def test_streams_drained_and_oversized_stream_fully_omitted(self):
        class Channel:
            stdout = [b"safe\npassword=", b"SyntheticSecret91"]
            stderr = [b"warning"]
            def recv_ready(self): return bool(self.stdout)
            def recv_stderr_ready(self): return bool(self.stderr)
            def recv(self, n): return self.stdout.pop(0)
            def recv_stderr(self, n): return self.stderr.pop(0)
            def exit_status_ready(self): return True
            def recv_exit_status(self): return 0
        result = collect(Channel(), timeout=1, max_output=16)
        self.assertEqual(result["stdout"], "[OUTPUT_OMITTED_SIZE_LIMIT]")
        self.assertEqual(result["stderr"], "warning")

    def test_timeout_does_not_report_success(self):
        class Channel:
            def recv_ready(self): return False
            def recv_stderr_ready(self): return False
            def recv(self, n): raise AssertionError("No output available")
            def recv_stderr(self, n): raise AssertionError("No output available")
            def exit_status_ready(self): return False
        with self.assertRaises(OutcomeUnknown):
            collect(Channel(), timeout=-1)

    def test_no_remote_command_when_host_key_rejected(self):
        from cloud_ops.ssh import run
        class Key:
            def asbytes(self): return b"wrong-server"
        class FakeClient:
            def set_missing_host_key_policy(self, policy): self.policy = policy
            def connect(self, **kwargs): self.policy.missing_host_key(self, "host", Key())
            def get_transport(self): raise AssertionError("Must not run commands after rejected key")
            def close(self): pass
        target = {"auth": "key", "identity_file": "unused", "host": "host", "port": 22,
                  "username": "user", "host_fingerprint": "SHA256:invalid"}
        with tempfile.TemporaryDirectory() as d, patch("paramiko.SSHClient", FakeClient):
            a = Audit(d, Redactor(), "test", "pin refusal", "probe", "abc")
            with self.assertRaises(PolicyError):
                run(target, "test", a, Redactor())
            a.finish("failed")


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.policy = {"allowed_hosts": ["example.org"], "max_bytes": 1024,
                       "max_seconds": 5, "max_redirects": 2}

    def test_source_validation_blocks_unknown_host_userinfo_and_local_address(self):
        for url in ("http://example.org/a", "https://evil.org/a", "https://user:pass@example.org/a",
                    "https://example.org/a?token=secret", "https://example.org:8443/a"):
            with self.subTest(url=url), self.assertRaises(PolicyError):
                validate_url(url, self.policy, public_dns)
        with self.assertRaises(PolicyError):
            validate_url("https://example.org/a", self.policy,
                         lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))])

    def factory(self, data, redirect=None):
        class Response(io.BytesIO):
            status = 200
            headers = {"Content-Type": "text/plain"}
            def geturl(self): return "https://example.org/a"
        def factory(*handlers):
            if redirect:
                handler = next(h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
                handler.redirect_request(urllib.request.Request("https://example.org/a"), None,
                                         302, "Found", {}, redirect)
            class Opener:
                def open(self, req, timeout): return Response(data)
            return Opener()
        return factory

    def test_valid_hash_download_never_executes_and_records_file(self):
        data = b"not an executable; synthetic fixture"
        with tempfile.TemporaryDirectory() as d:
            a = Audit(d, Redactor(), "test", "download test", "download", "abc")
            result = download("https://example.org/a", "fixture.txt", hashlib.sha256(data).hexdigest(),
                              False, d, self.policy, a, public_dns, self.factory(data))
            a.finish("succeeded")
            self.assertEqual(Path(result["file"]).read_bytes(), data)
            self.assertFalse(result["executed"])
            self.assertEqual(result["verification"], "matched_expected_hash")

    def test_hash_mismatch_removes_only_own_partial_and_produces_no_download(self):
        with tempfile.TemporaryDirectory() as d:
            a = Audit(d, Redactor(), "test", "mismatch test", "download", "abc")
            with self.assertRaises(PolicyError):
                download("https://example.org/a", "fixture.txt", "0" * 64, False,
                         d, self.policy, a, public_dns, self.factory(b"changed"))
            a.finish("failed")
            self.assertEqual(list((Path(d) / "downloads").iterdir()), [])
            self.assertEqual(list((Path(d) / "staging").iterdir()), [])

    def test_redirect_rejected_before_opening_destination(self):
        with tempfile.TemporaryDirectory() as d:
            a = Audit(d, Redactor(), "test", "redirect test", "download", "abc")
            with self.assertRaises(PolicyError):
                download("https://example.org/a", "fixture.txt", None, True,
                         d, self.policy, a, public_dns, self.factory(b"", "https://evil.org/payload"))
            a.finish("failed")

    def test_oversized_and_path_escape_downloads_are_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            a = Audit(d, Redactor(), "test", "limit test", "download", "abc")
            for filename, data in (("../escape.txt", b"a"), ("large.txt", b"x" * 2048), ("CON.txt", b"a")):
                with self.subTest(filename=filename), self.assertRaises(PolicyError):
                    download("https://example.org/a", filename, None, True,
                             d, self.policy, a, public_dns, self.factory(data))
            a.finish("failed")


if __name__ == "__main__":
    unittest.main()
