#!/usr/bin/env python3
"""
Test script for basic box_id functionality in Camisole.
Tests both explicit box_id and auto-allocation modes.
"""

import asyncio
import json
import aiohttp

CAMISOLE_URL = "http://localhost:42920/run"

async def test_explicit_box_id():
    """Test with explicit box_id parameter."""
    print("Test 1: Explicit box_id=0")
    
    payload = {
        "lang": "python",
        "source": "print('Hello from box 0')",
        "box_id": 0
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(CAMISOLE_URL, json=payload) as resp:
            result = await resp.json()
            print(f"  Status: {resp.status}")
            print(f"  Success: {result.get('success')}")
            if result.get('success'):
                stdout = result.get('tests', [{}])[0].get('stdout', b'').decode()
                print(f"  Output: {stdout.strip()}")
            else:
                print(f"  Error: {result.get('error')}")
    print()

async def test_auto_allocation():
    """Test without box_id (auto-allocation)."""
    print("Test 2: Auto-allocation (no box_id)")
    
    payload = {
        "lang": "python",
        "source": "print('Hello from auto-allocated box')"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(CAMISOLE_URL, json=payload) as resp:
            result = await resp.json()
            print(f"  Status: {resp.status}")
            print(f"  Success: {result.get('success')}")
            if result.get('success'):
                stdout = result.get('tests', [{}])[0].get('stdout', b'').decode()
                print(f"  Output: {stdout.strip()}")
            else:
                print(f"  Error: {result.get('error')}")
    print()

async def test_different_boxes():
    """Test concurrent requests with different box_ids."""
    print("Test 3: Concurrent requests with different box_ids")
    
    payloads = [
        {"lang": "python", "source": "print('Box 0')", "box_id": 0},
        {"lang": "python", "source": "print('Box 1')", "box_id": 1},
    ]
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, payload in enumerate(payloads):
            task = session.post(CAMISOLE_URL, json=payload)
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        
        for i, resp in enumerate(responses):
            result = await resp.json()
            print(f"  Request {i} (box_id={payloads[i]['box_id']}): Success={result.get('success')}")
            if result.get('success'):
                stdout = result.get('tests', [{}])[0].get('stdout', b'').decode()
                print(f"    Output: {stdout.strip()}")
    print()

async def test_compile_execute_same_box():
    """Test that compile and execute use the same box."""
    print("Test 4: Compile + Execute with explicit box_id")
    
    payload = {
        "lang": "c",
        "source": "#include <stdio.h>\nint main() { printf(\"Compiled in box 2\"); return 0; }",
        "box_id": 2
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(CAMISOLE_URL, json=payload) as resp:
            result = await resp.json()
            print(f"  Status: {resp.status}")
            print(f"  Success: {result.get('success')}")
            if result.get('success'):
                compile_status = result.get('compile', {}).get('meta', {}).get('status')
                print(f"  Compile status: {compile_status}")
                stdout = result.get('tests', [{}])[0].get('stdout', b'').decode()
                print(f"  Output: {stdout.strip()}")
            else:
                print(f"  Error: {result.get('error')}")
    print()

async def main():
    print("=" * 60)
    print("Camisole box_id Implementation Tests")
    print("=" * 60)
    print()
    
    try:
        await test_explicit_box_id()
        await test_auto_allocation()
        await test_different_boxes()
        await test_compile_execute_same_box()
        
        print("=" * 60)
        print("All tests completed!")
        print("=" * 60)
    except aiohttp.ClientConnectorError:
        print("ERROR: Cannot connect to Camisole server at", CAMISOLE_URL)
        print("Make sure Camisole is running: python3 -m camisole serve")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
