import io
import unittest
from unittest.mock import patch
from urllib.error import URLError

from ggbh.updater import is_newer, latest_release, version_tuple


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class UpdaterTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertEqual(version_tuple("v1.2.10"), (1, 2, 10))
        self.assertTrue(is_newer("1.1.2", "1.1.1"))
        self.assertFalse(is_newer("v1.1.1", "1.1.1"))

    def test_latest_release_uses_github_api_data(self):
        def opener(request, timeout):
            self.assertIn("api.github.com/repos/example/project/releases/latest", request.full_url)
            self.assertEqual(timeout, 3)
            return _Response(b'{"tag_name":"v1.2.0","html_url":"https://github.com/example/project/releases/tag/v1.2.0"}')

        result = latest_release("example/project", timeout=3, opener=opener)
        self.assertEqual(result["version"], "1.2.0")

    def test_windows_fallback_uses_native_tls(self):
        native = {"tag_name": "v1.1.2", "html_url": "https://github.com/example/project/releases/tag/v1.1.2", "name": "修正版"}
        with patch("ggbh.updater.urlopen", side_effect=URLError("certificate verify failed")), \
             patch("ggbh.updater.powershell_latest_release", return_value=native) as fallback:
            result = latest_release("example/project", timeout=3)
        fallback.assert_called_once_with("example/project", 3)
        self.assertEqual(result["version"], "1.1.2")


if __name__ == "__main__":
    unittest.main()
