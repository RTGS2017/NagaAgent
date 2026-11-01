#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NagaAgent独立服务 - 通过OpenClaw执行任务
提供意图识别和OpenClaw任务调度功能
"""

import asyncio
import logging
import httpx
import os
import sys
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from system.config import config, add_config_listener
from agentserver.telemetry_client import emit_local_telemetry
from agentserver.openclaw import get_openclaw_client, set_openclaw_config
from agentserver.openclaw.embedded_runtime import get_embedded_runtime, EmbeddedRuntime

# 配置日志
logger = logging.getLogger(__name__)


def _track_travel_task(session_id: str, task: asyncio.Task) -> None:
    Modules.travel_tasks[session_id] = task

    def _cleanup(done: asyncio.Task) -> None:
        Modules.travel_tasks.pop(session_id, None)
        try:
            done.result()
        except asyncio.CancelledError:
            logger.info(f"[旅行] 任务已取消: {session_id}")
        except Exception as exc:
            logger.error(f"[旅行] 任务退出异常 [{session_id}]: {exc}")

    task.add_done_callback(_cleanup)


def _spawn_travel_session(session_id: str, *, resumed: bool = False) -> bool:
    existing = Modules.travel_tasks.get(session_id)
    if existing and not existing.done():
        return False
    task = asyncio.create_task(_run_travel_session(session_id, resumed=resumed), name=f"travel:{session_id}")
    _track_travel_task(session_id, task)
    return True


async def _resume_open_travel_sessions() -> None:
    from apiserver.travel_service import list_open_sessions

    sessions = list_open_sessions()
    restored = 0
    for session in sessions:
        if _spawn_travel_session(session.session_id, resumed=True):
            restored += 1
    if restored:
        logger.info(f"[旅行] 已恢复 {restored} 个未完成探索")


def _mark_travel_sessions_interrupted(
    *,
    session_ids: Optional[list[str]] = None,
    reason: str = "interrupted",
) -> list[str]:
    from apiserver.travel_service import (
        get_session_or_none,
        interrupt_open_sessions,
        mark_session_interrupted,
    )

    interrupted_ids: list[str] = []
    if session_ids:
        for session_id in session_ids:
            session = get_session_or_none(session_id)
            if session is None:
                continue
            updated = mark_session_interrupted(session, reason=reason)
            if updated.session_id not in interrupted_ids:
                interrupted_ids.append(updated.session_id)
        return interrupted_ids

    for session in interrupt_open_sessions(reason=reason):
        interrupted_ids.append(session.session_id)
    return interrupted_ids


async def _interrupt_travel_sessions(
    *,
    session_ids: Optional[list[str]] = None,
    reason: str = "interrupted",
) -> list[str]:
    interrupted_ids = _mark_travel_sessions_interrupted(session_ids=session_ids, reason=reason)
    cancelled_tasks: list[asyncio.Task] = []
    for session_id in interrupted_ids:
        task = Modules.travel_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            cancelled_tasks.append(task)
    if cancelled_tasks:
        await asyncio.gather(*cancelled_tasks, return_exceptions=True)
    return interrupted_ids


async def _start_gateway_if_port_free(runtime: EmbeddedRuntime) -> bool:
    """主 Gateway 仅按主端口状态判定是否需要启动。"""
    if runtime.gateway_running:
        logger.info("当前进程中的 OpenClaw Gateway 已在运行，跳过启动")
        return False

    if runtime.is_gateway_port_in_use():
        logger.info(f"端口 {config.openclaw.gateway_port} 已被占用，跳过 Gateway 启动")
        return False

    if runtime.has_gateway_process():
        logger.info("检测到其他 OpenClaw Gateway 进程，但主端口空闲；继续尝试启动 20789 主 Gateway")

    gw_ok = await runtime.start_gateway()
    if gw_ok:
        logger.info("OpenClaw Gateway 启动成功")
    else:
        logger.warning("OpenClaw Gateway 启动失败")
    return gw_ok


def _on_config_changed() -> None:
    """配置变更监听器：自动更新 OpenClaw LLM 配置"""
    try:
        embedded_runtime = get_embedded_runtime()

        if embedded_runtime.is_vendor_ready:
            from agentserver.openclaw.llm_config_bridge import inject_naga_llm_config

            inject_naga_llm_config()
            logger.info("配置变更：已更新 OpenClaw LLM 配置")
    except Exception as e:
        logger.warning(f"配置变更时更新 OpenClaw 配置失败: {e}")


def _is_port_in_use(port: int) -> bool:
    """检测端口是否被占用"""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result == 0
    except Exception:
        return False


async def _delayed_health_check():
    """延迟健康检查（等待所有服务启动）"""
    await asyncio.sleep(6)  # 虚拟机/低性能环境下启动更慢，适当延长缓冲时间

    try:
        from system.health_check import perform_startup_health_check
        results, _summary = await perform_startup_health_check()

        # API 在慢机器上可能晚于首次检查就绪，做一次延迟复检避免启动早期误报
        api_result = results.get("api_server")
        api_unhealthy = (
            api_result is not None
            and getattr(getattr(api_result, "status", None), "value", "") == "unhealthy"
        )
        if api_unhealthy:
            logger.info("[HealthCheck] 检测到 API 尚未就绪，12 秒后执行一次复检")
            await asyncio.sleep(12)
            await perform_startup_health_check()
    except Exception as e:
        logger.error(f"启动时健康检查失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI应用生命周期"""
    # startup
    try:
        # 初始化 OpenClaw 客户端 - 三层回退策略
        try:
            from agentserver.openclaw import detect_openclaw, OpenClawConfig as ClientOpenClawConfig
            from agentserver.openclaw.llm_config_bridge import (
                ensure_openclaw_config,
                inject_naga_llm_config,
                ensure_hooks_allow_request_session_key,
                ensure_gateway_local_mode,
                ensure_hooks_path,
                ensure_gateway_port,
            )

            embedded_runtime = get_embedded_runtime()
            logger.info(f"OpenClaw 运行时模式: {embedded_runtime.runtime_mode}")
            logger.info(f"  vendor_root: {embedded_runtime.vendor_root}")
            logger.info(f"  node_path: {embedded_runtime.node_path}")
            logger.info(f"  is_vendor_ready: {embedded_runtime.is_vendor_ready}")

            # ── Step 1: 确保 vendor 就绪 + 配置 + onboard ──
            if not embedded_runtime.is_vendor_ready:
                await embedded_runtime.ensure_vendor_ready()

            if embedded_runtime.is_vendor_ready:
                ensure_openclaw_config()
                ensure_gateway_port(auto_create=False)
                ensure_gateway_local_mode(auto_create=False)
                ensure_hooks_path(auto_create=False)
                ensure_hooks_allow_request_session_key(auto_create=False)

                await embedded_runtime.ensure_onboarded()
                inject_naga_llm_config()

                # ── Step 1.5: 清理端口范围内的残留进程 ──
                try:
                    from agentserver.openclaw.instance_manager import cleanup_port_range
                    cleaned = cleanup_port_range()
                    if cleaned:
                        await asyncio.sleep(1)  # 等端口释放
                except Exception as e:
                    logger.warning(f"端口清理失败（可忽略）: {e}")

                # ── Step 2: 启动 Gateway ──
                await _start_gateway_if_port_free(embedded_runtime)

            # 检测最终状态并初始化客户端
            openclaw_status = detect_openclaw(check_connection=False)

            if openclaw_status.installed:
                openclaw_config = ClientOpenClawConfig(
                    gateway_url=openclaw_status.gateway_url or config.openclaw.gateway_url,
                    gateway_token=openclaw_status.gateway_token,
                    hooks_token=openclaw_status.hooks_token,
                    hooks_path=getattr(openclaw_status, "hooks_path", "/hooks"),
                    timeout=config.openclaw.timeout,
                )
                logger.info(f"OpenClaw 配置: {openclaw_config.gateway_url}")
                logger.info(
                    f"  - gateway_token: {'***' + openclaw_config.gateway_token[-8:] if openclaw_config.gateway_token else '未配置'}"
                )
                logger.info(
                    f"  - hooks_token: {'***' + openclaw_config.hooks_token[-8:] if openclaw_config.hooks_token else '未配置'}"
                )
            else:
                openclaw_config = ClientOpenClawConfig(
                    gateway_url=config.openclaw.gateway_url,
                    gateway_token=config.openclaw.token,
                    hooks_token=config.openclaw.token,
                    timeout=config.openclaw.timeout,
                )
                logger.info(f"OpenClaw 未检测到安装，使用配置文件: {openclaw_config.gateway_url}")

            Modules.openclaw_client = get_openclaw_client(openclaw_config)
            Modules.openclaw_client.restore_session()
            logger.info(f"OpenClaw客户端初始化完成: {openclaw_config.gateway_url}")
        except Exception as e:
            logger.warning(f"OpenClaw客户端初始化失败（可选功能）: {e}")
            Modules.openclaw_client = None

        # 初始化干员多实例管理器（通讯录模式：只恢复列表，不启动进程）
        try:
            from agentserver.openclaw.instance_manager import InstanceManager
            embedded_runtime = get_embedded_runtime()
            Modules.instance_manager = InstanceManager(embedded_runtime, primary_client=Modules.openclaw_client)
            logger.info("干员多实例管理器已初始化")
            # 从 manifest 恢复通讯录（不启动进程）
            try:
                agents = Modules.instance_manager.restore_from_manifest()
                logger.info(f"通讯录恢复完成，共 {len(agents)} 个干员")
            except Exception as e:
                logger.warning(f"恢复通讯录失败（可忽略）: {e}")
            try:
                await _resume_open_travel_sessions()
            except Exception as e:
                logger.warning(f"恢复探索任务失败（可忽略）: {e}")
        except Exception as e:
            logger.warning(f"干员多实例管理器初始化失败（可选功能）: {e}")
            Modules.instance_manager = None

        # 注册配置变更监听器
        add_config_listener(_on_config_changed)
        logger.debug("已注册 OpenClaw 配置变更监听器")

        # 初始化军牌系统（统一后台任务调度）
        try:
            from agentserver.dogtag import (
                create_dogtag_scheduler,
                get_dogtag_registry,
                load_heartbeat_config,
                create_heartbeat_executor,
                load_proactive_config,
                create_proactive_analyzer,
                create_proactive_trigger,
            )
            from agentserver.dogtag.duties.heartbeat_duty import create_heartbeat_duty
            from agentserver.dogtag.duties.screen_vision_duty import create_screen_vision_duty

            # 1. 初始化子组件
            pv_config = load_proactive_config()
            create_proactive_trigger()
            create_proactive_analyzer(pv_config)

            hb_config = load_heartbeat_config()
            create_heartbeat_executor(hb_config)

            # 2. 创建军牌调度器
            Modules.dogtag_scheduler = create_dogtag_scheduler()
            registry = get_dogtag_registry()

            # 3. 注册职责
            hb_tag, hb_exec = create_heartbeat_duty(hb_config)
            registry.register(hb_tag, hb_exec)

            sv_tag, sv_exec = create_screen_vision_duty(pv_config)
            registry.register(sv_tag, sv_exec)

            # 4. 启动调度器
            await Modules.dogtag_scheduler.start()
            logger.info("[DogTag] 军牌系统已启动")
        except Exception as e:
            logger.warning(f"[DogTag] 军牌系统初始化失败（可选功能）: {e}")
            Modules.dogtag_scheduler = None

        logger.info("NagaAgent服务初始化完成")

        # 执行启动时健康检查（延迟2秒等待所有服务就绪）
        asyncio.create_task(_delayed_health_check())

    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        raise

    # 运行期
    yield

    # shutdown
    try:
        # 停止军牌系统
        if Modules.dogtag_scheduler:
            await Modules.dogtag_scheduler.stop()
            logger.info("[DogTag] 军牌系统已停止")

        # 关闭心跳执行器的 HTTP 客户端
        from agentserver.dogtag import get_heartbeat_executor
        hb_executor = get_heartbeat_executor()
        if hb_executor:
            await hb_executor.close()

        # 停止所有干员子实例（主 Gateway 由下方 stop_gateway 处理）
        interrupted_ids = await _interrupt_travel_sessions(reason="shutdown")
        if interrupted_ids:
            logger.info(f"[旅行] 服务关闭前已中断 {len(interrupted_ids)} 个探索任务")

        if Modules.instance_manager:
            await Modules.instance_manager.destroy_all()
            logger.info("干员多实例已全部停止")

        # 停止 Gateway 进程（内嵌模式）
        embedded_runtime = get_embedded_runtime()
        if embedded_runtime.gateway_running:
            await embedded_runtime.stop_gateway()

        logger.info("NagaAgent服务已关闭")
    except Exception as e:
        logger.error(f"服务关闭失败: {e}")


