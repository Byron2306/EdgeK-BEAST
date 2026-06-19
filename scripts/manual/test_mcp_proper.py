#!/usr/bin/env python3
"""
Test script to demonstrate MCP server communication with proper stdio protocol.
"""
import subprocess
import json
import time
import threading
import queue

def enqueue_output(out, queue):
    """Thread target to read lines from pipe and put them in queue."""
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()

def test_mcp_server():
    print("Starting EdgeK BEAST MCP server...")
    
    # Start the MCP server
    proc = subprocess.Popen(
        ['beast', 'mcp'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )
    
    # Set up queues to capture output
    stdout_q = queue.Queue()
    stderr_q = queue.Queue()
    
    stdout_thread = threading.Thread(target=enqueue_output, args=(proc.stdout, stdout_q))
    stderr_thread = threading.Thread(target=enqueue_output, args=(proc.stderr, stderr_q))
    
    stdout_thread.daemon = True
    stderr_thread.daemon = True
    stdout_thread.start()
    stderr_thread.start()
    
    try:
        # Give server time to start and show startup message
        time.sleep(1)
        
        # Check for any startup messages
        while not stderr_q.empty():
            line = stderr_q.get()
            print(f"STDERR: {line.decode('utf-8').rstrip()}")
        
        # Send initialize request
        print("\nSending initialize request...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "0.1.0"
                }
            }
        }
        
        init_json = json.dumps(init_request)
        init_message = f"Content-Length: {len(init_json)}\r\n\r\n{init_json}"
        print(f"Sending: {init_message}")
        proc.stdin.write(init_message.encode('utf-8'))
        proc.stdin.flush()
        
        # Wait for response
        time.sleep(0.5)
        
        # Read response
        response_data = b""
        # Simple approach: read until we have a complete message
        start_time = time.time()
        while time.time() - start_time < 2:  # 2 second timeout
            try:
                line = stdout_q.get_nowait()
                response_data += line
                # Try to parse as we go
                if b'\r\n\r\n' in response_data:
                    parts = response_data.split(b'\r\n\r\n', 1)
                    if len(parts) == 2:
                        headers, body = parts
                        # Parse Content-Length
                        for header in headers.decode('utf-8').split('\r\n'):
                            if header.lower().startswith('content-length:'):
                                length = int(header.split(':', 1)[1].strip())
                                if len(body) >= length:
                                    # We have the complete message
                                    response_json = json.loads(body[:length].decode('utf-8'))
                                    print(f"Received initialize response: {json.dumps(response_json, indent=2)}")
                                    break
            except queue.Empty:
                pass
            time.sleep(0.01)
        
        # Send initialized notification
        print("\nSending initialized notification...")
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        notif_json = json.dumps(init_notif)
        notif_message = f"Content-Length: {len(notif_json)}\r\n\r\n{notif_json}"
        print(f"Sending: {notif_message}")
        proc.stdin.write(notif_message.encode('utf-8'))
        proc.stdin.flush()
        
        time.sleep(0.5)
        
        # Send tools/list request
        print("\nSending tools/list request...")
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        tools_json = json.dumps(tools_request)
        tools_message = f"Content-Length: {len(tools_json)}\r\n\r\n{tools_json}"
        print(f"Sending: {tools_message}")
        proc.stdin.write(tools_message.encode('utf-8'))
        proc.stdin.flush()
        
        # Wait for response
        time.sleep(0.5)
        
        # Read tools/list response
        response_data = b""
        start_time = time.time()
        while time.time() - start_time < 2:
            try:
                line = stdout_q.get_nowait()
                response_data += line
                if b'\r\n\r\n' in response_data:
                    parts = response_data.split(b'\r\n\r\n', 1)
                    if len(parts) == 2:
                        headers, body = parts
                        for header in headers.decode('utf-8').split('\r\n'):
                            if header.lower().startswith('content-length:'):
                                length = int(header.split(':', 1)[1].strip())
                                if len(body) >= length:
                                    response_json = json.loads(body[:length].decode('utf-8'))
                                    print(f"Received tools/list response: {json.dumps(response_json, indent=2)}")
                                    # Check if we have the beast_prepare_task tool
                                    if 'result' in response_json and 'tools' in response_json['result']:
                                        tools = [t['name'] for t in response_json['result']['tools']]
                                        print(f"Available tools: {tools}")
                                        if 'beast_prepare_task' in tools:
                                            print("✓ beast_prepare_task tool is available!")
                                    break
            except queue.Empty:
                pass
            time.sleep(0.01)
        
        # Send beast_prepare_task call
        print("\nSending beast_prepare_task call...")
        prepare_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "beast_prepare_task",
                "arguments": {
                    "taskDescription": "Diagnose the Hugging Face provider route",
                    "context": {"provider": "huggingface"}
                }
            }
        }
        prepare_json = json.dumps(prepare_request)
        prepare_message = f"Content-Length: {len(prepare_json)}\r\n\r\n{prepare_json}"
        print(f"Sending: {prepare_message}")
        proc.stdin.write(prepare_message.encode('utf-8'))
        proc.stdin.flush()
        
        # Wait for response
        time.sleep(1)
        
        # Read prepare_task response
        response_data = b""
        start_time = time.time()
        while time.time() - start_time < 3:
            try:
                line = stdout_q.get_nowait()
                response_data += line
                if b'\r\n\r\n' in response_data:
                    parts = response_data.split(b'\r\n\r\n', 1)
                    if len(parts) == 2:
                        headers, body = parts
                        for header in headers.decode('utf-8').split('\r\n'):
                            if header.lower().startswith('content-length:'):
                                length = int(header.split(':', 1)[1].strip())
                                if len(body) >= length:
                                    response_json = json.loads(body[:length].decode('utf-8'))
                                    print(f"Received beast_prepare_task response: {json.dumps(response_json, indent=2)}")
                                    if 'result' in response_json:
                                        print("✓ Task envelope prepared successfully!")
                                    break
            except queue.Empty:
                pass
            time.sleep(0.01)
            
    finally:
        print("\nTerminating server...")
        proc.terminate()
        proc.wait(timeout=2)
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        print("Server terminated.")

if __name__ == "__main__":
    test_mcp_server()