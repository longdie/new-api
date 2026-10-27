"""Offline regression checks using fake credentials only."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import stat
import tempfile
import unittest

from convert_codex_auth import convert_auth, main


class ConvertCodexAuthTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".local-tests"
        scratch.mkdir(exist_ok=True)
        directory = tempfile.TemporaryDirectory(prefix="auth-converter-", dir=scratch)
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.source = self.folder / "auth.json"
        self.target = self.folder / "new-api-credential.json"
        self.auth = {
            "tokens": {
                "access_token": "FAKE-ACCESS-DO-NOT-USE",
                "refresh_token": "FAKE-REFRESH-DO-NOT-USE",
                "account_id": "FAKE-ACCOUNT-DO-NOT-USE",
                "id_token": "FAKE-ID-DO-NOT-USE",
            },
            "last_refresh": "2026-10-27T00:00:00Z",
            "OPENAI_API_KEY": "FAKE-KEY-DO-NOT-USE",
        }
        self.source.write_text(json.dumps(self.auth), encoding="utf-8")

    def run_cli(self, *arguments):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main([str(self.source), *arguments])
        messages = stdout.getvalue() + stderr.getvalue()
        for value in [*self.auth["tokens"].values(), self.auth["OPENAI_API_KEY"]]:
            self.assertNotIn(value, messages)
        return result, messages

    def test_conversion_is_private_and_leaves_input_unchanged(self):
        before = self.source.read_bytes()
        result, _ = self.run_cli()
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(self.target.read_text()), {
            "type": "codex",
            "access_token": self.auth["tokens"]["access_token"],
            "refresh_token": self.auth["tokens"]["refresh_token"],
            "account_id": self.auth["tokens"]["account_id"],
            "last_refresh": self.auth["last_refresh"],
        })
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o600)
        self.assertEqual(self.source.read_bytes(), before)

    def test_explicit_output_and_utf8_bom(self):
        self.source.write_text(json.dumps(self.auth), encoding="utf-8-sig")
        destination = self.folder / "private" / "channel.json"
        result, _ = self.run_cli("-o", str(destination))
        self.assertEqual(result, 0)
        self.assertTrue(destination.is_file())
        self.assertFalse(self.target.exists())

    def test_rejects_missing_or_invalid_fields(self):
        for field in ("access_token", "refresh_token", "account_id"):
            for value in (None, "", "  ", 123, [], {}):
                with self.subTest(field=field, value=value):
                    auth = {"tokens": {**self.auth["tokens"], field: value}}
                    with self.assertRaises(ValueError):
                        convert_auth(auth)
        for auth in ([], None, {}, {"tokens": []}, {"OPENAI_API_KEY": "fake"}):
            with self.subTest(auth_type=type(auth).__name__):
                with self.assertRaises(ValueError):
                    convert_auth(auth)

    def test_optional_refresh_time_can_be_absent(self):
        converted = convert_auth({"tokens": self.auth["tokens"]})
        self.assertNotIn("last_refresh", converted)

    def test_invalid_input_is_not_printed_or_written(self):
        for document in (
            '{"tokens": "FAKE-ACCESS-DO-NOT-USE",',
            json.dumps({"tokens": {"access_token": "FAKE-ACCESS-DO-NOT-USE"}}),
        ):
            with self.subTest(malformed=document.endswith(",")):
                self.source.write_text(document)
                result, _ = self.run_cli()
                self.assertEqual(result, 1)
                self.assertFalse(self.target.exists())

    def test_existing_output_and_input_cannot_be_overwritten(self):
        self.target.write_text("keep existing output")
        result, _ = self.run_cli()
        self.assertEqual(result, 1)
        self.assertEqual(self.target.read_text(), "keep existing output")
        before = self.source.read_bytes()
        result, _ = self.run_cli("-o", str(self.source))
        self.assertEqual(result, 1)
        self.assertEqual(self.source.read_bytes(), before)

    def test_rejects_output_symlink(self):
        for destination in (self.source, self.folder / "absent.json"):
            with self.subTest(existing_destination=destination.exists()):
                self.target.symlink_to(destination)
                result, _ = self.run_cli()
                self.assertEqual(result, 1)
                self.assertTrue(self.target.is_symlink())
                self.target.unlink()
        self.assertFalse((self.folder / "absent.json").exists())


if __name__ == "__main__":
    unittest.main()