app = FastAPI(title="NagaAgent Server", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Modules:
    """全局模块管理器"""

    openclaw_client = None
    dogtag_scheduler = None  # 军牌系统统一调度器
    instance_manager = None  # 干员多实例管理器
    travel_tasks: Dict[str, asyncio.Task] = {}


def _now_iso() -> str:
    """获取当前时间ISO格式"""
    return datetime.now().isoformat()


async def _process_openclaw_task(instruction: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """通过 OpenClaw 执行任务"""
    try:
        if not Modules.openclaw_client:
            return {
                "success": False,
                "error": "OpenClaw 客户端未初始化",
                "task_type": "openclaw",
                "instruction": instruction,
            }

        logger.info(f"开始通过 OpenClaw 执行任务: {instruction}")

        task = await Modules.openclaw_client.send_message(
            message=instruction,
            session_key=session_id,
            name="NagaAgent",
        )

        logger.info(f"OpenClaw 任务完成: {instruction}, 状态: {task.status.value}")
        return {
            "success": task.status.value == "completed",
            "result": task.to_dict(),
            "task_type": "openclaw",
            "instruction": instruction,
        }

    except Exception as e:
        logger.error(f"OpenClaw 任务失败: {e}")
        return {"success": False, "error": str(e), "task_type": "openclaw", "instruction": instruction}


# ============ API端点 ============


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": _now_iso(),
        "modules": {
            "openclaw": Modules.openclaw_client is not None,
            "dogtag": Modules.dogtag_scheduler is not None,
        },
    }


@app.get("/health/full")
async def full_health_check():
    """完整健康检查（包括所有服务）"""
    from system.health_check import get_health_checker

    checker = get_health_checker()
    results = await checker.check_all()
    summary = checker.get_summary(results)

    # 转换为可序列化格式
    results_dict = {}
    for service_name, result in results.items():
        results_dict[service_name] = {
            "status": result.status.value,
            "message": result.message,
            "checks": result.checks,
            "details": result.details,
            "latency_ms": result.latency_ms,
        }

    return {
        "summary": summary,
        "services": results_dict,
        "timestamp": _now_iso(),
    }


# ============ OpenClaw 集成 API ============


@app.get("/openclaw/health")
async def openclaw_health_check():
    """检查 OpenClaw Gateway 健康状态"""
    if not Modules.openclaw_client:
        return {"success": False, "status": "not_configured", "message": "OpenClaw 客户端未配置"}

    try:
        health = await Modules.openclaw_client.health_check()
        return {"success": True, "health": health}
    except Exception as e:
        logger.error(f"OpenClaw 健康检查失败: {e}")
        return {"success": False, "status": "error", "error": str(e)}


@app.post("/openclaw/config")
async def configure_openclaw(payload: Dict[str, Any]):
    """配置 OpenClaw 连接

    请求体:
    - gateway_url: Gateway 地址 (默认从 config.openclaw.gateway_url 读取)
    - token: 认证 token
    - timeout: 超时时间
    - default_model: 默认模型
    - default_channel: 默认通道
    """
    try:
        from agentserver.openclaw import OpenClawConfig as ClientOpenClawConfig

        openclaw_config = ClientOpenClawConfig(
            gateway_url=payload.get("gateway_url", config.openclaw.gateway_url),
            token=payload.get("token"),
            hooks_path=payload.get("hooks_path", "/hooks"),
            timeout=payload.get("timeout", config.openclaw.timeout),
            default_model=payload.get("default_model"),
            default_channel=payload.get("default_channel", "last"),
        )
        set_openclaw_config(openclaw_config)
        Modules.openclaw_client = get_openclaw_client()

        logger.info(f"OpenClaw 配置更新: {openclaw_config.gateway_url}")

        return {"success": True, "message": "OpenClaw 配置已更新", "gateway_url": openclaw_config.gateway_url}
    except Exception as e:
        logger.error(f"OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"配置失败: {e}")


@app.post("/openclaw/send")
async def openclaw_send_message(payload: Dict[str, Any]):
    """
    发送消息给 OpenClaw Agent

    使用 POST /hooks/agent 端点
    文档: https://docs.openclaw.ai/automation/webhook

    请求体:
    - message: 消息内容 (必需)
    - task_id: 外部任务ID（可选；用于与调度器task_id对齐）
    - session_key: 会话标识 (可选)
    - name: hook 名称 (可选)
    - channel: 消息通道 (可选)
    - to: 接收者 (可选)
    - model: 模型名称 (可选)
    - wake_mode: 唤醒模式 now/next-heartbeat (可选)
    - deliver: 是否投递 (可选)
    - timeout_seconds: 等待结果超时时间，默认120秒 (可选)
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    message = payload.get("message")
    if not message:
        raise HTTPException(400, "message 不能为空")

    # 如果提供了 task_id 但未提供 session_key，则默认使用 task_id 派生稳定会话键，便于按任务查看中间过程
    task_id = payload.get("task_id")
    session_key = payload.get("session_key")
    if task_id and not session_key:
        session_key = f"naga:task:{task_id}"

    try:
        task = await Modules.openclaw_client.send_message(
            message=message,
            session_key=session_key,
            name=payload.get("name"),
            channel=payload.get("channel"),
            to=payload.get("to"),
            model=payload.get("model"),
            wake_mode=payload.get("wake_mode", "now"),
            deliver=payload.get("deliver", False),
            timeout_seconds=payload.get("timeout_seconds", 120),
            task_id=task_id,
        )

        return {
            "success": task.status.value != "failed",
            "task": task.to_dict(),
            "reply": task.result.get("reply") if task.result else None,
            "replies": task.result.get("replies") if task.result else None,
            "error": task.error,
        }
    except Exception as e:
        logger.error(f"OpenClaw 发送消息失败: {e}")
        raise HTTPException(500, f"发送失败: {e}")


@app.post("/openclaw/wake")
async def openclaw_wake(payload: Dict[str, Any]):
    """
    触发 OpenClaw 系统事件

    使用 POST /hooks/wake 端点
    文档: https://docs.openclaw.ai/automation/webhook

    请求体:
    - text: 事件描述 (必需)
    - mode: 触发模式 now/next-heartbeat (可选)
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    text = payload.get("text")
    if not text:
        raise HTTPException(400, "text 不能为空")

    try:
        result = await Modules.openclaw_client.wake(text=text, mode=payload.get("mode", "now"))
        return result
    except Exception as e:
        logger.error(f"OpenClaw 触发事件失败: {e}")
        raise HTTPException(500, f"触发失败: {e}")


# ============ 干员实例管理 ============


@app.get("/openclaw/instances")
async def list_instances():
    """列出所有干员（通讯录），不管进程是否在跑"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")
    return {"instances": Modules.instance_manager.list_agents()}


# ── 新通讯录 API ──

@app.get("/openclaw/agents")
async def list_agents():
    """列出通讯录中所有干员（不管进程是否在跑）"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")
    return {"agents": Modules.instance_manager.list_agents()}


@app.post("/openclaw/agents")
async def create_agent(payload: Dict[str, Any]):
    """新建干员（写 manifest + 创建目录，不启动进程）"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    name = payload.get("name")
    character_template = (payload.get("character_template") or payload.get("characterTemplate") or "").strip() or None
    engine = (payload.get("engine") or "openclaw").strip() or "openclaw"
    telemetry_props = {
        "engine": engine,
        "name_length": len(str(name or "")),
        "has_character_template": bool(character_template),
    }
    try:
        inst = Modules.instance_manager.create_agent(
            name,
            character_template=character_template,
            engine=engine,
        )
        await emit_local_telemetry(
            "agent_create",
            {
                **telemetry_props,
                "created_agent_id": inst.id,
            },
            agent_id=inst.id,
        )
        return {
            "id": inst.id,
            "name": inst.name,
            "running": inst.running,
            "character_template": inst.character_template,
            "engine": inst.engine,
        }
    except Exception as e:
        await emit_local_telemetry(
            "agent_create_fail",
            {
                **telemetry_props,
                "error": e,
            },
        )
        logger.error(f"创建干员失败: {e}")
        raise HTTPException(500, f"创建失败: {e}")


@app.get("/openclaw/agents/{agent_id}/settings")
async def get_agent_settings(agent_id: str):
    """读取干员设置（名字 / 引擎 / 人设 / SOUL.md）。"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    settings = Modules.instance_manager.get_agent_settings(agent_id)
    if settings is None:
        raise HTTPException(404, "干员不存在")
    return settings


@app.put("/openclaw/agents/{agent_id}/settings")
async def update_agent_settings(agent_id: str, payload: Dict[str, Any]):
    """更新干员设置（名字 / 引擎 / 人设 / SOUL.md）。"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    name = payload.get("name")
    if name is not None:
        name = str(name).strip()
        if not name:
            raise HTTPException(400, "name 不能为空")

    engine = payload.get("engine")
    if engine is not None:
        engine = str(engine).strip()

    update_character_template = "character_template" in payload or "characterTemplate" in payload
    character_template = payload.get("character_template")
    if character_template is None and "characterTemplate" in payload:
        character_template = payload.get("characterTemplate")
    if character_template is not None:
        character_template = str(character_template).strip() or None

    update_soul_content = "soul_content" in payload or "soulContent" in payload
    soul_content = payload.get("soul_content")
    if soul_content is None and "soulContent" in payload:
        soul_content = payload.get("soulContent")
    if soul_content is not None:
        soul_content = str(soul_content)

    telemetry_props = {
        "changed_fields": sorted(
            field
            for field, changed in (
                ("name", name is not None),
                ("engine", engine is not None),
                ("character_template", update_character_template),
                ("soul_content", update_soul_content),
            )
            if changed
        ),
        "name_length": len(name or "") if name is not None else None,
        "engine": engine,
        "has_character_template": bool(character_template) if update_character_template else None,
        "soul_content_chars": len(soul_content or "") if update_soul_content else None,
    }

    try:
        settings = await Modules.instance_manager.update_agent_settings(
            agent_id,
            name=name,
            character_template=character_template,
            update_character_template=update_character_template,
            engine=engine,
            soul_content=soul_content,
            update_soul_content=update_soul_content,
        )
    except ValueError as exc:
        await emit_local_telemetry(
            "agent_settings_update_fail",
            {
                **telemetry_props,
                "error": str(exc),
                "status_code": 400,
            },
            agent_id=agent_id,
        )
        raise HTTPException(400, str(exc))
    except Exception as exc:
        await emit_local_telemetry(
            "agent_settings_update_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=agent_id,
        )
        logger.error(f"更新干员设置失败: {exc}")
        raise HTTPException(500, f"更新失败: {exc}")

    if settings is None:
        await emit_local_telemetry(
            "agent_settings_update_fail",
            {
                **telemetry_props,
                "status_code": 404,
                "error": "干员不存在",
            },
            agent_id=agent_id,
        )
        raise HTTPException(404, "干员不存在")
    await emit_local_telemetry("agent_settings_update", telemetry_props, agent_id=agent_id)
    return settings


@app.delete("/openclaw/agents/{agent_id}")
async def delete_agent(agent_id: str, delete_data: bool = True):
    """从通讯录删除干员 + 停止进程 + 可选删数据"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    try:
        await Modules.instance_manager.destroy_agent_async(agent_id, delete_data=delete_data)
        await emit_local_telemetry(
            "agent_delete",
            {
                "delete_data": bool(delete_data),
            },
            agent_id=agent_id,
        )
        return {"success": True}
    except Exception as e:
        await emit_local_telemetry(
            "agent_delete_fail",
            {
                "delete_data": bool(delete_data),
                "error": e,
            },
            agent_id=agent_id,
        )
        logger.error(f"删除干员失败: {e}")
        raise HTTPException(500, f"删除失败: {e}")


@app.put("/openclaw/agents/{agent_id}/name")
async def rename_agent(agent_id: str, payload: Dict[str, Any]):
    """重命名干员（通讯录 + 目录）"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")
    new_name = (payload.get("name") or "").strip()
    if not new_name:
        await emit_local_telemetry(
            "agent_rename_fail",
            {
                "name_length": 0,
                "status_code": 400,
                "error": "name 不能为空",
            },
            agent_id=agent_id,
        )
        raise HTTPException(400, "name 不能为空")
    ok = Modules.instance_manager.rename_agent(agent_id, new_name)
    if not ok:
        await emit_local_telemetry(
            "agent_rename_fail",
            {
                "name_length": len(new_name),
                "status_code": 404,
                "error": "干员不存在",
            },
            agent_id=agent_id,
        )
        raise HTTPException(404, "干员不存在")
    await emit_local_telemetry(
        "agent_rename",
        {
            "name_length": len(new_name),
        },
        agent_id=agent_id,
    )
    return {"success": True, "name": new_name}


@app.get("/openclaw/agents/{agent_id}/history")
async def get_agent_history(agent_id: str, limit: int = 50):
    """获取干员对话历史（自动 ensure_running 启动进程）"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")
    inst = Modules.instance_manager.get_instance(agent_id)
    if inst is None:
        raise HTTPException(404, "干员不存在")
    if inst.engine != "openclaw":
        return {"messages": []}

    # 按需启动进程（需要 Gateway 运行才能查询 session 历史）
    if not inst.running or not inst.client:
        try:
            inst = await Modules.instance_manager.ensure_running(agent_id)
        except Exception as e:
            logger.warning(f"启动干员 [{agent_id}] 以获取历史失败: {e}")
            return {"messages": []}

    session_key = inst.client._default_session_key
    if not session_key:
        logger.warning(f"干员 [{inst.name}] session_key 为空，无法获取历史")
        return {"messages": []}

    try:
        logger.info(f"获取干员 [{inst.name}] 历史: session_key={session_key}, limit={limit}")
        history = await inst.client.get_local_session_history(
            session_key=session_key,
            limit=limit,
        )
        if history.get("success"):
            messages = [
                msg for msg in history.get("messages", [])
                if isinstance(msg, dict) and msg.get("role") in ("user", "assistant")
            ]
            logger.info(f"解析后有效消息: {len(messages)} 条")
            return {"messages": messages}
        logger.warning(f"获取干员 [{inst.name}] 历史失败: {history.get('error', 'unknown')}")
        return {"messages": []}
    except Exception as e:
        logger.warning(f"获取干员 [{inst.name}] 历史失败: {e}", exc_info=True)
        return {"messages": []}


