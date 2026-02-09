#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 通信测试脚本 (Python 版)

使用方法:
    python agentserver/openclaw/test_connection.py
"""

import asyncio
import httpx
import os

# 确保 localhost 请求绕过代理
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

GATEWAY_URL = "http://127.0.0.1:18789"
GATEWAY_TOKEN = "9d3d8c24a1739f3a8a21653bbc218bc54f53ff1a5c5381de"
HOOKS_TOKEN = "testnagahook"

GATEWAY_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {GATEWAY_TOKEN}"
}

HOOKS_HEADERS = {
    "Content-Type": "application/json",
    "x-openclaw-token": HOOKS_TOKEN
}


async def test_root():
    """测试根路径"""
    print("\n[1] 测试 GET /")
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{GATEWAY_URL}/", headers=GATEWAY_HEADERS)
            print(f"    状态码: {r.status_code}")
            print(f"    响应: {r.text[:200] if r.text else '(空)'}")
        except Exception as e:
            print(f"    错误: {e}")


async def test_hooks_agent():
    """测试发送消息 POST /hooks/agent"""
    print("\n[2] 测试 POST /hooks/agent")
    payload = {
        "message": "你好，这是测试消息",
        "sessionKey": "naga:test",
        "name": "NagaTest"
    }

    # 尝试多种认证方式
    auth_methods = [
        ("Bearer token", {"Content-Type": "application/json", "Authorization": f"Bearer {HOOKS_TOKEN}"}),
        ("x-openclaw-token", {"Content-Type": "application/json", "x-openclaw-token": HOOKS_TOKEN}),
        ("query param", {"Content-Type": "application/json"}),
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        for name, headers in auth_methods:
            try:
                url = f"{GATEWAY_URL}/hooks/agent"
                if name == "query param":
                    url += f"?token={HOOKS_TOKEN}"
                r = await client.post(url, headers=headers, json=payload)
                print(f"    [{name}] 状态码: {r.status_code}")
                if r.status_code != 401:
                    print(f"    响应: {r.text[:300] if r.text else '(空)'}")
                    break
            except Exception as e:
                print(f"    [{name}] 错误: {e}")


async def test_hooks_wake():
    """测试触发事件 POST /hooks/wake"""
    print("\n[3] 测试 POST /hooks/wake")
    payload = {
        "text": "NagaAgent 测试事件",
        "mode": "now"
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(f"{GATEWAY_URL}/hooks/wake", headers=HOOKS_HEADERS, json=payload)
            print(f"    状态码: {r.status_code}")
            print(f"    响应: {r.text[:500] if r.text else '(空)'}")
        except Exception as e:
            print(f"    错误: {e}")


async def test_hooks_agent_sync_reply():
    """测试发送消息并等待 LLM 回复 POST /hooks/agent + 轮询 sessions_history"""
    print("\n[4] 测试 POST /hooks/agent (发送消息并获取回复)")
    session_key = f"naga:reply-test-{int(asyncio.get_event_loop().time())}"
    payload = {
        "message": "用一句话介绍你自己",
        "sessionKey": session_key,
        "name": "NagaReplyTest",
        "deliver": False,
        "timeoutSeconds": 60,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {HOOKS_TOKEN}",
    }

    print(f"    发送消息: {payload['message']}")
    print(f"    sessionKey: {session_key}")

    async with httpx.AsyncClient(timeout=90) as client:
        try:
            # Step 1: 发送消息
            r = await client.post(
                f"{GATEWAY_URL}/hooks/agent",
                headers=headers,
                json=payload,
            )
            print(f"    状态码: {r.status_code}")

            if r.status_code not in (200, 202):
                print(f"    ❌ 发送失败: {r.text[:300]}")
                return

            import json
            result = r.json()
            run_id = result.get("runId", "N/A")
            print(f"    runId: {run_id}")

            # 检查是否直接返回了回复 (status=ok + reply)
            if result.get("status") == "ok" and result.get("reply"):
                print(f"    ✅ 同步回复: {result['reply'][:300]}")
                return

            # Step 2: 轮询 sessions_history 等待回复
            print(f"    202 已接受，轮询等待 LLM 回复...")
            full_session_key = f"agent:main:{session_key}"

            for attempt in range(1, 16):  # 最多 15 次，约 45 秒
                await asyncio.sleep(3)
                try:
                    hr = await client.post(
                        f"{GATEWAY_URL}/tools/invoke",
                        headers=GATEWAY_HEADERS,
                        json={
                            "tool": "sessions_history",
                            "args": {"sessionKey": full_session_key, "limit": 3},
                        },
                        timeout=10,
                    )
                    if hr.status_code == 200:
                        data = hr.json()
                        details = data.get("result", {}).get("details", {})
                        messages = details.get("messages", [])

                        # 找最后一条 assistant 消息
                        for msg in reversed(messages):
                            if msg.get("role") != "assistant":
                                continue
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                texts = [
                                    item.get("text", "")
                                    for item in content
                                    if isinstance(item, dict) and item.get("type") == "text"
                                ]
                                if texts:
                                    reply = "\n".join(texts).strip()
                                    print(f"    ✅ 轮询第{attempt}次获取到回复:")
                                    print(f"    {reply[:500]}")
                                    return
                            elif isinstance(content, str) and content.strip():
                                print(f"    ✅ 轮询第{attempt}次获取到回复:")
                                print(f"    {content[:500]}")
                                return

                    print(f"    ... 轮询第{attempt}次，暂无回复")
                except Exception as e:
                    print(f"    ... 轮询第{attempt}次异常: {e}")

            print(f"    ⚠️  轮询超时，未获取到回复")

        except httpx.TimeoutException:
            print(f"    ❌ HTTP 超时")
        except Exception as e:
            print(f"    ❌ 错误: {e}")


async def test_tools_invoke():
    """测试工具调用 POST /tools/invoke"""
    print("\n[5] 测试 POST /tools/invoke")

    # 测试会话相关工具的详细返回
    tools_to_try = [
        ("sessions_list", {}),
        ("sessions_history", {"sessionKey": "agent:main:naga:test", "limit": 5}),
        ("session_status", {}),
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        for tool_name, args in tools_to_try:
            payload = {"tool": tool_name}
            if args:
                payload["args"] = args
            try:
                r = await client.post(
                    f"{GATEWAY_URL}/tools/invoke",
                    headers=GATEWAY_HEADERS,
                    json=payload
                )
                print(f"\n    [{tool_name}] 状态码: {r.status_code}")
                if r.status_code == 200:
                    import json
                    result = r.json()
                    print(f"    响应: {json.dumps(result, indent=2, ensure_ascii=False)[:800]}")
                else:
                    print(f"    错误: {r.text[:200]}")
            except Exception as e:
                print(f"    [{tool_name}] 错误: {e}")


async def main():
    print("=" * 50)
    print("OpenClaw 通信测试 (Python)")
    print(f"Gateway: {GATEWAY_URL}")
    print("=" * 50)

    await test_root()
    await test_hooks_agent_sync_reply()
    await test_hooks_agent()
    await test_hooks_wake()
    await test_tools_invoke()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
