from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from system.config import config


class GuideRequest(BaseModel):
    content: str = Field(default="", description="用户问题")
    game_id: str | None = Field(default=None, description="游戏ID（可选）")
    server_id: str | None = Field(default=None, description="服务器ID")
    images: list[str] = Field(default_factory=list, description="图片base64列表")
    auto_screenshot: bool = Field(default=False, description="是否自动截图")
    history: list[dict[str, Any]] = Field(default_factory=list, description="可选历史消息")
    force_query_mode: str | None = Field(default=None, description="强制查询模式，跳过路由")


class GuideReference(BaseModel):
    type: str = "document"
    title: str = ""
    source: str = ""
    score: float | None = None


class GuideResponse(BaseModel):
    content: str
    query_mode: str = "full"
    references: list[GuideReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class GuideEngineSettings:
    enabled: bool = True
    gamedata_dir: str = "./data"
    embedding_api_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_api_model: str | None = None
    game_guide_llm_api_base_url: str | None = None   # 攻略专用LLM API地址，需支持图片输入
    game_guide_llm_api_key: str | None = None        # 攻略专用LLM API密钥
    game_guide_llm_api_model: str | None = None      # 攻略专用LLM模型名，需支持图片输入
    game_guide_llm_api_type: str = "openai"          # 攻略专用LLM API类型（openai/gemini）
    neo4j_uri: str = "neo4j://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "your_password"
    prompt_dir: str = "guide_engine/game_prompts"
    screenshot_monitor_index: int = 1
    auto_screenshot_on_guide: bool = False

    @classmethod
    def from_runtime(cls) -> "GuideEngineSettings":
        root = config.system.base_dir
        ge = config.guide_engine

        prompt_dir = ge.prompt_dir
        gamedata_dir = ge.gamedata_dir

        if prompt_dir.startswith("./"):
            prompt_dir = str((root / prompt_dir[2:]).resolve())
        if gamedata_dir.startswith("./"):
            gamedata_dir = str((root / gamedata_dir[2:]).resolve())

        # NagaModel 网关优先：认证态走统一网关
        from apiserver import naga_auth
        if naga_auth.should_use_model_gateway():
            _emb_base = naga_auth.NAGA_MODEL_URL
            _emb_key = naga_auth.get_access_token()
            _emb_model = "default"
            _llm_base = naga_auth.NAGA_MODEL_URL
            _llm_key = naga_auth.get_access_token()
            _llm_model = "default"
        else:
            _emb_base = ge.embedding_api_base_url or config.api.base_url
            _emb_key = ge.embedding_api_key or config.api.api_key
            _emb_model = ge.embedding_api_model or "text-embedding-3-small"
            _llm_base = ge.game_guide_llm_api_base_url or config.api.base_url
            _llm_key = ge.game_guide_llm_api_key or config.api.api_key
            _llm_model = ge.game_guide_llm_api_model or config.api.model

        return cls(
            enabled=ge.enabled,
            gamedata_dir=gamedata_dir,
            embedding_api_base_url=_emb_base,
            embedding_api_key=_emb_key,
            embedding_api_model=_emb_model,
            game_guide_llm_api_base_url=_llm_base,
            game_guide_llm_api_key=_llm_key,
            game_guide_llm_api_model=_llm_model,
            game_guide_llm_api_type=ge.game_guide_llm_api_type,
            neo4j_uri=ge.neo4j_uri,
            neo4j_user=ge.neo4j_user,
            neo4j_password=ge.neo4j_password,
            prompt_dir=prompt_dir,
            screenshot_monitor_index=ge.screenshot_monitor_index,
            auto_screenshot_on_guide=ge.auto_screenshot_on_guide,
        )


_settings: GuideEngineSettings | None = None


def get_guide_engine_settings() -> GuideEngineSettings:
    global _settings
    if _settings is None:
        _settings = GuideEngineSettings.from_runtime()
    return _settings
