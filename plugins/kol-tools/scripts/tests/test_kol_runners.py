import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class KolRunnerTests(unittest.TestCase):
    def write_fake_bin(self, root: Path, name: str) -> Path:
        script = root / name
        script.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys

payload = {
    "argv": sys.argv[1:],
    "stdin": sys.stdin.read(),
    "cwd": os.getcwd(),
}
print(json.dumps(payload, ensure_ascii=False))
""",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def test_codex_runner_passes_stdin_to_codex_exec(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = self.write_fake_bin(root, "codex")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "kol_codex_runner.py"),
                    "--codex-bin",
                    str(fake),
                    "--cd",
                    str(root),
                    "--model",
                    "test-model",
                ],
                input="hello codex",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stdin"], "hello codex")
            self.assertEqual(Path(payload["cwd"]).resolve(), root.resolve())
            self.assertEqual(payload["argv"][0], "exec")
            self.assertIn("-", payload["argv"])
            self.assertIn("--ephemeral", payload["argv"])
            self.assertIn("--ask-for-approval", payload["argv"])
            self.assertIn("never", payload["argv"])
            self.assertIn("--model", payload["argv"])
            self.assertIn("test-model", payload["argv"])

    def test_claude_runner_passes_stdin_to_claude_print(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = self.write_fake_bin(root, "claude")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "kol_claude_runner.py"),
                    "--claude-bin",
                    str(fake),
                    "--cwd",
                    str(root),
                    "--model",
                    "test-claude",
                ],
                input="hello claude",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stdin"], "hello claude")
            self.assertEqual(Path(payload["cwd"]).resolve(), root.resolve())
            self.assertIn("--print", payload["argv"])
            self.assertIn("--input-format", payload["argv"])
            self.assertIn("text", payload["argv"])
            self.assertIn("--output-format", payload["argv"])
            self.assertIn("--model", payload["argv"])
            self.assertIn("test-claude", payload["argv"])
            self.assertIn("--tools", payload["argv"])


if __name__ == "__main__":
    unittest.main()
