#!/usr/bin/env python3
"""
Test script for Phase 2: Request-level box locking in Camisole.
Tests concurrent requests, error handling, and atomicity.
"""

import asyncio
import json
import aiohttp
import time

CAMISOLE_URL = "http://localhost:42920/run"

async def test_concurrent_same_box():
    """Test concurrent requests with same box_id - second should get BOX_BUSY."""
    print("Test 1: Concurrent requests with same box_id (expect 409)")
    
    payloads = [
        {"lang": "python", "source": "import time; time.sleep(3); print('Request 1')", "box_id": 0},
        {"lang": "python", "source": "print('Request 2')", "box_id": 0},
    ]
    
    async with aiohttp.ClientSession() as session:
        # Start both requests concurrently
        tasks = [session.post(CAMISOLE_URL, json=p) for p in payloads]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        for resp in responses:
            if isinstance(resp, Exception):
                print(f"  Exception: {resp}")
                continue
            result = await resp.json()
            results.append(result)
        
        # One should succeed, one should get BOX_BUSY
        success_count = sum(1 for r in results if r.get('success'))
        busy_count = sum(1 for r in results if r.get('error_code') == 'BOX_BUSY')
        
        print(f"  Successful: {success_count}")
        print(f"  BOX_BUSY: {busy_count}")
        print(f"  ✅ PASS" if busy_count == 1 and success_count == 1 else "  ❌ FAIL")
    print()

async def test_concurrent_different_boxes():
    """Test concurrent requests with different box_ids - both should succeed."""
    print("Test 2: Concurrent requests with different box_ids (both succeed)")
    
    payloads = [
        {"lang": "python", "source": "import time; time.sleep(2); print('Box 0')", "box_id": 0},
        {"lang": "python", "source": "import time; time.sleep(2); print('Box 1')", "box_id": 1},
    ]
    
    start = time.time()
    async with aiohttp.ClientSession() as session:
        tasks = [session.post(CAMISOLE_URL, json=p) for p in payloads]
        responses = await asyncio.gather(*tasks)
        
        results = [await resp.json() for resp in responses]
        duration = time.time() - start
        
        success_count = sum(1 for r in results if r.get('success'))
        
        print(f"  Successful: {success_count}/2")
        print(f"  Duration: {duration:.2f}s (should be ~2s, not ~4s)")
        print(f"  ✅ PASS" if success_count == 2 and duration < 3 else "  ❌ FAIL")
    print()

async def test_sequential_same_box():
    """Test sequential requests with same box_id - both should succeed."""
    print("Test 3: Sequential requests with same box_id (both succeed)")
    
    payload = {"lang": "python", "source": "print('Hello')", "box_id": 0}
    
    async with aiohttp.ClientSession() as session:
        # First request
        resp1 = await session.post(CAMISOLE_URL, json=payload)
        result1 = await resp1.json()
        
        # Second request (after first completes)
        resp2 = await session.post(CAMISOLE_URL, json=payload)
        result2 = await resp2.json()
        
        success_count = sum([result1.get('success'), result2.get('success')])
        
        print(f"  Request 1: {'✓' if result1.get('success') else '✗'}")
        print(f"  Request 2: {'✓' if result2.get('success') else '✗'}")
        print(f"  ✅ PASS" if success_count == 2 else "  ❌ FAIL")
    print()

async def test_compile_execute_atomicity():
    """Test that compile and execute use same box atomically."""
    print("Test 4: Compile + Execute atomicity with explicit box_id")
    
    payload = {
        "lang": "c",
        "source": "#include <stdio.h>\nint main() { printf(\"Compiled and executed\"); return 0; }",
        "box_id": 2,
        "tests": [{"stdin": ""}, {"stdin": ""}]  # Two test runs
    }
    
    async with aiohttp.ClientSession() as session:
        resp = await session.post(CAMISOLE_URL, json=payload)
        result = await resp.json()
        
        if result.get('success'):
            compile_status = result.get('compile', {}).get('meta', {}).get('status')
            test_count = len(result.get('tests', []))
            all_tests_ok = all(t.get('meta', {}).get('status') == 'OK' for t in result.get('tests', []))
            
            print(f"  Compile: {compile_status}")
            print(f"  Tests: {test_count} (all OK: {all_tests_ok})")
            print(f"  ✅ PASS" if compile_status == 'OK' and all_tests_ok else "  ❌ FAIL")
        else:
            print(f"  Error: {result.get('error')}")
            print(f"  ❌ FAIL")
    print()

async def test_auto_allocation():
    """Test backward compatibility - auto-allocation without box_id."""
    print("Test 5: Auto-allocation (no box_id) - backward compatibility")
    
    payload = {"lang": "python", "source": "print('Auto-allocated')"}
    
    async with aiohttp.ClientSession() as session:
        resp = await session.post(CAMISOLE_URL, json=payload)
        result = await resp.json()
        
        print(f"  Success: {result.get('success')}")
        if result.get('success'):
            stdout = result.get('tests', [{}])[0].get('stdout', b'').decode()
            print(f"  Output: {stdout.strip()}")
            print(f"  ✅ PASS")
        else:
            print(f"  Error: {result.get('error')}")
            print(f"  ❌ FAIL")
    print()

async def test_error_codes():
    """Test error code structure for worker retry logic."""
    print("Test 6: Error code structure (for worker retry)")
    
    # Start a long-running request
    payload1 = {"lang": "python", "source": "import time; time.sleep(10); print('Long')", "box_id": 0}
    payload2 = {"lang": "python", "source": "print('Quick')", "box_id": 0}
    
    async with aiohttp.ClientSession() as session:
        # Start long request
        task1 = asyncio.create_task(session.post(CAMISOLE_URL, json=payload1))
        
        # Wait a bit, then try to use same box
        await asyncio.sleep(0.5)
        resp2 = await session.post(CAMISOLE_URL, json=payload2)
        result2 = await resp2.json()
        
        # Cancel long request
        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass
        
        if result2.get('error_code') == 'BOX_BUSY':
            print(f"  Error code: {result2.get('error_code')} ✓")
            print(f"  Box ID: {result2.get('box_id')} ✓")
            print(f"  Error message: {result2.get('error')}")
            print(f"  ✅ PASS - Worker can retry with backoff")
        else:
            print(f"  Unexpected result: {result2}")
            print(f"  ❌ FAIL")
    print()

async def main():
    print("=" * 70)
    print("Camisole Phase 2: Request-Level Box Locking Tests")
    print("=" * 70)
    print()
    
    try:
        await test_concurrent_same_box()
        await test_concurrent_different_boxes()
        await test_sequential_same_box()
        await test_compile_execute_atomicity()
        await test_auto_allocation()
        await test_error_codes()
        
        print("=" * 70)
        print("All tests completed!")
        print("=" * 70)
    except aiohttp.ClientConnectorError:
        print("ERROR: Cannot connect to Camisole server at", CAMISOLE_URL)
        print("Make sure Camisole is running: python3 -m camisole serve")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
