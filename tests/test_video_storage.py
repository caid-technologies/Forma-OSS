from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.video_storage import list_project_videos


class VideoStorageTests(unittest.TestCase):
    def test_list_project_videos_returns_empty_when_storage_is_missing(self) -> None:
        with patch.dict(os.environ, {"BLUEPRINT_DEV_MODE": "false"}, clear=True):
            self.assertEqual([], list_project_videos("project-123"))


if __name__ == "__main__":
    unittest.main()