@app.get("/openclaw/agents/{agent_id}/runtime")
async def get_agent_runtime(agent_id: str, wake: bool = False):
    """解析指定干员当前运行时；wake=true 时若未启动则按需唤醒。"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    try:
        runtime = await Modules.instance_manager.resolve_runtime(agent_id, wake=wake)
        return {"success": True, "runtime": runtime}
    except RuntimeError as exc:
        detail = str(exc)
        status = 404 if "不存在" in detail else 409
        raise HTTPException(status, detail)
    except Exception as exc:
        logger.error(f"解析干员运行时失败 [{agent_id}]: {exc}")
        raise HTTPException(500, f"解析运行时失败: {exc}")


@app.post("/openclaw/agents/{agent_id}/send")
async def send_to_agent(agent_id: str, payload: Dict[str, Any]):
    """向指定干员发送消息（同步等待结果），内部自动 ensure_running。"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    message = payload.get("message", "")
    if not message:
        raise HTTPException(400, "message 不能为空")

    timeout = int(payload.get("timeout_seconds", 120) or 120)
    session_key = payload.get("session_key")
    name = payload.get("name")

    result = await Modules.instance_manager.send_message(
        agent_id,
        message,
        timeout=timeout,
        session_key=session_key,
        name=name,
    )
    if not result.get("success", False) and "error" in result:
        logger.warning(f"发送消息到干员 [{agent_id}] 失败: {result.get('error')}")
    return result


@app.post("/openclaw/agents/{agent_id}/stream")
async def stream_to_agent(agent_id: str, payload: Dict[str, Any]):
    """向干员发送消息（SSE 流式输出），内部自动 ensure_running"""
    from fastapi.responses import StreamingResponse
    import json as _json

    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    message = payload.get("message", "")
    if not message:
        raise HTTPException(400, "message 不能为空")

    timeout = payload.get("timeout_seconds", 120)

    async def event_stream():
        async for chunk in Modules.instance_manager.send_message_stream(agent_id, message, timeout):
            yield f"data: {_json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ============ 本地搜索代理（拦截 OpenClaw web_search） ============

_search_http_client: Optional[httpx.AsyncClient] = None


def _get_search_client() -> httpx.AsyncClient:
    """搜索代理共享 httpx 客户端"""

    global _search_http_client
    if _search_http_client is None or _search_http_client.is_closed:
        _search_http_client = httpx.AsyncClient(timeout=30.0, proxy=None)
    return _search_http_client


