import asyncio
import base64
import hashlib
import hmac
import inspect
import json
import os
import signal
import subprocess
import sys
import time

import httpx
import uvicorn
import websockets
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect

import supabase_backend


STREAMLIT_INTERNAL_PORT = int(os.getenv("STREAMLIT_INTERNAL_PORT", "8501"))
STREAMLIT_HOST = os.getenv("STREAMLIT_INTERNAL_HOST", "127.0.0.1")
STREAMLIT_HTTP_BASE = f"http://{STREAMLIT_HOST}:{STREAMLIT_INTERNAL_PORT}"
STREAMLIT_WS_BASE = f"ws://{STREAMLIT_HOST}:{STREAMLIT_INTERNAL_PORT}"

app = FastAPI(title="Sports Cave OS")
_streamlit_process = None


def verify_shopify_hmac(raw_body, hmac_header):
    secret = os.getenv("SHOPIFY_WEBHOOK_SECRET", "").strip()
    if not secret or not hmac_header:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    calculated = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(calculated, hmac_header.strip())


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "sports-cave-os"}


@app.post("/webhooks/shopify/orders-paid")
async def shopify_orders_paid_webhook(request: Request):
    raw_body = await request.body()
    if not verify_shopify_hmac(raw_body, request.headers.get("X-Shopify-Hmac-SHA256", "")):
        return Response("Invalid Shopify webhook signature.", status_code=401)
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except ValueError:
        return Response("Invalid JSON payload.", status_code=400)
    webhook_id = request.headers.get("X-Shopify-Webhook-Id") or request.headers.get("X-Shopify-Event-Id") or ""
    topic = request.headers.get("X-Shopify-Topic") or "orders/paid"
    try:
        result = supabase_backend.process_order_paid_webhook(payload, webhook_id, topic=topic)
    except Exception as error:
        supabase_backend.log_app_error(
            "shopify_webhook_failed",
            str(error),
            {"webhook_id": webhook_id, "topic": topic},
        )
        return Response("Webhook accepted but processing failed.", status_code=500)
    status = "duplicate" if result.get("duplicate") else "processed"
    return {"ok": True, "status": status, "assignments_created": result.get("assignments_created", 0)}


def _filtered_proxy_headers(headers):
    blocked = {
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def streamlit_http_proxy(path: str, request: Request):
    query = request.url.query
    target_url = f"{STREAMLIT_HTTP_BASE}/{path}"
    if query:
        target_url = f"{target_url}?{query}"
    body = await request.body()
    headers = _filtered_proxy_headers(request.headers)
    async with httpx.AsyncClient(timeout=None, follow_redirects=False) as client:
        upstream = await client.request(request.method, target_url, headers=headers, content=body)
    response_headers = _filtered_proxy_headers(upstream.headers)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


@app.websocket("/{path:path}")
async def streamlit_websocket_proxy(websocket: WebSocket, path: str):
    await websocket.accept()
    query = websocket.url.query
    target_url = f"{STREAMLIT_WS_BASE}/{path}"
    if query:
        target_url = f"{target_url}?{query}"
    header_pairs = [
        (key, value)
        for key, value in websocket.headers.items()
        if key.lower() not in {"host", "connection", "upgrade", "sec-websocket-key", "sec-websocket-version"}
    ]
    header_kwarg = (
        "additional_headers"
        if "additional_headers" in inspect.signature(websockets.connect).parameters
        else "extra_headers"
    )
    try:
        async with websockets.connect(target_url, **{header_kwarg: header_pairs}) as upstream:
            async def client_to_upstream():
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        await upstream.close()
                        break
                    if "text" in message:
                        await upstream.send(message["text"])
                    elif "bytes" in message:
                        await upstream.send(message["bytes"])

            async def upstream_to_client():
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            tasks = [
                asyncio.create_task(client_to_upstream()),
                asyncio.create_task(upstream_to_client()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


def start_streamlit():
    args = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        str(STREAMLIT_INTERNAL_PORT),
        "--server.address",
        STREAMLIT_HOST,
        "--server.headless",
        "true",
        "--server.enableCORS",
        "false",
        "--server.enableXsrfProtection",
        "false",
    ]
    env = os.environ.copy()
    env.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    return subprocess.Popen(args, env=env)


def stop_streamlit(process):
    if not process or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            process.send_signal(signal.SIGKILL)


if __name__ == "__main__":
    _streamlit_process = start_streamlit()
    try:
        time.sleep(float(os.getenv("STREAMLIT_BOOT_SECONDS", "2")))
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8500")))
    finally:
        stop_streamlit(_streamlit_process)
