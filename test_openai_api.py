#!/usr/bin/env python3
"""
Test script for the OpenAI-compatible API
"""

import asyncio
import aiohttp
import json
from config import config

async def test_openai_api():
    """Test the OpenAI-compatible API endpoints"""
    api_url = f"http://{config.api_server.host}:{config.api_server.port}"
    api_key = config.api.api_key
    
    # Headers with API key
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Test models endpoint
    print("Testing /v1/models endpoint...")
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{api_url}/v1/models", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"[PASS] Models endpoint working. Available models: {len(data.get('data', []))}")
            else:
                print(f"[FAIL] Models endpoint failed with status {resp.status}")
    
    # Test chat completions endpoint (non-streaming)
    print("\nTesting /v1/chat/completions (non-streaming)...")
    payload = {
        "model": config.api.model,
        "messages": [
            {"role": "user", "content": "Hello, who are you?"}
        ],
        "temperature": 0.7,
        "max_tokens": 100
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{api_url}/v1/chat/completions", 
                              headers=headers,
                              json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"[PASS] Chat completions (non-streaming) working")
                print(f"  Response: {data['choices'][0]['message']['content'][:100]}...")
            else:
                print(f"[FAIL] Chat completions (non-streaming) failed with status {resp.status}")
    
    # Test chat completions endpoint (streaming)
    print("\nTesting /v1/chat/completions (streaming)...")
    payload["stream"] = True
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{api_url}/v1/chat/completions",
                              headers=headers,
                              json=payload) as resp:
            if resp.status == 200:
                print("[PASS] Chat completions (streaming) working")
                print("  Streaming response:")
                async for line in resp.content:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        data_str = line_str[6:].strip()
                        if data_str != "[DONE]":
                            try:
                                data = json.loads(data_str)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        print(f"    {content}", end="", flush=True)
                            except json.JSONDecodeError:
                                pass
                print("\n  Streaming completed")
            else:
                print(f"[FAIL] Chat completions (streaming) failed with status {resp.status}")

if __name__ == "__main__":
    print("Testing NagaAgent OpenAI-Compatible API")
    print("=" * 40)
    asyncio.run(test_openai_api())
    print("\n" + "=" * 40)
    print("API testing completed")