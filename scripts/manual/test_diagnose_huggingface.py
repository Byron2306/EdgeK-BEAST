#!/usr/bin/env python3
"""Test script to diagnose the Hugging Face provider route using BEAST MCP stdio server."""

import json
import subprocess
import sys
import time

def main():
    print("Starting EdgeK BEAST MCP server for Hugging Face diagnosis...")
    
    # Start the MCP server as a subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp.stdio_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,  # We'll handle bytes
        bufsize=0
    )
    
    def send_request(request_dict):
        """Send a JSON-RPC request with Content-Length header."""
        request_json = json.dumps(request_dict)
        request_bytes = request_json.encode('utf-8')
        header = f"Content-Length: {len(request_bytes)}\r\n\r\n".encode('ascii')
        proc.stdin.write(header + request_bytes)
        proc.stdin.flush()
        
        # Read response
        # Read headers
        headers = {}
        while True:
            line = proc.stdout.readline()
            if line == b'\r\n' or line == b'\n':
                break
            if line:
                key, value = line.decode('utf-8').split(':', 1)
                headers[key.strip().lower()] = value.strip()
        
        # Read body
        length = int(headers.get('content-length', '0'))
        if length > 0:
            body = proc.stdout.read(length)
            return json.loads(body.decode('utf-8'))
        return None

    try:
        # Send initialize request
        print("Sending initialize request...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "diagnosis-client", "version": "0.1.0"}
            }
        }
        init_response = send_request(init_request)
        print(f"Initialize response: {json.dumps(init_response, indent=2)}")
        
        # Send initialized notification
        print("Sending initialized notification...")
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        # Notifications don't have an id and we don't expect a response
        request_json = json.dumps(initialized_notification)
        request_bytes = request_json.encode('utf-8')
        header = f"Content-Length: {len(request_bytes)}\r\n\r\n".encode('ascii')
        proc.stdin.write(header + request_bytes)
        proc.stdin.flush()
        
        # Send tools/list to see available tools
        print("Sending tools/list request...")
        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        list_response = send_request(list_request)
        print(f"Tools/list response: {json.dumps(list_response, indent=2)}")
        
        # Call beast_prepare_task to diagnose Hugging Face provider route
        print("Calling beast_prepare_task for Hugging Face provider route diagnosis...")
        prepare_task_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "beast_prepare_task",
                "arguments": {
                    "user_request": "Diagnose the Hugging Face provider route",
                    "provider": "huggingface",
                    "task_class": "diagnosis",
                    "project": "edgek-beast",
                    "dry_run": True
                }
            }
        }
        prepare_task_response = send_request(prepare_task_request)
        print(f"Beast prepare task response: {json.dumps(prepare_task_response, indent=2)}")
        
        # Extract the task envelope from the response
        if prepare_task_response and "result" in prepare_task_response:
            # The result is a list of content objects, we need the text
            content = prepare_task_response["result"]["content"]
            if content and len(content) > 0 and content[0]["type"] == "text":
                task_envelope_text = content[0]["text"]
                print("\n=== Task Envelope for Hugging Face Provider Diagnosis ===")
                print(task_envelope_text)
                print("=" * 60)
                
                # Optionally, we could parse the task envelope and use it for further steps
                # For example, build a route card or run quality cascade
                # But for now, we just show the envelope as requested.
        
    finally:
        # Terminate the server
        print("Terminating server...")
        proc.terminate()
        proc.wait(timeout=5)
        print("Server terminated.")

if __name__ == "__main__":
    main()