async def _local_search_proxy(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    本地搜索代理：拦截 web_search 请求，走 Naga 或 Brave，不转发给 OpenClaw。
    返回 MCP 工具结果格式 { success, result: { content: [...] } }
    """
    query = args.get("query", "") or args.get("q", "")
    count = args.get("count", 10) or args.get("limit", 10)
    freshness = args.get("freshness")

    if not query:
        return {"success": False, "error": "缺少搜索关键词 (query)"}

    try:
        # 优先级1: 已登录 Naga → NagaBusiness 搜索代理
        from apiserver import naga_auth

        if naga_auth.is_authenticated():
            token = naga_auth.get_access_token()
            params: Dict[str, Any] = {"q": query, "count": count}
            if freshness:
                params["freshness"] = freshness
            client = _get_search_client()
            resp = await client.post(
                naga_auth.NAGA_MODEL_URL + "/tools/search",
                json=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            source = "naga"
        else:
            # 优先级2: 配置了 search_api_key → 直接调 Brave
            api_key = config.online_search.search_api_key
            if not api_key:
                return {"success": False, "error": "未登录且未配置 search_api_key，无法搜索"}
            api_base = config.online_search.search_api_base
            params = {"q": query, "count": count}
            if freshness:
                params["freshness"] = freshness
            client = _get_search_client()
            resp = await client.get(
                api_base,
                params=params,
                headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            )
            source = "brave"

        if resp.status_code != 200:
            try:
                err = resp.json()
                msg = err.get("error", {}).get("message", "") if isinstance(err.get("error"), dict) else str(err)
            except Exception:
                msg = f"HTTP {resp.status_code}"
            logger.warning(f"[搜索代理] {source} 搜索失败: {msg}")
            return {"success": False, "error": f"搜索失败: {msg}"}

        data = resp.json()
        results = data.get("web", {}).get("results", [])

        # 格式化为可读文本
        if not results:
            text = "未找到相关搜索结果。"
        else:
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.get('title', '')}")
                lines.append(f"   URL: {r.get('url', '')}")
                if r.get("description"):
                    lines.append(f"   摘要: {r['description']}")
                if r.get("age"):
                    lines.append(f"   时间: {r['age']}")
                lines.append("")
            text = "\n".join(lines)

        logger.info(f"[搜索代理] {source} 搜索完成: query=\"{query}\", 结果数={len(results)}")

        # 返回 MCP 工具结果格式
        return {
            "success": True,
            "result": {"content": [{"type": "text", "text": text}]},
        }

    except Exception as e:
        logger.error(f"[搜索代理] 搜索异常: {e}")
        return {"success": False, "error": f"搜索异常: {e}"}


@app.post("/openclaw/tools/invoke")
async def openclaw_invoke_tool(payload: Dict[str, Any]):
    """
    直接调用 OpenClaw 工具

    使用 POST /tools/invoke 端点
    文档: https://docs.openclaw.ai/gateway/tools-invoke-http-api

    请求体:
    - tool: 工具名称 (必需)
    - args: 工具参数 (可选)
    - action: 动作 (可选)
    - session_key: 会话标识 (可选)
    """
    tool = payload.get("tool")
    if not tool:
        raise HTTPException(400, "tool 不能为空")

    # web_search 拦截：走本地搜索代理，不转发给 OpenClaw
    if tool == "web_search":
        return await _local_search_proxy(payload.get("args") or {})

    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        result = await Modules.openclaw_client.invoke_tool(
            tool=tool, args=payload.get("args"), action=payload.get("action"), session_key=payload.get("session_key")
        )
        return result
    except Exception as e:
        logger.error(f"OpenClaw 工具调用失败: {e}")
        raise HTTPException(500, f"调用失败: {e}")


# ============ OpenClaw 本地任务查询 API ============


@app.get("/openclaw/tasks")
async def openclaw_get_local_tasks():
    """获取本地缓存的所有 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        tasks = Modules.openclaw_client.get_all_tasks()
        return {"success": True, "tasks": [task.to_dict() for task in tasks], "count": len(tasks)}
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/tasks/{task_id}")
async def openclaw_get_task(task_id: str):
    """获取单个 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        task = Modules.openclaw_client.get_task(task_id)
        if task:
            return {"success": True, "task": task.to_dict()}
        else:
            raise HTTPException(404, f"任务不存在: {task_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/tasks/{task_id}/detail")
async def openclaw_get_task_detail(
    task_id: str,
    include_history: bool = True,
    history_limit: int = 50,
    include_tools: bool = False,
):
    """获取单个 OpenClaw 任务详情（包含本地 events 与可选 sessions_history）"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        task = Modules.openclaw_client.get_task(task_id)
        if not task:
            raise HTTPException(404, f"任务不存在: {task_id}")

        resp: Dict[str, Any] = {
            "success": True,
            "task": task.to_dict(),
        }

        if include_history:
            if task.session_key:
                history = await Modules.openclaw_client.get_sessions_history(
                    session_key=task.session_key,
                    limit=history_limit,
                    include_tools=include_tools,
                )
                resp["history"] = history
            else:
                resp["history"] = {"success": True, "messages": [], "note": "task_has_no_session_key"}

        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务详情失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/history")
async def openclaw_get_history(
    session_key: Optional[str] = None,
    limit: int = 120,
    include_tools: bool = True,
):
    """
    获取 OpenClaw 历史。

    - session_key 为空：读取当前默认会话的 Gateway sessions_history。
    - session_key 非空：读取对应本地 transcript，供 travel 看板/对话界面查看原始记录。
    """
    normalized_key = str(session_key or "").strip()
    if not normalized_key:
        if not Modules.openclaw_client:
            raise HTTPException(503, "OpenClaw 客户端未就绪")

        try:
            return await Modules.openclaw_client.get_sessions_history(
                session_key=None,
                limit=limit,
                include_tools=include_tools,
            )
        except Exception as e:
            logger.error(f"获取 OpenClaw 默认会话历史失败: {e}")
            raise HTTPException(500, f"获取失败: {e}")

    try:
        if normalized_key.startswith("travel:"):
            parts = normalized_key.split(":")
            agent_id = parts[1] if len(parts) >= 3 and parts[1] != "main" else None
            if agent_id:
                if not Modules.instance_manager:
                    raise HTTPException(503, "实例管理器未就绪")
                inst = await Modules.instance_manager.ensure_running(agent_id)
                if not inst.client:
                    raise HTTPException(503, "干员客户端未就绪")
                history = await inst.client.get_local_session_transcript(
                    session_key=normalized_key,
                    limit=limit,
                )
            else:
                if not Modules.openclaw_client:
                    raise HTTPException(503, "OpenClaw 客户端未就绪")
                history = await Modules.openclaw_client.get_local_session_transcript(
                    session_key=normalized_key,
                    limit=limit,
                )
        else:
            if not Modules.openclaw_client:
                raise HTTPException(503, "OpenClaw 客户端未就绪")
            history = await Modules.openclaw_client.get_local_session_transcript(
                session_key=normalized_key,
                limit=limit,
            )
        return {"success": True, "history": history}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"按 session_key 获取 OpenClaw 历史失败 [{normalized_key}]: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.delete("/openclaw/tasks/completed")
async def openclaw_clear_completed_tasks():
    """清理已完成的 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        Modules.openclaw_client.clear_completed_tasks()
        return {"success": True, "message": "已清理完成的任务"}
    except Exception as e:
        logger.error(f"清理 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"清理失败: {e}")


@app.get("/openclaw/session")
async def openclaw_get_session():
    """
    获取当前 OpenClaw 调度终端会话信息

    用于在设置界面显示 Naga 调度 OpenClaw 的终端连接状态

    返回:
    - 有活跃会话: session_key, created_at, last_activity, message_count, last_run_id, status
    - 无会话: has_session=False, message="请和 OpenClaw 交互以显示交互终端"
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        session_info = Modules.openclaw_client.get_session_info()

        if session_info is None:
            return {"has_session": False, "message": "请和 OpenClaw 交互以显示交互终端"}

        return {"has_session": True, "session": session_info}
    except Exception as e:
        logger.error(f"获取 OpenClaw 会话信息失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/status")
async def openclaw_get_status():
    """
    获取 OpenClaw 当前状态

    调用 session_status 工具获取实时状态

    Returns:
        OpenClaw 当前状态文本
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        result = await Modules.openclaw_client.get_session_status()
        return result
    except Exception as e:
        logger.error(f"获取 OpenClaw 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


# ============ OpenClaw 安装和配置管理 API ============


@app.get("/openclaw/install/check")
async def openclaw_check_installation():
    """
    检查 OpenClaw 安装状态

    Returns:
        安装状态信息
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        status, version = installer.check_installation()

        # 检查 Node.js
        node_ok, node_version = installer.check_node_version()

        return {
            "success": True,
            "status": status.value,
            "version": version,
            "node_ok": node_ok,
            "node_version": node_version,
            "npm_available": installer.check_npm_available(),
        }
    except Exception as e:
        logger.error(f"检查 OpenClaw 安装状态失败: {e}")
        raise HTTPException(500, f"检查失败: {e}")


@app.post("/openclaw/install")
async def openclaw_install(payload: Dict[str, Any] = None):
    """
    安装 OpenClaw

    请求体:
    - method: 安装方式 ("npm" 或 "script"，默认 "npm")

    Returns:
        安装结果
    """
    try:
        from agentserver.openclaw import get_openclaw_installer, InstallMethod

        installer = get_openclaw_installer()

        method_str = (payload or {}).get("method", "npm")
        method = InstallMethod.NPM if method_str == "npm" else InstallMethod.SCRIPT

        result = await installer.install(method)

        return result.to_dict()
    except Exception as e:
        logger.error(f"安装 OpenClaw 失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.post("/openclaw/setup")
async def openclaw_setup(payload: Dict[str, Any] = None):
    """
    初始化 OpenClaw 配置

    请求体:
    - hooks_token: Hooks 认证 token（可选，不传则自动生成）

    Returns:
        初始化结果
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        hooks_token = (payload or {}).get("hooks_token")

        result = await installer.setup(hooks_token)

        return result.to_dict()
    except Exception as e:
        logger.error(f"初始化 OpenClaw 失败: {e}")
        raise HTTPException(500, f"初始化失败: {e}")


@app.post("/openclaw/gateway/start")
async def openclaw_start_gateway():
    """启动 OpenClaw Gateway"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.start_gateway(background=True)

        return result.to_dict()
    except Exception as e:
        logger.error(f"启动 Gateway 失败: {e}")
        raise HTTPException(500, f"启动失败: {e}")


@app.post("/openclaw/gateway/stop")
async def openclaw_stop_gateway():
    """停止 OpenClaw Gateway"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.stop_gateway()

        return result.to_dict()
    except Exception as e:
        logger.error(f"停止 Gateway 失败: {e}")
        raise HTTPException(500, f"停止失败: {e}")


@app.post("/openclaw/gateway/restart")
async def openclaw_restart_gateway():
    """重启 OpenClaw Gateway"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.restart_gateway()

        return result.to_dict()
    except Exception as e:
        logger.error(f"重启 Gateway 失败: {e}")
        raise HTTPException(500, f"重启失败: {e}")


@app.post("/openclaw/gateway/install")
async def openclaw_install_gateway_service():
    """安装 Gateway 为系统服务"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.install_gateway_service()

        return result.to_dict()
    except Exception as e:
        logger.error(f"安装 Gateway 服务失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.get("/openclaw/gateway/status")
async def openclaw_gateway_status():
    """获取 Gateway 状态"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.check_gateway_status()

        return result
    except Exception as e:
        logger.error(f"获取 Gateway 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/doctor")
async def openclaw_doctor():
    """运行 OpenClaw 健康检查"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.run_doctor()

        return result
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(500, f"检查失败: {e}")


# ============ OpenClaw 配置管理 API ============


@app.get("/openclaw/config")
async def openclaw_get_config():
    """
    获取 OpenClaw 配置摘要

    只返回安全的配置信息，不包含 token 等敏感数据
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        config_manager = get_openclaw_config_manager()
        summary = config_manager.get_current_config_summary()

        return {"success": True, "config": summary}
    except Exception as e:
        logger.error(f"获取 OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/openclaw/config/set")
async def openclaw_set_config(payload: Dict[str, Any]):
    """
    设置 OpenClaw 配置

    只允许修改白名单中的字段

    请求体:
    - field: 字段路径（如 "agents.defaults.model.primary"）
    - value: 新值

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        field = payload.get("field")
        value = payload.get("value")

        if not field:
            raise HTTPException(400, "field 不能为空")

        config_manager = get_openclaw_config_manager()
        result = config_manager.set(field, value)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置 OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"设置失败: {e}")


@app.post("/openclaw/config/model")
async def openclaw_set_model(payload: Dict[str, Any]):
    """
    设置默认模型

    请求体:
    - model: 模型标识符（如 "zai/glm-4.7"）
    - alias: 模型别名（可选）

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        model = payload.get("model")
        alias = payload.get("alias")

        if not model:
            raise HTTPException(400, "model 不能为空")

        config_manager = get_openclaw_config_manager()

        results = []

        # 设置主模型
        result = config_manager.set_primary_model(model)
        results.append(result.to_dict())

        # 设置别名（如果提供）
        if alias:
            alias_result = config_manager.add_model_alias(model, alias)
            results.append(alias_result.to_dict())

        return {"success": all(r["success"] for r in results), "results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置模型失败: {e}")
        raise HTTPException(500, f"设置失败: {e}")


@app.post("/openclaw/config/hooks")
async def openclaw_configure_hooks(payload: Dict[str, Any]):
    """
    配置 Hooks

    请求体:
    - enabled: 是否启用（可选）
    - token: Hooks token（可选，不传则自动生成）

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        config_manager = get_openclaw_config_manager()
        results = []

        # 启用/禁用
        if "enabled" in payload:
            result = config_manager.set_hooks_enabled(payload["enabled"])
            results.append(result.to_dict())

        # 设置 token
        if "token" in payload:
            token = payload["token"]
        elif payload.get("generate_token"):
            token = config_manager.generate_hooks_token()
        else:
            token = None

        if token:
            result = config_manager.set_hooks_token(token)
            results.append(result.to_dict())

        return {
            "success": all(r["success"] for r in results) if results else True,
            "results": results,
            "token": token,  # 返回生成的 token
        }
    except Exception as e:
        logger.error(f"配置 Hooks 失败: {e}")
        raise HTTPException(500, f"配置失败: {e}")


# ============ OpenClaw Skills 管理 API ============


@app.get("/openclaw/skills")
async def openclaw_list_skills():
    """列出已安装的 Skills"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        skills = await installer.list_skills()

        return {"success": True, "skills": skills}
    except Exception as e:
        logger.error(f"列出 Skills 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/openclaw/skills/install")
async def openclaw_install_skill(payload: Dict[str, Any]):
    """
    安装 Skill

    请求体:
    - skill: Skill 标识符

    Returns:
        安装结果
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        skill = payload.get("skill")
        if not skill:
            raise HTTPException(400, "skill 不能为空")

        installer = get_openclaw_installer()
        result = await installer.install_skill(skill)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"安装 Skill 失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.post("/openclaw/skills/enable")
async def openclaw_enable_skill(payload: Dict[str, Any]):
    """
    启用/禁用 Skill

    请求体:
    - skill: Skill 名称
    - enabled: 是否启用

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        skill = payload.get("skill")
        enabled = payload.get("enabled", True)

        if not skill:
            raise HTTPException(400, "skill 不能为空")

        config_manager = get_openclaw_config_manager()
        result = config_manager.enable_skill(skill, enabled)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启用/禁用 Skill 失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


# ============ 旅行执行 ============

@app.post("/travel/execute")
async def travel_execute(payload: Dict[str, Any]):
    """接收旅行 session_id，异步启动旅行协程"""
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(400, "session_id 不能为空")

    from apiserver.travel_service import load_session, TravelStatus

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "旅行 session 不存在")

    if session.agent_id:
        if not Modules.instance_manager:
            raise HTTPException(503, "实例管理器未就绪")
    elif not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    _spawn_travel_session(session_id, resumed=session.status == TravelStatus.INTERRUPTED)
    return {"status": "accepted", "session_id": session_id}


@app.post("/travel/interrupt")
async def travel_interrupt(payload: Dict[str, Any]):
    """将一个或多个探索任务切到 interrupted，并中断对应协程。"""
    raw_session_ids = payload.get("session_ids")
    session_id = payload.get("session_id")
    session_ids: Optional[list[str]]
    if isinstance(raw_session_ids, list):
        session_ids = [str(item) for item in raw_session_ids if item]
    elif session_id:
        session_ids = [str(session_id)]
    else:
        session_ids = None

    interrupted_ids = await _interrupt_travel_sessions(
        session_ids=session_ids,
        reason=str(payload.get("reason") or "interrupted"),
    )
    return {"status": "success", "session_ids": interrupted_ids}


@app.post("/travel/browser-settings")
async def travel_browser_settings(payload: Dict[str, Any]):
    from apiserver.travel_service import load_session

    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(400, "session_id 不能为空")

    try:
        session = load_session(str(session_id))
    except FileNotFoundError:
        raise HTTPException(404, "旅行 session 不存在")

    if not session.agent_id or not Modules.instance_manager:
        return {"status": "success", "applied": False, "reason": "no_agent_instance"}

    visible = payload.get("browser_visible")
    result = await Modules.instance_manager.update_browser_preferences(
        session.agent_id,
        visible=None if visible is None else bool(visible),
    )
    return {"status": "success", "applied": True, "result": result}


@app.post("/travel/instruction")
async def travel_instruction(payload: Dict[str, Any]):
    from apiserver.travel_service import (
        OPEN_TRAVEL_STATUSES,
        append_progress_event,
        build_travel_instruction_prompt,
        load_session,
        save_session,
    )

    session_id = str(payload.get("session_id") or "").strip()
    message = str(payload.get("message") or "").strip()
    if not session_id:
        raise HTTPException(400, "session_id 不能为空")
    if not message:
        raise HTTPException(400, "message 不能为空")

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "旅行 session 不存在")

    if session.status not in OPEN_TRAVEL_STATUSES:
        raise HTTPException(409, "当前探索已结束，不能再追加指令")

    session_key = (session.openclaw_session_key or "").strip()
    if not session_key:
        raise HTTPException(409, "当前探索还没进入可交互阶段")

    prompt = build_travel_instruction_prompt(message)
    if session.agent_id:
        if not Modules.instance_manager:
            raise HTTPException(503, "实例管理器未就绪")
        await Modules.instance_manager.ensure_running(session.agent_id)

        async def _worker(inst):
            if not inst.client:
                raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
            return await inst.client.send_message(
                message=prompt,
                session_key=session_key,
                name="NagaTravel",
                timeout_seconds=0,
            )

        await Modules.instance_manager.run_serialized(session.agent_id, _worker)
    else:
        if not Modules.openclaw_client:
            raise HTTPException(503, "OpenClaw 客户端未就绪")
        await Modules.openclaw_client.send_message(
            message=prompt,
            session_key=session_key,
            name="NagaTravel",
            timeout_seconds=0,
        )

    append_progress_event(
        session,
        "user_instruction",
        f"已追加探索指令：{message[:80]}",
        meta={"message": message[:400]},
    )
    save_session(session)
    return {"status": "success", "session_id": session_id}


