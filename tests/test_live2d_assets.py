from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from system import live2d_assets


class MemoryUpload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content
        self._offset = 0
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._content) - self._offset
        chunk = self._content[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    async def close(self) -> None:
        self.closed = True


class Live2DAssetsTest(unittest.TestCase):
    def test_normalize_live2d_upload_path_rejects_traversal(self) -> None:
        with self.assertRaises(ValueError):
            live2d_assets.normalize_live2d_upload_path("../evil.model3.json")

        with self.assertRaises(ValueError):
            live2d_assets.normalize_live2d_upload_path("model/../../evil.model3.json")

    def test_find_live2d_model_path_requires_single_model_file(self) -> None:
        paths = [
            live2d_assets.normalize_live2d_upload_path("avatar/avatar.model3.json"),
            live2d_assets.normalize_live2d_upload_path("avatar/texture_00.png"),
        ]

        self.assertEqual(
            live2d_assets.find_live2d_model_path(paths).as_posix(),
            "avatar/avatar.model3.json",
        )

        with self.assertRaises(ValueError):
            live2d_assets.find_live2d_model_path(paths, "avatar/texture_00.png")

    def test_create_and_delete_custom_live2d_model(self) -> None:
        with TemporaryDirectory() as tmp:
            storage_dir = Path(tmp) / "custom_models"
            with (
                patch.object(live2d_assets, "CUSTOM_LIVE2D_DIR", storage_dir),
                patch.object(live2d_assets, "CUSTOM_LIVE2D_INDEX", storage_dir / "models.json"),
            ):
                files = [
                    MemoryUpload("avatar/avatar.model3.json", b'{"Version":3}'),
                    MemoryUpload("avatar/avatar.moc3", b"moc"),
                    MemoryUpload("avatar/textures/texture_00.png", b"png"),
                ]

                model = asyncio.run(
                    live2d_assets.create_custom_live2d_model(
                        name=" 测试模型 ",
                        files=files,
                        requested_model_path=None,
                        api_port=8000,
                    )
                )

                self.assertEqual(model["name"], "测试模型")
                self.assertEqual(model["model_path"], "avatar/avatar.model3.json")
                self.assertEqual(model["file_count"], 3)
                self.assertTrue(model["source"].endswith(f"/custom-live2d/{model['id']}/avatar/avatar.model3.json"))
                self.assertTrue((storage_dir / model["id"] / "avatar" / "avatar.model3.json").exists())

                loaded = live2d_assets.get_custom_live2d_model(model["id"], 9000)
                self.assertIsNotNone(loaded)
                self.assertTrue(loaded["source"].startswith("http://localhost:9000/"))

                self.assertTrue(live2d_assets.delete_custom_live2d_model(model["id"]))
                self.assertFalse((storage_dir / model["id"]).exists())


if __name__ == "__main__":
    unittest.main()
