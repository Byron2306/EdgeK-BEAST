#!/usr/bin/env python3
import subprocess
import json
import time
import sys

def test_mcp_server():
    # Start the MCP server
    proc = subprocess.Popen(
        ['beast', 'mcp'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0
    )
    
    try:
        # Give server time to start
        time.sleep(0.5)
        
        # Send initialize request
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
        proc.stdin.write(init_message)
        proc.stdin.flush()
        
        # Read response
        # First read headers
        headers = ""
        while True:
            char = proc.stdout.read(1)
            if char == '\r':
                # Peek next char
                next_char = proc.stdout.read(1)
                if next_char == '\n':
                    # Check for end of headers
                    peek = proc.stdout.read(1)
                    if peek == '\r':
                        proc.stdout.read(1)  # consume \n
                        break
                    else:
                        # Not end of headers, put back
                        proc.stdout = proc.stdout  # reset? Actually we need to handle this better
                        # Simpler approach: read line by line
                        break
                else:
                    headers += char + next_char
            elif char == '\n':
                if headers.endswith('\r\n'):
                    break
                headers += char
            else:
                headers += char
        
        # Actually, let's use a simpler approach - read lines
        proc.stdout = open(proc.stdout.fileno(), 'r', encoding='utf-8', buffering=1)
        
        # Read until we get empty line (end of headers)
        while True:
            line = proc.stdout.readline()
            if line == '\r\n' or line == '\n' or line == '':
                break
        
        # Now read Content-Length header from what we've seen
        # Let's restart with a cleaner approach
        
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    test_mcp_server()