async def _run_travel_session(session_id: str, *, resumed: bool = False):
    """旅行主循环协程"""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from apiserver.travel_service import (
        append_progress_event,
        load_session, save_session, TravelStatus,
        analyze_history,
        build_forum_post_payload,
        build_quota_warning_prompt,
        build_social_prompt,
        build_travel_prompt,
        build_wrap_up_prompt,
        remove_session_browser_policy,
        set_session_phase,
        sync_session_browser_policy,
    )
    from agentserver.travel_notifications import (
        build_travel_full_report_message,
        deliver_travel_completion_notifications,
    )

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        logger.error(f"旅行 session 不存在: {session_id}")
        return

    travel_client = Modules.openclaw_client
    if session.agent_id:
        if not Modules.instance_manager:
            raise RuntimeError("实例管理器未就绪，无法使用指定干员执行探索")
        inst = await Modules.instance_manager.ensure_running(session.agent_id)
        if not inst.client:
            raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
        session.agent_name = inst.name
        travel_client = inst.client
        await Modules.instance_manager.update_browser_preferences(
            session.agent_id,
            visible=session.browser_visible,
            stop_browser_if_changed=False,
        )
    elif travel_client is None:
        raise RuntimeError("OpenClaw 客户端未就绪")

    session_key = f"travel:{session.agent_id or 'main'}:{session_id[:8]}"
    session.openclaw_session_key = session_key
    session.status = TravelStatus.RUNNING
    session.interrupted_at = None
    session.interrupted_reason = None
    if not session.started_at:
        session.started_at = datetime.now().isoformat()
    if resumed:
        session.resume_count += 1
    session.last_heartbeat_at = datetime.now().isoformat()
    set_session_phase(
        session,
        "bootstrapping",
        message=f"已分配给干员 {session.agent_name or session.agent_id or '默认干员'}，准备开始探索。",
        meta={
            "agent_id": session.agent_id,
            "openclaw_session_key": session_key,
            "resumed": resumed,
        },
    )
    sync_session_browser_policy(session)
    await emit_local_telemetry(
        "explore_dispatch_agent",
        {
            "agent_name": session.agent_name,
            "uses_dedicated_agent": bool(session.agent_id),
            "time_limit_minutes": session.time_limit_minutes,
            "credit_limit": session.credit_limit,
        },
        trace_id=f"travel:{session_id}",
        session_id=session_id,
        agent_id=session.agent_id,
    )
    await emit_local_telemetry(
        "openclaw_task_created",
        {
            "openclaw_session_key": session_key,
            "agent_name": session.agent_name,
        },
        trace_id=f"travel:{session_id}",
        session_id=session_id,
        agent_id=session.agent_id,
    )

    logger.info(
        f"[旅行] 开始旅行 session: {session_id}, key={session_key}, "
        f"agent={session.agent_name or session.agent_id or 'default'}"
    )

    def _apply_history_analysis(current_session, analysis) -> None:
        current_session.discoveries = analysis.discoveries
        current_session.social_interactions = analysis.social_interactions
        current_session.credits_used = analysis.credits_used
        current_session.tool_stats = analysis.tool_stats
        current_session.sources = list(getattr(analysis, "sources", []) or [])
        current_session.unique_sources = len(current_session.sources)
        if getattr(analysis, "summary_report_path", None):
            current_session.summary_report_path = analysis.summary_report_path
        if getattr(analysis, "summary_report_title", None):
            current_session.summary_report_title = analysis.summary_report_title

    async def _send_to_travel_client(**kwargs):
        if session.agent_id:
            if not Modules.instance_manager:
                raise RuntimeError("实例管理器未就绪")

            async def _worker(inst):
                if not inst.client:
                    raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
                return await inst.client.send_message(**kwargs)

            return await Modules.instance_manager.run_serialized(session.agent_id, _worker)
        return await travel_client.send_message(**kwargs)

    async def _load_travel_history(*, limit: int, include_tools: bool):
        if session.agent_id:
            if not Modules.instance_manager:
                raise RuntimeError("实例管理器未就绪")

            async def _worker(inst):
                if not inst.client:
                    raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
                return await inst.client.get_local_session_history(
                    session_key=session_key,
                    limit=limit,
                )

            return await Modules.instance_manager.run_serialized(session.agent_id, _worker)
        return await travel_client.get_local_session_history(
            session_key=session_key,
            limit=limit,
        )

    async def _cleanup_travel_browser(current_session, *, reason: str) -> None:
        cleanup_session_key = str(
            getattr(current_session, "openclaw_session_key", None) or session_key or ""
        ).strip()
        if not cleanup_session_key:
            return

        try:
            if current_session.agent_id:
                if not Modules.instance_manager:
                    raise RuntimeError("实例管理器未就绪")

                async def _worker(inst):
                    if not inst.client:
                        raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
                    return await inst.client.invoke_tool(
                        tool="browser",
                        args={"action": "stop"},
                        session_key=cleanup_session_key,
                    )

                result = await Modules.instance_manager.run_serialized(current_session.agent_id, _worker)
            else:
                result = await travel_client.invoke_tool(
                    tool="browser",
                    args={"action": "stop"},
                    session_key=cleanup_session_key,
                )

            if isinstance(result, dict) and result.get("success"):
                logger.info(f"[旅行] 已回收浏览器句柄: session={session_id}, reason={reason}")
            else:
                logger.warning(
                    f"[旅行] 浏览器句柄回收未完全成功: session={session_id}, reason={reason}, result={result}"
                )
        except Exception as cleanup_error:
            logger.warning(
                f"[旅行] 浏览器句柄回收失败: session={session_id}, reason={reason}, error={cleanup_error}"
            )
        finally:
            remove_session_browser_policy(cleanup_session_key)

    try:
        # 发送探索指令
        await _send_to_travel_client(
            message=build_travel_prompt(session),
            session_key=session_key,
            name="NagaTravel",
            timeout_seconds=0,
        )
        set_session_phase(
            session,
            "running",
            message="主探索指令已下发，开始检索最新线索。",
        )

        # 如果想社交，额外发送社交指令
        if session.want_friends:
            await _send_to_travel_client(
                message=build_social_prompt(session),
                session_key=session_key,
                name="NagaTravel",
                timeout_seconds=0,
            )
            append_progress_event(
                session,
                "social_prompt_sent",
                "已追加社交探索指令，会在合适时尝试扩展互动。",
            )
            save_session(session)

        # 监控循环
        start_time = datetime.fromisoformat(session.started_at)
        seen_discovery_urls: set = set()
        seen_social_keys: set = set()

        while True:
            await asyncio.sleep(30)

            # 检查时间限制
            elapsed = (datetime.now() - start_time).total_seconds() / 60
            session.elapsed_minutes = round(elapsed, 1)
            remaining_minutes = max(0.0, session.time_limit_minutes - elapsed)
            remaining_credits = max(0, session.credit_limit - session.credits_used)

            if elapsed >= session.time_limit_minutes:
                logger.info(f"[旅行] 时间到达限制 {session.time_limit_minutes} 分钟")
                break

            # 重新加载 session（可能被外部 cancel）
            try:
                session = load_session(session_id)
            except Exception:
                break

            if session.status == TravelStatus.CANCELLED:
                logger.info(f"[旅行] session 已被取消: {session_id}")
                await _cleanup_travel_browser(session, reason="cancelled")
                return

            if session.status == TravelStatus.INTERRUPTED:
                logger.info(f"[旅行] session 已被中断: {session_id}")
                await _cleanup_travel_browser(session, reason="interrupted")
                return

            previous_discovery_count = len(session.discoveries)

            # 轮询 OpenClaw 获取新消息
            try:
                history = await _load_travel_history(limit=80, include_tools=True)
                messages = history if isinstance(history, list) else history.get("messages", [])

                # 从工具结果和阶段性文本中提炼发现、社交、预算
                analysis = analyze_history(messages)
                _apply_history_analysis(session, analysis)

                existing_activity_ids = {
                    str((event.meta or {}).get("travel_tool_call_id"))
                    for event in session.progress_events
                    if (event.meta or {}).get("travel_tool_call_id")
                }
                for activity_event in getattr(analysis, "activity_events", []) or []:
                    activity_id = str((activity_event.meta or {}).get("travel_tool_call_id") or "")
                    if activity_id and activity_id in existing_activity_ids:
                        continue
                    append_progress_event(
                        session,
                        activity_event.type,
                        activity_event.message,
                        level=activity_event.level,
                        meta=activity_event.meta,
                        timestamp=activity_event.timestamp,
                    )
                    if activity_id:
                        existing_activity_ids.add(activity_id)

                for d in session.discoveries:
                    seen_discovery_urls.add(d.url)

                for s in session.social_interactions:
                    key = f"{s.type}:{s.post_id}:{s.content_preview[:30]}"
                    if key not in seen_social_keys:
                        seen_social_keys.add(key)
                if len(session.discoveries) > previous_discovery_count:
                    append_progress_event(
                        session,
                        "discoveries_updated",
                        f"本轮新增 {len(session.discoveries) - previous_discovery_count} 条发现，累计 {len(session.discoveries)} 条。",
                        meta={
                            "discoveries": len(session.discoveries),
                            "unique_sources": session.unique_sources,
                            "credits_used": session.credits_used,
                        },
                    )
                    await emit_local_telemetry(
                        "openclaw_discovery_added",
                        {
                            "new_discoveries": len(session.discoveries) - previous_discovery_count,
                            "total_discoveries": len(session.discoveries),
                            "unique_sources": session.unique_sources,
                            "credits_used": session.credits_used,
                        },
                        trace_id=f"travel:{session_id}",
                        session_id=session_id,
                        agent_id=session.agent_id,
                    )
                    session.idle_polls = 0
                else:
                    session.idle_polls += 1

            except Exception as e:
                logger.warning(f"[旅行] 轮询历史失败: {e}")

            session.elapsed_minutes = round(elapsed, 1)
            session.last_heartbeat_at = datetime.now().isoformat()

            time_warning_threshold = max(1.0, session.time_limit_minutes * 0.1)
            credit_warning_threshold = max(1, int(session.credit_limit * 0.1))
            warning_trigger: Optional[str] = None
            if not session.time_warning_sent and remaining_minutes <= time_warning_threshold:
                warning_trigger = "time"
            if not session.credit_warning_sent and remaining_credits <= credit_warning_threshold:
                warning_trigger = "both" if warning_trigger == "time" else "credit"
            if warning_trigger:
                try:
                    await _send_to_travel_client(
                        message=build_quota_warning_prompt(
                            session,
                            remaining_minutes=remaining_minutes,
                            remaining_credits=remaining_credits,
                            trigger=warning_trigger,
                        ),
                        session_key=session_key,
                        name="NagaTravel",
                        timeout_seconds=0,
                    )
                    append_progress_event(
                        session,
                        "quota_warning",
                        f"配额接近上限：剩余约 {max(0.0, remaining_minutes):.1f} 分钟，剩余约 {max(0, remaining_credits)} 积分。",
                        level="warn",
                        meta={
                            "trigger": warning_trigger,
                            "remaining_minutes": round(max(0.0, remaining_minutes), 1),
                            "remaining_credits": max(0, remaining_credits),
                        },
                    )
                    if warning_trigger in {"time", "both"}:
                        session.time_warning_sent = True
                    if warning_trigger in {"credit", "both"}:
                        session.credit_warning_sent = True
                except Exception as e:
                    logger.warning(f"[旅行] 发送预算预警失败: {e}")

            # 预算接近上限或长时间无增量时，要求 OpenClaw 开始收束
            wrap_up_threshold = int(session.credit_limit * 0.9)
            hard_stop_threshold = session.credit_limit
            should_request_wrap_up = (
                (
                    (
                        session.credits_used >= wrap_up_threshold
                        or remaining_minutes <= time_warning_threshold
                    )
                    and (len(session.discoveries) > 0 or session.idle_polls >= 1)
                )
                or (session.idle_polls >= 2 and len(session.discoveries) > 0)
            )
            if should_request_wrap_up and not session.wrap_up_sent:
                try:
                    await _send_to_travel_client(
                        message=build_wrap_up_prompt(session),
                        session_key=session_key,
                        name="NagaTravel",
                        timeout_seconds=0,
                    )
                    session.wrap_up_sent = True
                    set_session_phase(
                        session,
                        "wrapping_up",
                        message="探索已进入收束阶段，正在整理最终报告。",
                        meta={
                            "credits_used": session.credits_used,
                            "idle_polls": session.idle_polls,
                            "discoveries": len(session.discoveries),
                        },
                    )
                    logger.info(
                        f"[旅行] 已发送收束指令: {session_id}, credits={session.credits_used}, idle={session.idle_polls}"
                    )
                    await emit_local_telemetry(
                        "explore_wrap_up_requested",
                        {
                            "credits_used": session.credits_used,
                            "credit_limit": session.credit_limit,
                            "idle_polls": session.idle_polls,
                            "discoveries": len(session.discoveries),
                        },
                        trace_id=f"travel:{session_id}",
                        session_id=session_id,
                        agent_id=session.agent_id,
                    )
                except Exception as e:
                    logger.warning(f"[旅行] 发送收束指令失败: {e}")

            if session.credits_used >= hard_stop_threshold:
                append_progress_event(
                    session,
                    "hard_limit",
                    f"已达到积分限制 {session.credits_used}/{session.credit_limit}，准备结束探索。",
                    level="warn",
                )
                logger.info(f"[旅行] 估算积分到达限制 {session.credits_used}/{session.credit_limit}")
                break

            if session.idle_polls >= 4 and len(session.discoveries) > 0:
                append_progress_event(
                    session,
                    "idle_stop",
                    "长时间没有新增发现，准备结束并整理结果。",
                    meta={"idle_polls": session.idle_polls},
                )
                logger.info(f"[旅行] 长时间无新增发现，准备结束: idle_polls={session.idle_polls}")
                break

            save_session(session)

        # 发送收尾指令
        logger.info(f"[旅行] 发送收尾指令: {session_id}")
        set_session_phase(
            session,
            "finalizing",
            message="已发送最终收尾指令，正在等待探索总结。",
        )
        try:
            await _send_to_travel_client(
                message=build_wrap_up_prompt(session),
                session_key=session_key,
                name="NagaTravel",
                timeout_seconds=300,
            )

            # 等待并获取最终回复
            await asyncio.sleep(30)
            history = await _load_travel_history(limit=20, include_tools=False)
            messages = history if isinstance(history, list) else history.get("messages", [])
            # 最后一条 assistant 消息作为 summary
            for msg in reversed(messages):
                role = msg.get("role", "")
                if role == "assistant":
                    session.summary = msg.get("content", "")[:2000]
                    await emit_local_telemetry(
                        "explore_summary_ready",
                        {
                            "summary_chars": len(session.summary or ""),
                        },
                        trace_id=f"travel:{session_id}",
                        session_id=session_id,
                        agent_id=session.agent_id,
                    )
                    break

            # 收尾完成后重新解析完整历史，确保最终总结里的真实 discovery 会落盘。
            final_history = await _load_travel_history(limit=120, include_tools=True)
            final_messages = final_history if isinstance(final_history, list) else final_history.get("messages", [])
            final_analysis = analyze_history(final_messages)
            _apply_history_analysis(session, final_analysis)
        except Exception as e:
            logger.warning(f"[旅行] 收尾指令失败: {e}")
            session.summary = f"旅行完成，共发现 {len(session.discoveries)} 个内容。（收尾指令超时）"

        session.status = TravelStatus.COMPLETED
        session.phase = "completed"
        session.completed_at = datetime.now().isoformat()
        append_progress_event(
            session,
            "completed",
            f"探索已完成：累计 {len(session.discoveries)} 条发现，{session.unique_sources} 个来源。",
            meta={
                "discoveries": len(session.discoveries),
                "unique_sources": session.unique_sources,
                "credits_used": session.credits_used,
                "elapsed_minutes": session.elapsed_minutes,
            },
        )
        save_session(session)
        await _cleanup_travel_browser(session, reason="completed")

        logger.info(
            f"[旅行] 完成: {session_id}, 发现={len(session.discoveries)}, 社交={len(session.social_interactions)}"
        )

        # 自动产出论坛精华版
        if session.post_to_forum and session.summary:
            try:
                set_session_phase(
                    session,
                    "publishing",
                    message="正在自动发布论坛精华摘要。",
                )
                from apiserver.routes.forum import create_forum_post_internal

                forum_payload = build_forum_post_payload(session)
                session.forum_digest = forum_payload.get("content")
                post_result = await create_forum_post_internal(forum_payload, timeout_seconds=20.0)
                if isinstance(post_result, dict):
                    session.forum_post_id = str(
                        post_result.get("id")
                        or post_result.get("postId")
                        or post_result.get("post", {}).get("id")
                        or ""
                    ) or None
                session.forum_post_status = "posted"
                append_progress_event(
                    session,
                    "forum_posted",
                    "探索摘要已自动发布到论坛。",
                    meta={"forum_post_id": session.forum_post_id},
                )
                save_session(session)
                logger.info(f"[旅行] 已自动发布论坛精华帖: session={session_id}, post_id={session.forum_post_id}")
            except Exception as e:
                session.forum_post_status = f"failed:{e}"
                append_progress_event(
                    session,
                    "forum_post_failed",
                    f"论坛自动发布失败：{e}",
                    level="error",
                )
                save_session(session)
                logger.warning(f"[旅行] 自动发布论坛精华帖失败: {e}")

        # 完整版报告回传给用户/通道
        if session.deliver_full_report:
            try:
                set_session_phase(
                    session,
                    "delivering_report",
                    message="正在回传完整探索报告。",
                )
                if not session.deliver_channel and not session.deliver_to:
                    session.full_report_delivery_status = "stored_in_app"
                    save_session(session)
                else:
                    deliver_kwargs = {
                        "message": build_travel_full_report_message(session),
                        "deliver": True,
                        "session_key": session_key,
                        "name": "NagaTravel",
                        "timeout_seconds": 30,
                    }
                    if session.deliver_channel:
                        deliver_kwargs["channel"] = session.deliver_channel
                    if session.deliver_to:
                        deliver_kwargs["to"] = session.deliver_to
                    await _send_to_travel_client(**deliver_kwargs)
                    session.full_report_delivery_status = "delivered"
                append_progress_event(
                    session,
                    "report_delivery",
                    "探索结果已按当前配置完成回传。",
                    meta={"channel": session.deliver_channel or "in_app"},
                )
                save_session(session)
            except Exception as e:
                session.full_report_delivery_status = f"failed:{e}"
                append_progress_event(
                    session,
                    "report_delivery_failed",
                    f"探索结果回传失败：{e}",
                    level="error",
                )
                save_session(session)
                logger.warning(f"[旅行] 完整报告回传失败: {e}")

        try:
            set_session_phase(
                session,
                "notifying",
                message="正在发送探索完成通知。",
            )
            session.notification_delivery_statuses = await deliver_travel_completion_notifications(session, travel_client)
            save_session(session)
            for channel, status in session.notification_delivery_statuses.items():
                await emit_local_telemetry(
                    "notify_delivery_success" if not str(status).startswith("failed:") else "notify_delivery_fail",
                    {
                        "channel": channel,
                        "status": status,
                    },
                    trace_id=f"travel:{session_id}",
                    session_id=session_id,
                    agent_id=session.agent_id,
                )
        except Exception as e:
            logger.warning(f"[旅行] 完成通知发送失败: {e}")

        session.phase = "completed"
        save_session(session)

        await emit_local_telemetry(
            "explore_finish",
            {
                "discoveries": len(session.discoveries),
                "social_interactions": len(session.social_interactions),
                "credits_used": session.credits_used,
                "elapsed_minutes": session.elapsed_minutes,
                "unique_sources": session.unique_sources,
                "forum_post_status": session.forum_post_status,
                "full_report_delivery_status": session.full_report_delivery_status,
                "notification_delivery_statuses": session.notification_delivery_statuses,
            },
            trace_id=f"travel:{session_id}",
            session_id=session_id,
            agent_id=session.agent_id,
        )

    except asyncio.CancelledError:
        try:
            session = load_session(session_id)
            if session.status == TravelStatus.CANCELLED:
                session.phase = "cancelled"
                append_progress_event(
                    session,
                    "cancelled",
                    "探索已取消。",
                    level="warn",
                )
                save_session(session)
                await _cleanup_travel_browser(session, reason="cancelled")
                logger.info(f"[旅行] 协程已取消（已取消态）: {session_id}")
            elif session.status == TravelStatus.INTERRUPTED:
                session.phase = "interrupted"
                save_session(session)
                await _cleanup_travel_browser(session, reason="interrupted")
                logger.info(f"[旅行] 协程已取消（已中断态）: {session_id}")
            else:
                from apiserver.travel_service import mark_session_interrupted

                session = mark_session_interrupted(session, reason="task_cancelled")
                await _cleanup_travel_browser(session, reason="task_cancelled")
                logger.info(f"[旅行] 协程已取消并转为中断态: {session_id}")
        except Exception as inner:
            logger.warning(f"[旅行] 处理取消态失败 [{session_id}]: {inner}")
        raise
    except Exception as e:
        logger.error(f"[旅行] 异常: {e}", exc_info=True)
        try:
            session = load_session(session_id)
            session.status = TravelStatus.FAILED
            session.phase = "failed"
            session.error = str(e)
            session.completed_at = datetime.now().isoformat()
            append_progress_event(
                session,
                "failed",
                f"探索执行失败：{e}",
                level="error",
            )
            save_session(session)
            await _cleanup_travel_browser(session, reason="failed")
            await emit_local_telemetry(
                "explore_fail",
                {
                    "error": e,
                    "discoveries": len(session.discoveries),
                    "credits_used": session.credits_used,
                },
                trace_id=f"travel:{session_id}",
                session_id=session_id,
                agent_id=session.agent_id,
            )
        except Exception:
            pass


