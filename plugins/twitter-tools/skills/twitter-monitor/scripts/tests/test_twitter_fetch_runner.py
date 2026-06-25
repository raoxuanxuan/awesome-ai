import subprocess
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import twitter_fetch_runner  # noqa: E402


class TwitterFetchRunnerTests(unittest.TestCase):
    def test_run_twitter_fetch_raises_runtime_error_on_timeout(self):
        with mock.patch.object(
            twitter_fetch_runner,
            "resolve_twitter_fetch_bin",
            return_value=Path("/mock/twitter-fetch"),
        ):
            with mock.patch.dict(
                twitter_fetch_runner.os.environ,
                {"TWITTER_MONITOR_FETCH_TIMEOUT_SECONDS": "7"},
                clear=False,
            ):
                with mock.patch.object(
                    twitter_fetch_runner.subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(["/mock/twitter-fetch"], 7),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "twitter-fetch timed out after 7s: history --user tig88411109",
                    ):
                        twitter_fetch_runner.run_twitter_fetch(
                            ["history", "--user", "tig88411109"]
                        )


if __name__ == "__main__":
    unittest.main()
