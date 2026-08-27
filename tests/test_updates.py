import io
import json
import unittest
from urllib.error import HTTPError

from jsonfold.updates import LATEST_RELEASE_URL, check_for_updates, version_key


class FakeResponse:
    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class UpdateTests(unittest.TestCase):
    def test_version_keys_support_v_prefix(self) -> None:
        self.assertGreater(version_key("v1.10.0"), version_key("1.9.9"))
        self.assertEqual(version_key("v0.2.0"), (0, 2, 0))

    def test_new_release_is_reported(self) -> None:
        def opener(request: object, timeout: int) -> FakeResponse:
            self.assertEqual(getattr(request, "full_url"), LATEST_RELEASE_URL)
            self.assertEqual(timeout, 8)
            return FakeResponse({"tag_name": "v0.3.0", "html_url": "https://github.com/Jaap79/JSON-Fold/releases/tag/v0.3.0"})

        result = check_for_updates("0.2.0", opener)
        self.assertEqual(result.status, "available")
        self.assertEqual(result.tag_name, "v0.3.0")

    def test_current_and_missing_release_are_handled(self) -> None:
        current = check_for_updates("0.2.0", lambda *_args, **_kwargs: FakeResponse({"tag_name": "v0.2.0", "html_url": "https://github.com/Jaap79/JSON-Fold/releases/tag/v0.2.0"}))
        self.assertEqual(current.status, "current")

        def missing(*_args: object, **_kwargs: object) -> FakeResponse:
            raise HTTPError(LATEST_RELEASE_URL, 404, "Not Found", {}, io.BytesIO())

        result = check_for_updates("0.2.0", missing)
        self.assertEqual(result.status, "no_release")


if __name__ == "__main__":
    unittest.main()