# ========== Proactive Vision API ==========


@app.get("/proactive_vision/config")
async def get_proactive_vision_config():
    """获取主动视觉系统配置"""
    try:
        from agentserver.dogtag import load_proactive_config

        config = load_proactive_config()
        return {"success": True, "config": config.model_dump()}
    except Exception as e:
        logger.error(f"获取 ProactiveVision 配置失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/proactive_vision/config")
async def update_proactive_vision_config(payload: Dict[str, Any]):
    """更新主动视觉系统配置"""
    try:
        from agentserver.dogtag import (
            load_proactive_config,
            save_proactive_config,
            ProactiveVisionConfig,
            create_proactive_analyzer,
        )
        from agentserver.dogtag import get_dogtag_registry
        from agentserver.dogtag.duties.screen_vision_duty import create_screen_vision_duty

        # 加载当前配置并备份到内存（用于回滚）
        old_config_backup = load_proactive_config()

        # 更新字段
        config_dict = old_config_backup.model_dump()
        config_dict.update(payload)

        # 创建新配置对象并验证
        new_config = ProactiveVisionConfig(**config_dict)

        # 先保存配置，确保配置有效
        if not save_proactive_config(new_config):
            raise HTTPException(500, "配置保存失败")

        # 重新注册 screen_vision 职责
        try:
            create_proactive_analyzer(new_config)
            registry = get_dogtag_registry()
            sv_tag, sv_exec = create_screen_vision_duty(new_config)
            registry.register(sv_tag, sv_exec)
            logger.info("[ProactiveVision] 配置已更新，screen_vision 职责已重新注册")
        except Exception as e:
            logger.error(f"[ProactiveVision] 应用新配置失败: {e}")
            # 回滚
            try:
                save_proactive_config(old_config_backup)
                create_proactive_analyzer(old_config_backup)
                sv_tag_old, sv_exec_old = create_screen_vision_duty(old_config_backup)
                registry.register(sv_tag_old, sv_exec_old)
                logger.info("[ProactiveVision] 已成功回滚到旧配置")
            except Exception as rollback_error:
                logger.error(f"[ProactiveVision] 回滚失败: {rollback_error}")
            raise HTTPException(500, f"应用新配置失败，已尝试回滚: {e}")

        return {"success": True, "message": "配置已更新", "config": new_config.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 ProactiveVision 配置失败: {e}")
        raise HTTPException(500, f"更新失败: {e}")


@app.post("/proactive_vision/enable")
async def enable_proactive_vision(payload: Dict[str, Any]):
    """启用/禁用主动视觉系统"""
    try:
        enabled = payload.get("enabled", True)

        from agentserver.dogtag import load_proactive_config, save_proactive_config, get_dogtag_registry
        from agentserver.dogtag.models import DutyStatus

        config = load_proactive_config()
        config.enabled = enabled

        if save_proactive_config(config):
            registry = get_dogtag_registry()
            registry.update_status(
                "screen_vision",
                DutyStatus.ENABLED if enabled else DutyStatus.DISABLED,
            )

            status = "已启用" if enabled else "已禁用"
            return {"success": True, "message": f"主动视觉系统{status}", "enabled": enabled}
        else:
            raise HTTPException(500, "配置保存失败")
    except Exception as e:
        logger.error(f"切换 ProactiveVision 状态失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


@app.get("/proactive_vision/status")
async def get_proactive_vision_status():
    """获取主动视觉系统运行状态"""
    try:
        if not Modules.dogtag_scheduler:
            return {
                "success": True,
                "running": False,
                "enabled": False,
                "message": "调度器未初始化",
            }

        from agentserver.dogtag import load_proactive_config, get_proactive_analyzer, get_dogtag_registry

        config = load_proactive_config()
        registry = get_dogtag_registry()
        sv_tag = registry.get("screen_vision")

        # 获取性能统计
        performance_stats = {}
        analyzer = get_proactive_analyzer()
        if analyzer:
            performance_stats = analyzer.get_performance_stats()

        return {
            "success": True,
            "running": Modules.dogtag_scheduler._running,
            "enabled": config.enabled,
            "duty_status": sv_tag.status.value if sv_tag else "unregistered",
            "last_check": Modules.dogtag_scheduler._last_check_times.get("screen_vision", 0),
            "last_activity": Modules.dogtag_scheduler._last_user_activity,
            "check_interval": config.check_interval_seconds,
            "performance": performance_stats,
        }
    except Exception as e:
        logger.error(f"获取 ProactiveVision 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/proactive_vision/trigger/test")
async def test_proactive_vision_trigger(payload: Dict[str, Any]):
    """测试触发规则（忽略冷却时间）"""
    try:
        rule_id = payload.get("rule_id")
        if not rule_id:
            raise HTTPException(400, "rule_id 不能为空")

        from agentserver.dogtag import load_proactive_config, get_proactive_trigger

        config = load_proactive_config()
        rule = None
        for r in config.trigger_rules:
            if r.rule_id == rule_id:
                rule = r
                break

        if not rule:
            raise HTTPException(404, f"规则不存在: {rule_id}")

        trigger = get_proactive_trigger()
        if not trigger:
            raise HTTPException(503, "触发器未初始化")

        # 重置冷却时间以允许立即触发
        trigger.reset_cooldown(rule_id)

        # 发送测试消息
        test_context = "这是一条测试消息"
        await trigger.send_proactive_message(rule, test_context)

        return {"success": True, "message": f"测试触发规则: {rule.name}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试 ProactiveVision 触发失败: {e}")
        raise HTTPException(500, f"测试失败: {e}")


@app.post("/proactive_vision/activity")
async def update_user_activity():
    """更新用户活动时间（由前端定期调用）"""
    try:
        if Modules.dogtag_scheduler:
            Modules.dogtag_scheduler.update_user_activity()
        return {"success": True}
    except Exception as e:
        logger.error(f"更新用户活动时间失败: {e}")
        return {"success": False, "error": str(e)}


@app.post("/proactive_vision/window_mode")
async def set_proactive_vision_window_mode(payload: Dict[str, Any]):
    """设置窗口模式（由前端在模式切换时调用）

    ProactiveVision只在悬浮球模式（ball/compact/full）下运行，classic模式时暂停

    Args:
        payload: {"mode": "classic" | "ball" | "compact" | "full"}
    """
    try:
        mode = payload.get("mode", "classic")

        if mode not in ("classic", "ball", "compact", "full"):
            return {"success": False, "error": f"无效的窗口模式: {mode}"}

        if Modules.dogtag_scheduler:
            Modules.dogtag_scheduler.set_window_mode(mode)

        return {
            "success": True,
            "mode": mode,
            "active": mode in ("ball", "compact", "full"),
        }
    except Exception as e:
        logger.error(f"设置窗口模式失败: {e}")
        return {"success": False, "error": str(e)}


@app.post("/proactive_vision/reset_timer")
async def reset_proactive_vision_timer(payload: Dict[str, Any]):
    """重置ProactiveVision检查计时器（由MCP Server调用）

    当AI主动调用screen_vision MCP时，MCP Server会调用此API重置计时器，
    避免ProactiveVision短时间内重复分析同一屏幕。

    Args:
        payload: {"reason": "mcp_call_screen_vision"}
    """
    try:
        reason = payload.get("reason", "external_trigger")

        if Modules.dogtag_scheduler:
            Modules.dogtag_scheduler.reset_check_timer("screen_vision", reason)
            return {
                "success": True,
                "message": "计时器已重置",
                "reason": reason,
            }
        else:
            return {
                "success": False,
                "error": "军牌调度器未初始化",
            }
    except Exception as e:
        logger.error(f"重置ProactiveVision计时器失败: {e}")
        return {"success": False, "error": str(e)}


@app.get("/proactive_vision/metrics")
async def get_proactive_vision_metrics():
    """获取ProactiveVision性能指标"""
    try:
        from agentserver.dogtag.screen_vision.metrics import get_metrics

        metrics = get_metrics()
        all_metrics = metrics.get_all_metrics()

        return {
            "success": True,
            "metrics": all_metrics,
        }
    except Exception as e:
        logger.error(f"获取 ProactiveVision metrics 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/proactive_vision/metrics/prometheus")
async def get_proactive_vision_metrics_prometheus():
    """获取Prometheus格式的性能指标"""
    try:
        from agentserver.dogtag.screen_vision.metrics import get_metrics
        from fastapi.responses import PlainTextResponse

        metrics = get_metrics()
        prometheus_text = metrics.get_prometheus_format()

        return PlainTextResponse(content=prometheus_text, media_type="text/plain; version=0.0.4")
    except Exception as e:
        logger.error(f"获取 Prometheus metrics 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


# ======================================================================
# Heartbeat 心跳系统端点
# ======================================================================


@app.post("/heartbeat/conversation_event")
async def heartbeat_conversation_event(payload: Dict[str, Any]):
    """接收 api_server 的对话生命周期事件（兼容旧路由，委托给军牌系统）"""
    return await dogtag_conversation_event(payload)


@app.get("/heartbeat/config")
async def get_heartbeat_config():
    """获取心跳系统配置"""
    try:
        from agentserver.dogtag import load_heartbeat_config

        cfg = load_heartbeat_config()
        return {"success": True, "config": cfg.model_dump()}
    except Exception as e:
        logger.error(f"获取 Heartbeat 配置失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/heartbeat/config")
async def update_heartbeat_config(payload: Dict[str, Any]):
    """更新心跳系统配置（含重新注册职责）"""
    try:
        from agentserver.dogtag import (
            load_heartbeat_config,
            save_heartbeat_config,
            HeartbeatConfig,
            create_heartbeat_executor,
            get_dogtag_registry,
        )
        from agentserver.dogtag.duties.heartbeat_duty import create_heartbeat_duty

        old_config = load_heartbeat_config()
        config_dict = old_config.model_dump()
        config_dict.update(payload)
        new_config = HeartbeatConfig(**config_dict)

        if not save_heartbeat_config(new_config):
            raise HTTPException(500, "配置保存失败")

        # 重建执行器 + 重新注册职责
        create_heartbeat_executor(new_config)
        registry = get_dogtag_registry()
        hb_tag, hb_exec = create_heartbeat_duty(new_config)
        registry.register(hb_tag, hb_exec)
        logger.info("[Heartbeat] 配置已更新，heartbeat 职责已重新注册")

        return {"success": True, "message": "配置已更新", "config": new_config.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 Heartbeat 配置失败: {e}")
        raise HTTPException(500, f"更新失败: {e}")


@app.post("/heartbeat/enable")
async def enable_heartbeat(payload: Dict[str, Any]):
    """快捷开关：启用/禁用心跳系统"""
    try:
        enabled = payload.get("enabled", True)

        from agentserver.dogtag import load_heartbeat_config, save_heartbeat_config, get_dogtag_registry
        from agentserver.dogtag.models import DutyStatus

        cfg = load_heartbeat_config()
        cfg.enabled = enabled

        if save_heartbeat_config(cfg):
            registry = get_dogtag_registry()
            registry.update_status(
                "heartbeat",
                DutyStatus.ENABLED if enabled else DutyStatus.DISABLED,
            )

            # 同步执行器的配置
            from agentserver.dogtag import get_heartbeat_executor
            hb = get_heartbeat_executor()
            if hb:
                hb.config = cfg

            status = "已启用" if enabled else "已禁用"
            return {"success": True, "message": f"心跳系统{status}", "enabled": enabled}
        else:
            raise HTTPException(500, "配置保存失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换 Heartbeat 状态失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


@app.post("/heartbeat/trigger")
async def trigger_heartbeat():
    """手动触发一次心跳检查"""
    try:
        if not Modules.dogtag_scheduler:
            raise HTTPException(400, "军牌调度器未初始化")

        await Modules.dogtag_scheduler.trigger_once("heartbeat")
        return {
            "success": True,
            "message": "心跳已触发",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手动触发 Heartbeat 失败: {e}")
        raise HTTPException(500, f"触发失败: {e}")


@app.get("/heartbeat/status")
async def get_heartbeat_status():
    """获取心跳系统运行状态"""
    try:
        from agentserver.dogtag import get_heartbeat_executor, get_dogtag_registry

        hb = get_heartbeat_executor()
        if not hb:
            return {
                "success": True,
                "running": False,
                "enabled": False,
                "message": "执行器未初始化",
            }

        status = hb.get_status()

        # 从军牌系统补充调度状态
        if Modules.dogtag_scheduler:
            registry = get_dogtag_registry()
            tag = registry.get("heartbeat")
            countdown_active = (
                "heartbeat" in Modules.dogtag_scheduler._event_countdowns
                and not Modules.dogtag_scheduler._event_countdowns["heartbeat"].done()
            )
            status["running"] = Modules.dogtag_scheduler._running
            status["conversation_active"] = Modules.dogtag_scheduler._conversation_active
            status["countdown_active"] = countdown_active
            status["duty_status"] = tag.status.value if tag else "unregistered"
            status["in_active_hours"] = Modules.dogtag_scheduler._is_in_active_hours(
                hb.config.active_hours_start, hb.config.active_hours_end
            )

        return {"success": True, **status}
    except Exception as e:
        logger.error(f"获取 Heartbeat 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


# ======================================================================
# Heartbeat Checklist CRUD 端点
# ======================================================================


@app.get("/heartbeat/checklist")
async def get_heartbeat_checklist(status: Optional[str] = None):
    """获取 checklist 条目列表，可选 ?status=pending 过滤"""
    try:
        from agentserver.dogtag import load_checklist

        cl = load_checklist()
        items = cl.items
        if status:
            items = [i for i in items if i.status == status]
        return {
            "success": True,
            "items": [i.model_dump() for i in items],
            "total": len(items),
        }
    except Exception as e:
        logger.error(f"获取 Checklist 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/heartbeat/checklist")
async def create_checklist_item(payload: Dict[str, Any]):
    """新增 checklist 条目 {"content": "...", "priority": "normal"}"""
    try:
        from agentserver.dogtag import add_item

        content = payload.get("content", "").strip()
        if not content:
            raise HTTPException(400, "content 不能为空")

        priority = payload.get("priority", "normal")
        item = add_item(content, source="user", priority=priority)
        return {"success": True, "item": item.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"新增 Checklist 条目失败: {e}")
        raise HTTPException(500, f"新增失败: {e}")


@app.put("/heartbeat/checklist/{item_id}")
async def update_checklist_item(item_id: str, payload: Dict[str, Any]):
    """更新 checklist 条目 {"status": "done", "notes": "..."}"""
    try:
        from agentserver.dogtag import update_item

        allowed_fields = {"status", "notes", "priority", "content"}
        updates = {k: v for k, v in payload.items() if k in allowed_fields}
        if not updates:
            raise HTTPException(400, "无有效更新字段")

        ok = update_item(item_id, **updates)
        if not ok:
            raise HTTPException(404, f"条目不存在: {item_id}")
        return {"success": True, "message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 Checklist 条目失败: {e}")
        raise HTTPException(500, f"更新失败: {e}")


@app.delete("/heartbeat/checklist/{item_id}")
async def delete_checklist_item(item_id: str):
    """删除 checklist 条目"""
    try:
        from agentserver.dogtag import remove_item

        ok = remove_item(item_id)
        if not ok:
            raise HTTPException(404, f"条目不存在: {item_id}")
        return {"success": True, "message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 Checklist 条目失败: {e}")
        raise HTTPException(500, f"删除失败: {e}")


# ======================================================================
# 军牌系统 (DogTag) 统一端点
# ======================================================================


@app.get("/dogtag/status")
async def get_dogtag_status():
    """获取军牌调度器状态 + 全部任务状态"""
    try:
        if not Modules.dogtag_scheduler:
            return {"success": True, "running": False, "message": "调度器未初始化"}
        return {"success": True, **Modules.dogtag_scheduler.get_status()}
    except Exception as e:
        logger.error(f"获取 DogTag 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/dogtag/duties")
async def get_dogtag_duties():
    """获取所有注册的职责列表"""
    try:
        from agentserver.dogtag import get_dogtag_registry

        registry = get_dogtag_registry()
        duties = {
            duty_id: tag.model_dump()
            for duty_id, tag in registry.get_all().items()
        }
        return {"success": True, "duties": duties, "count": len(duties)}
    except Exception as e:
        logger.error(f"获取 DogTag 职责列表失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/dogtag/duties/{duty_id}/enable")
async def enable_dogtag_duty(duty_id: str):
    """启用指定职责"""
    try:
        from agentserver.dogtag import get_dogtag_registry
        from agentserver.dogtag.models import DutyStatus

        registry = get_dogtag_registry()
        if not registry.get(duty_id):
            raise HTTPException(404, f"职责不存在: {duty_id}")
        registry.update_status(duty_id, DutyStatus.ENABLED)
        return {"success": True, "message": f"职责 '{duty_id}' 已启用"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启用 DogTag 职责失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


@app.post("/dogtag/duties/{duty_id}/disable")
async def disable_dogtag_duty(duty_id: str):
    """禁用指定职责"""
    try:
        from agentserver.dogtag import get_dogtag_registry
        from agentserver.dogtag.models import DutyStatus

        registry = get_dogtag_registry()
        if not registry.get(duty_id):
            raise HTTPException(404, f"职责不存在: {duty_id}")
        registry.update_status(duty_id, DutyStatus.DISABLED)
        return {"success": True, "message": f"职责 '{duty_id}' 已禁用"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"禁用 DogTag 职责失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


@app.post("/dogtag/duties/{duty_id}/trigger")
async def trigger_dogtag_duty(duty_id: str):
    """手动触发指定职责"""
    try:
        if not Modules.dogtag_scheduler:
            raise HTTPException(503, "军牌调度器未初始化")

        from agentserver.dogtag import get_dogtag_registry

        registry = get_dogtag_registry()
        if not registry.get(duty_id):
            raise HTTPException(404, f"职责不存在: {duty_id}")

        await Modules.dogtag_scheduler.trigger_once(duty_id)
        return {"success": True, "message": f"职责 '{duty_id}' 已触发"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"触发 DogTag 职责失败: {e}")
        raise HTTPException(500, f"触发失败: {e}")


@app.post("/dogtag/conversation_event")
async def dogtag_conversation_event(payload: Dict[str, Any]):
    """接收对话生命周期事件"""
    event = payload.get("event", "")
    try:
        if not Modules.dogtag_scheduler:
            return {"status": "no_scheduler"}

        if event == "started":
            Modules.dogtag_scheduler.on_conversation_started()
        elif event == "ended":
            Modules.dogtag_scheduler.on_conversation_ended()
        else:
            return {"status": "unknown_event", "event": event}

        logger.info(f"[DogTag] 收到对话事件: {event}")
        return {"status": "ok", "event": event}
    except Exception as e:
        logger.error(f"[DogTag] 处理对话事件失败: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    from agentserver.config import AGENT_SERVER_PORT

    uvicorn.run(app, host="0.0.0.0", port=AGENT_SERVER_PORT, access_log=False)
