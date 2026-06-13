"""
Test script for EdgeK BEAST Gateway
Phase 1: Minimal Gateway Implementation
"""

import asyncio
import httpx
import json
from typing import Dict, Any
import pytest

@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_health_endpoint():
    """Test the health check endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/health")
        print(f"Health check: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200

@pytest.mark.asyncio
async def test_root_endpoint():
    """Test the root endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/")
        print(f"Root endpoint: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200

@pytest.mark.asyncio
async def test_openai_models():
    """Test OpenAI models endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/v1/models")
        print(f"OpenAI models: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200

@pytest.mark.asyncio
async def test_openai_chat_completion():
    """Test OpenAI chat completion endpoint"""
    async with httpx.AsyncClient() as client:
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello, EdgeK BEAST!"}
            ],
            "max_tokens": 50
        }
        response = await client.post(
            "http://localhost:8000/v1/chat/completions",
            json=payload
        )
        print(f"OpenAI chat completion: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200

@pytest.mark.asyncio
async def test_anthropic_message():
    """Test Anthropic message endpoint"""
    async with httpx.AsyncClient() as client:
        payload = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 100,
            "messages": [
                {"role": "user", "content": "Hello, EdgeK BEAST!"}
            ]
        }
        response = await client.post(
            "http://localhost:8000/v1/messages",
            json=payload
        )
        print(f"Anthropic message: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200

async def run_all_tests():
    """Run all tests"""
    print("Starting EdgeK BEAST Gateway tests...\n")
    
    tests = [
        test_health_endpoint,
        test_root_endpoint,
        test_openai_models,
        test_openai_chat_completion,
        test_anthropic_message
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
            print(f"✓ {test.__name__}: {'PASS' if result else 'FAIL'}\n")
        except Exception as e:
            print(f"✗ {test.__name__}: ERROR - {e}\n")
            results.append(False)
    
    passed = sum(results)
    total = len(results)
    print(f"Tests completed: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed.")
        return False

if __name__ == "__main__":
    asyncio.run(run_all_tests())