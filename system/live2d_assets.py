"""自定义 Live2D 模型资源管理。"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import quote
from uuid import uuid4

from .config import get_data_dir


class UploadedLive2DFile(Protocol):
    """FastAPI UploadFile 的最小协议，便于单元测试复用。"""

    filename: str | None

    async def read(self, size: int = -1) -> bytes:
        ...

    async def close(self) -> None:
        ...


CUSTOM_LIVE2D_DIR = get_data_dir() / "live2d" / "custom_models"
CUSTOM_LIVE2D_INDEX = CUSTOM_LIVE2D_DIR / "models.json"
MAX_LIVE2D_FILE_COUNT = 512
MAX_LIVE2D_TOTAL_BYTES = 300 * 1024 * 1024
_MODEL_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_ALLOWED_ASSET_SUFFIXES = {
    ".json",
    ".moc3",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".webm",
    ".txt",
    ".bytes",
    ".atlas",
}


def sanitize_live2d_model_name(name: str) -> str:
    """清理展示名称，保留中英文等可见字符。"""
    normalized = " ".join(str(name or "").strip().split())
    if not normalized:
        raise ValueError("模型名称不能为空")
    if len(normalized) > 80:
        raise ValueError("模型名称不能超过 80 个字符")
    return normalized


def normalize_live2d_upload_path(filename: str | None) -> PurePosixPath:
    """将上传文件名规范化为安全的 POSIX 相对路径。"""
    raw = str(filename or "").replace("\\", "/").strip()
    raw = raw.lstrip("/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute():
        raise ValueError("上传文件路径无效")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"上传文件路径不安全: {filename}")
    if len(path.parts) > 24:
        raise ValueError(f"上传文件路径过深: {filename}")
    return path


def is_allowed_live2d_asset_path(path: PurePosixPath) -> bool:
    """判断资源扩展名是否适合公开为 Live2D 静态资源。"""
    return Path(path.name).suffix.lower() in _ALLOWED_ASSET_SUFFIXES


def find_live2d_model_path(paths: list[PurePosixPath], requested_model_path: str | None = None) -> PurePosixPath:
    """从上传文件中定位 .model3.json 文件。"""
    if requested_model_path:
        requested = normalize_live2d_upload_path(requested_model_path)
        if requested not in paths:
            raise ValueError("指定的模型文件不在上传内容中")
        if not requested.name.lower().endswith(".model3.json"):
            raise ValueError("模型文件必须是 .model3.json")
        return requested

    model_paths = [path for path in paths if path.name.lower().endswith(".model3.json")]
    if not model_paths:
        raise ValueError("上传目录中没有找到 .model3.json 模型文件")
    if len(model_paths) > 1:
        raise ValueError("上传目录中包含多个 .model3.json，请选择具体模型文件")
    return model_paths[0]


def _ensure_storage() -> None:
    CUSTOM_LIVE2D_DIR.mkdir(parents=True, exist_ok=True)


def _read_index() -> dict[str, Any]:
    _ensure_storage()
    if not CUSTOM_LIVE2D_INDEX.exists():
        return {"version": 1, "models": []}
    try:
        data = json.loads(CUSTOM_LIVE2D_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "models": []}
    if not isinstance(data, dict):
        return {"version": 1, "models": []}
    models = data.get("models")
    if not isinstance(models, list):
        data["models"] = []
    data.setdefault("version", 1)
    return data


def _write_index(data: dict[str, Any]) -> None:
    _ensure_storage()
    fd, tmp_path = tempfile.mkstemp(dir=str(CUSTOM_LIVE2D_DIR), prefix=".models_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        Path(tmp_path).replace(CUSTOM_LIVE2D_INDEX)
    except BaseException:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        finally:
            raise


def _validate_model_id(model_id: str) -> str:
    normalized = str(model_id or "").strip()
    if not _MODEL_ID_RE.fullmatch(normalized):
        raise ValueError("模型 ID 无效")
    return normalized


def _public_model_payload(model: dict[str, Any], api_port: int) -> dict[str, Any]:
    model_id = str(model.get("id") or "")
    model_path = str(model.get("model_path") or "")
    encoded_model_path = quote(model_path, safe="/")
    return {
        **model,
        "source": f"http://localhost:{api_port}/custom-live2d/{quote(model_id, safe='')}/{encoded_model_path}",
    }


def list_custom_live2d_models(api_port: int) -> list[dict[str, Any]]:
    """列出可供前端使用的自定义 Live2D 模型。"""
    data = _read_index()
    models = [item for item in data.get("models", []) if isinstance(item, dict)]
    return [_public_model_payload(model, api_port) for model in models]


def get_custom_live2d_model(model_id: str, api_port: int) -> dict[str, Any] | None:
    """读取单个自定义 Live2D 模型。"""
    normalized_id = _validate_model_id(model_id)
    data = _read_index()
    for model in data.get("models", []):
        if isinstance(model, dict) and model.get("id") == normalized_id:
            return _public_model_payload(model, api_port)
    return None


async def create_custom_live2d_model(
    name: str,
    files: list[UploadedLive2DFile],
    requested_model_path: str | None,
    api_port: int,
) -> dict[str, Any]:
    """保存一组 Live2D 资源文件并返回模型元数据。"""
    display_name = sanitize_live2d_model_name(name)
    if not files:
        raise ValueError("请上传 Live2D 模型目录")
    if len(files) > MAX_LIVE2D_FILE_COUNT:
        raise ValueError(f"上传文件数量不能超过 {MAX_LIVE2D_FILE_COUNT}")

    _ensure_storage()
    model_id = uuid4().hex
    temp_dir = CUSTOM_LIVE2D_DIR / f".{model_id}.tmp"
    final_dir = CUSTOM_LIVE2D_DIR / model_id
    paths: list[PurePosixPath] = []
    seen_paths: set[str] = set()
    total_bytes = 0

    try:
        temp_dir.mkdir(parents=True, exist_ok=False)
        for upload in files:
            rel_path = normalize_live2d_upload_path(upload.filename)
            rel_key = rel_path.as_posix()
            if rel_key in seen_paths:
                raise ValueError(f"上传目录包含重复文件: {rel_key}")
            if not is_allowed_live2d_asset_path(rel_path):
                raise ValueError(f"不支持的 Live2D 资源类型: {rel_key}")

            seen_paths.add(rel_key)
            paths.append(rel_path)
            target_path = temp_dir / rel_key
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("wb") as handle:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_LIVE2D_TOTAL_BYTES:
                        raise ValueError("Live2D 模型资源总大小超过限制")
                    handle.write(chunk)
            await upload.close()

        model_path = find_live2d_model_path(paths, requested_model_path).as_posix()
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir.replace(final_dir)

        metadata = {
            "id": model_id,
            "name": display_name,
            "model_path": model_path,
            "file_count": len(paths),
            "total_bytes": total_bytes,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        index = _read_index()
        index["models"] = [
            item for item in index.get("models", [])
            if not isinstance(item, dict) or item.get("id") != model_id
        ]
        index["models"].append(metadata)
        _write_index(index)
        return _public_model_payload(metadata, api_port)
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(final_dir, ignore_errors=True)
        raise


def delete_custom_live2d_model(model_id: str) -> bool:
    """删除自定义 Live2D 模型。"""
    normalized_id = _validate_model_id(model_id)
    index = _read_index()
    before = len(index.get("models", []))
    index["models"] = [
        item for item in index.get("models", [])
        if not isinstance(item, dict) or item.get("id") != normalized_id
    ]
    deleted = len(index["models"]) != before
    shutil.rmtree(CUSTOM_LIVE2D_DIR / normalized_id, ignore_errors=True)
    if deleted:
        _write_index(index)
    return deleted
