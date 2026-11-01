#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端冒烟测试：
1. 复用已运行后端，若未运行则启动 `main.py --headless`
2. 等待 API / Agent Server 就绪
3. 验证未登录可用路径；提供账号时额外验证登录、鉴权路径
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE = "http://127.0.0.1:8000"
DEFAULT_AGENT_BASE = "http://127.0.0.1:8001"


def log(message: str) -> None:
    print(f"[smoke] {message}", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NagaAgent backend smoke test")
    parser.add_argument(
        "--username",
        default=os.environ.get("NAGA_SMOKE_USERNAME", ""),
        help="登录用户名；也可通过 NAGA_SMOKE_USERNAME 提供",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("NAGA_SMOKE_PASSWORD", ""),
        help="登录密码；也可通过 NAGA_SMOKE_PASSWORD 提供",
    )
    parser.add_argument(
        "--skip-auth",
        action="store_true",
        help="跳过验证码、登录和 /auth/me 已登录检查，只验证未登录本地路径",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API server base URL")
    parser.add_argument("--agent-base", default=DEFAULT_AGENT_BASE, help="Agent server base URL")
    parser.add_argument("--timeout", type=float, default=120.0, help="启动等待超时（秒）")
    parser.add_argument(
        "--start-if-needed",
        action="store_true",
        help="如果 8000/8001 未就绪，则自动启动本地后端",
    )
    parser.add_argument(
        "--python",
        default=str(PROJECT_ROOT / ".venv" / "bin" / "python"),
        help="启动后端使用的 Python 解释器",
    )
    args = parser.parse_args()
    if not args.skip_auth and (not args.username or not args.password):
        parser.error("未指定 --skip-auth 时必须提供 --username/--password 或 NAGA_SMOKE_USERNAME/NAGA_SMOKE_PASSWORD")
    return args


def request_json(method: str, url: str, *, expected: int = 200, **kwargs) -> Any:
    resp = requests.request(method, url, timeout=20, **kwargs)
    if resp.status_code != expected:
        raise RuntimeError(f"{method} {url} -> {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"{method} {url} returned non-JSON body: {resp.text[:500]}") from exc


def wait_health(url: str, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error = "unknown"
    log(f"等待健康检查: {url}")
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                log(f"健康检查通过: {url}")
                return
            last_error = f"status={resp.status_code} body={resp.text[:200]}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1.0)
    raise TimeoutError(f"等待健康检查超时: {url}, last_error={last_error}")


def solve_captcha(question: str) -> str:
    text = question.strip()
    match = re.search(r"(-?\d+)\s*([+\-*/xX×÷])\s*(-?\d+)", text)
    if not match:
        raise ValueError(f"无法解析验证码题目: {question}")
    left = int(match.group(1))
    op = match.group(2)
    right = int(match.group(3))
    if op == "+":
        value = left + right
    elif op == "-":
        value = left - right
    elif op in {"*", "x", "X", "×"}:
        value = left * right
    elif op in {"/", "÷"}:
        if right == 0:
            raise ValueError(f"验证码除数为 0: {question}")
        value = left // right
    else:
        raise ValueError(f"不支持的验证码运算符: {question}")
    return str(value)


def ensure_backend(args: argparse.Namespace) -> tuple[Optional[subprocess.Popen[str]], Optional[Path]]:
    api_health = f"{args.api_base}/health"
    agent_health = f"{args.agent_base}/health"

    try:
        wait_health(api_health, 2.0)
        wait_health(agent_health, 2.0)
        log("检测到现有后端，复用运行中实例")
        return None, None
    except Exception:
        if not args.start_if_needed:
            raise

    log_dir = Path(tempfile.mkdtemp(prefix="naga-smoke-"))
    log_path = log_dir / "backend.log"
    log_fp = open(log_path, "w", encoding="utf-8")
    cmd = [args.python, "main.py", "--headless"]
    log(f"启动本地后端: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid if sys.platform != "win32" else None,
    )

    try:
        wait_health(api_health, args.timeout)
        wait_health(agent_health, args.timeout)
        log(f"本地后端启动完成，日志: {log_path}")
        return proc, log_path
    except Exception:
        stop_backend(proc)
        raise


def stop_backend(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            proc.send_signal(signal.SIGTERM)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=10)
    except Exception:
        try:
            if sys.platform == "win32":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass


def run_smoke(args: argparse.Namespace) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "api_base": args.api_base,
        "agent_base": args.agent_base,
        "checks": {},
    }

    api_health = request_json("GET", f"{args.api_base}/health")
    agent_health = request_json("GET", f"{args.agent_base}/health")
    summary["checks"]["api_health"] = api_health
    summary["checks"]["agent_health"] = agent_health

    summary["checks"]["tool_status"] = request_json("GET", f"{args.api_base}/tool_status")
    summary["checks"]["auth_me_unauthenticated"] = request_json(
        "GET",
        f"{args.api_base}/auth/me",
        expected=401,
    )
    summary["checks"]["system_config"] = request_json("GET", f"{args.api_base}/system/config")
    summary["checks"]["characters"] = request_json("GET", f"{args.api_base}/system/characters")
    summary["checks"]["tasks_proxy"] = request_json("GET", f"{args.api_base}/openclaw/tasks")
    summary["checks"]["tasks_direct"] = request_json("GET", f"{args.agent_base}/openclaw/tasks")

    tool_notification = request_json(
        "POST",
        f"{args.api_base}/tool_notification",
        expected=400,
        json={"stage": "executing"},
    )
    summary["checks"]["tool_notification_missing_session"] = tool_notification
    request_json(
        "POST",
        f"{args.api_base}/tool_notification",
        json={
            "session_id": "smoke-session",
            "stage": "executing",
            "tool_calls": [{"service_name": "smoke", "tool_name": "ping", "status": "ok"}],
        },
    )
    summary["checks"]["tool_status_visible"] = request_json("GET", f"{args.api_base}/tool_status")
    request_json(
        "POST",
        f"{args.api_base}/tool_notification",
        json={"session_id": "smoke-session", "stage": "hide"},
    )
    summary["checks"]["tool_status_hidden"] = request_json("GET", f"{args.api_base}/tool_status")

    request_json(
        "POST",
        f"{args.api_base}/ui_notification",
        json={
            "action": "show_mcp_result",
            "results": [
                {
                    "service_name": "smoke",
                    "tool_name": "ping",
                    "status": "ok",
                    "result": {"message": "pong"},
                }
            ],
        },
    )
    summary["checks"]["clawdbot_replies"] = request_json("GET", f"{args.api_base}/clawdbot/replies")

    request_json(
        "POST",
        f"{args.api_base}/ui_notification",
        json={"action": "live2d_action", "action_name": "wave"},
    )
    summary["checks"]["live2d_actions"] = request_json("GET", f"{args.api_base}/live2d/actions")

    request_json(
        "POST",
        f"{args.api_base}/ui_notification",
        json={"action": "music_control", "music_action": "play", "track": "smoke"},
    )
    summary["checks"]["music_commands"] = request_json("GET", f"{args.api_base}/music/commands")

    request_json(
        "POST",
        f"{args.api_base}/queue/push",
        json={"source": "heartbeat", "content": "smoke-heartbeat"},
    )
    summary["checks"]["heartbeat_replies"] = request_json("GET", f"{args.api_base}/clawdbot/replies")

    config_body = summary["checks"]["system_config"]
    config_data = config_body.get("config", {}) if isinstance(config_body, dict) else {}
    api_config = config_data.get("api", {}) if isinstance(config_data, dict) else {}
    api_key = str(api_config.get("api_key") or "").strip()
    base_url = str(api_config.get("base_url") or "").strip().rstrip("/")
    if base_url == "https://api.deepseek.com/v1" and api_key in {"", "your-api-key-here", "sk-placeholder-key-not-set"}:
        summary["checks"]["local_placeholder_completion"] = request_json(
            "POST",
            f"{args.api_base}/v1/chat/completions",
            expected=400,
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}]},
        )
    else:
        summary["checks"]["local_placeholder_completion"] = {
            "skipped": True,
            "reason": "运行时配置不是默认占位本地模型配置，避免误打真实上游模型",
        }

    if args.skip_auth:
        summary["checks"]["login"] = {"skipped": True, "reason": "--skip-auth"}
        return summary

    captcha = request_json("GET", f"{args.api_base}/auth/captcha")
    captcha_id = captcha.get("captchaId") or captcha.get("captcha_id")
    question = captcha.get("question", "")
    if not captcha_id or not question:
        raise RuntimeError(f"验证码响应异常: {captcha}")

    captcha_answer = solve_captcha(question)
    log(f"验证码解析成功: {question} = {captcha_answer}")
    login_payload = {
        "username": args.username,
        "password": args.password,
        "captcha_id": captcha_id,
        "captcha_answer": captcha_answer,
    }
    login_result = request_json("POST", f"{args.api_base}/auth/login", json=login_payload)
    access_token = login_result.get("access_token") or login_result.get("accessToken")
    if not access_token:
        raise RuntimeError(f"登录响应缺少 access_token: {login_result}")
    summary["checks"]["login"] = {
        "success": bool(login_result.get("success")),
        "user": login_result.get("user"),
    }

    me_result = request_json(
        "GET",
        f"{args.api_base}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    summary["checks"]["auth_me"] = {
        "user": me_result.get("user"),
        "memory_url": me_result.get("memory_url"),
        "has_access_token": bool(me_result.get("access_token")),
    }
    return summary


def main() -> int:
    args = parse_args()
    proc: Optional[subprocess.Popen[str]] = None
    log_path: Optional[Path] = None

    try:
        proc, log_path = ensure_backend(args)
        result = run_smoke(args)
        result["started_backend"] = proc is not None
        if log_path:
            result["backend_log"] = str(log_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        error: Dict[str, Any] = {"ok": False, "error": str(exc)}
        if log_path and log_path.exists():
            try:
                error["backend_log"] = str(log_path)
                error["backend_log_tail"] = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
            except Exception:
                pass
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 1
    finally:
        if proc is not None:
            stop_backend(proc)


if __name__ == "__main__":
    raise SystemExit(main())
