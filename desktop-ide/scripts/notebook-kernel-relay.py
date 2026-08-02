#!/usr/bin/env python3
"""Persistent, JSON-lines Jupyter kernel relay for the BEAST desktop host."""

import json
import os
import sys
import time

from jupyter_client import KernelManager


MAX_OUTPUT = 256 * 1024


def emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def compact(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[-MAX_OUTPUT:]


def output_from(message):
    content = message.get("content", {})
    kind = message.get("msg_type", "output")
    if kind == "stream":
        return {"output_type": "stream", "type": "stream", "name": content.get("name", "stdout"), "text": compact(content.get("text", ""))}
    if kind in {"display_data", "execute_result"}:
        data = content.get("data", {})
        output = {"output_type": kind, "type": kind, "text": compact(data.get("text/plain", data)), "data": data, "metadata": content.get("metadata", {})}
        if kind == "execute_result":
            output["execution_count"] = content.get("execution_count")
        return output
    if kind == "error":
        return {"output_type": "error", "type": "error", "ename": content.get("ename", "Error"), "evalue": content.get("evalue", ""), "traceback": content.get("traceback", [])[-12:]}
    return None


def execute(client, code, timeout):
    message_id = client.execute(code, store_history=True, allow_stdin=False)
    deadline = time.monotonic() + timeout
    outputs = []
    errored = False
    execution_count = None
    while time.monotonic() < deadline:
        message = client.get_iopub_msg(timeout=max(0.1, deadline - time.monotonic()))
        if message.get("parent_header", {}).get("msg_id") != message_id:
            continue
        if message.get("msg_type") == "execute_input":
            execution_count = message.get("content", {}).get("execution_count")
        output = output_from(message)
        if output:
            outputs.append(output)
            errored = errored or output["type"] == "error"
        if message.get("msg_type") == "status" and message.get("content", {}).get("execution_state") == "idle":
            return {"ok": not errored, "outputs": outputs, "execution_count": execution_count}
    return {"ok": False, "outputs": outputs, "error": f"Kernel cell timed out after {timeout}s", "execution_count": execution_count}


def main():
    workspace = os.environ.get("BEAST_ACTIVE_WORKSPACE") or None
    manager = KernelManager(kernel_name=os.environ.get("BEAST_JUPYTER_KERNEL", "beast-python"))
    manager.start_kernel(cwd=workspace)
    client = manager.client()
    client.start_channels()
    client.wait_for_ready(timeout=20)
    emit({"type": "ready", "kernel": manager.kernel_name, "pid": manager.provisioner.pid})
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                request_id = request.get("id")
                operation = request.get("operation")
                if operation == "execute":
                    code = str(request.get("code", ""))
                    timeout = max(1, min(float(request.get("timeout", 30)), 120))
                    response = execute(client, code, timeout)
                elif operation == "status":
                    response = {"ok": True, "kernel": manager.kernel_name}
                elif operation == "shutdown":
                    emit({"id": request_id, "ok": True, "stopped": True})
                    return
                else:
                    response = {"ok": False, "error": "unsupported kernel operation"}
                emit({"id": request_id, **response})
            except Exception as error:
                emit({"id": request.get("id") if "request" in locals() else None, "ok": False, "error": str(error)})
    finally:
        client.stop_channels()
        manager.shutdown_kernel(now=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit({"type": "fatal", "error": str(error)})
        raise
