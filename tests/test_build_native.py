import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from build_native import capture_runtime_notices


class NoticeCaptureTests(unittest.TestCase):
    def test_exact_notice_bytes_and_explicit_missing_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            licensed = root / "licensed"
            bare = root / "bare"
            licensed.mkdir()
            bare.mkdir()
            text = b"Actual upstream notice bytes\n"
            (licensed / "LICENSE-MIT").write_bytes(text)
            metadata = {"packages": [
                {"name": "licensed", "version": "1", "manifest_path": str(licensed / "Cargo.toml"),
                 "license": "MIT", "license_file": None},
                {"name": "bare", "version": "2", "manifest_path": str(bare / "Cargo.toml"),
                 "license": "BSD-2-Clause", "license_file": None},
            ]}
            destination = root / "output"
            destination.mkdir()
            capture_runtime_notices(metadata, destination)
            notices = destination / "runtime-licenses"
            self.assertEqual((notices / "licensed-1/LICENSE-MIT").read_bytes(), text)
            records = json.loads((notices / "manifest.json").read_text())["packages"]
            self.assertEqual(records[0]["files"], {"licensed-1/LICENSE-MIT": hashlib.sha256(text).hexdigest()})
            self.assertFalse(records[0]["missing_upstream_text"])
            self.assertTrue(records[1]["missing_upstream_text"])
            self.assertEqual(records[1]["files"], {})

    def test_missing_declared_notice_or_source_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = {"packages": [{"name": "broken", "version": "1",
                         "manifest_path": str(root / "Cargo.toml"),
                         "license_file": "MISSING"}]}
            with self.assertRaisesRegex(RuntimeError, "Missing declared license"):
                capture_runtime_notices(metadata, root)
            metadata["packages"][0]["manifest_path"] = str(root / "missing/Cargo.toml")
            with self.assertRaisesRegex(RuntimeError, "Missing resolved notice source"):
                capture_runtime_notices(metadata, root)
