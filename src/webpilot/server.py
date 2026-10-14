"""Daemon: relays commands from CLI/library clients to the connected browser extensions.

Protocol (JSON over WebSocket on 127.0.0.1):
  hello    -> {"type": "hello", "role": "client"|"extension", "token": ..., "mode": "real"|"temp", "profile": name}
  request  -> {"id", "cmd", "args", "mode", "profile", "timeout", "wait"}   (client -> daemon -> extension)

Each browser profile with the extension connects on its own, keyed by (mode, profile name). A request
without a profile goes to the only connected one; with several connected it must name one.
  response <- {"id", "ok", "result" | "error"}
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import time
import uuid

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

log = logging.getLogger("webpilot.daemon")

NOT_CONNECTED = {
    "real": "WebPilot extension (real browser) is not connected. Is Edge open with the extension "
    "loaded? See `webpilot setup` and `webpilot status`.",
    "temp": "Temporary browser is not connected. Run `webpilot temp start`.",
}
EXTENSION_ORIGINS = ("chrome-extension://", "extension://", "moz-extension://")
DUPLICATE_PROFILE = 4001  # close code: another connected extension already uses this profile name


class Daemon:
    def __init__(self, token: str, port: int):
        self.token = token
        self.port = port
        self.extensions: dict[str, dict[str, ServerConnection]] = {}  # mode -> profile -> socket
        self.ext_info: dict[str, dict[str, dict]] = {}
        self.ext_changed = asyncio.Condition()
        self.pending: dict[str, tuple[asyncio.Future, ServerConnection]] = {}
        self.stop_event = asyncio.Event()

    async def handler(self, ws: ServerConnection) -> None:
        # Web pages may open sockets to localhost; only extensions and non-browser clients get in.
        origin = ws.request.headers.get("Origin") if ws.request else None
        if origin and not origin.startswith(EXTENSION_ORIGINS):
            await ws.close(1008, "origin not allowed")
            return
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
        except (TimeoutError, ConnectionClosed, ValueError):
            return
        if hello.get("type") != "hello" or not hmac.compare_digest(str(hello.get("token", "")), self.token):
            await ws.close(1008, "bad token")
            return
        if hello.get("role") == "extension":
            await self.serve_extension(ws, hello)
        else:
            await self.serve_client(ws)

    async def serve_extension(self, ws: ServerConnection, hello: dict) -> None:
        mode = hello.get("mode") or "real"
        profile = str(hello.get("profile") or "default")
        if profile in self.extensions.get(mode, {}):
            # Refuse rather than replace, so two profiles with the same name cannot keep evicting each other.
            await ws.close(DUPLICATE_PROFILE, f"profile name {profile!r} already connected")
            return
        self.extensions.setdefault(mode, {})[profile] = ws
        self.ext_info.setdefault(mode, {})[profile] = {
            "version": hello.get("version"), "ua": hello.get("ua"), "since": time.time()}
        async with self.ext_changed:
            self.ext_changed.notify_all()
        log.info("extension connected: %s/%s", mode, profile)
        try:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await ws.send('{"type":"pong"}')
                    continue
                entry = self.pending.pop(msg.get("id"), None)
                if entry and not entry[0].done():
                    entry[0].set_result(msg)
        except ConnectionClosed:
            pass
        finally:
            if self.extensions.get(mode, {}).get(profile) is ws:
                del self.extensions[mode][profile]
                del self.ext_info[mode][profile]
                if not self.extensions[mode]:
                    del self.extensions[mode]
                    del self.ext_info[mode]
            for rid, (fut, owner) in list(self.pending.items()):
                if owner is ws and not fut.done():
                    fut.set_exception(RuntimeError("browser extension disconnected"))
                    self.pending.pop(rid, None)
            log.info("extension disconnected: %s/%s", mode, profile)

    async def serve_client(self, ws: ServerConnection) -> None:
        await ws.send(json.dumps({"type": "welcome"}))
        tasks: set[asyncio.Task] = set()
        try:
            async for raw in ws:
                task = asyncio.create_task(self.client_request(ws, json.loads(raw)))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        except ConnectionClosed:
            pass

    async def client_request(self, ws: ServerConnection, msg: dict) -> None:
        try:
            resp = {"id": msg.get("id"), "ok": True, "result": await self.dispatch(msg)}
        except Exception as e:  # noqa: BLE001 - every failure goes back to the client
            resp = {"id": msg.get("id"), "ok": False, "error": str(e) or type(e).__name__}
        try:
            await ws.send(json.dumps(resp))
        except ConnectionClosed:
            pass

    async def dispatch(self, msg: dict):
        cmd = msg.get("cmd")
        if cmd == "daemon.status":
            return {"pid": os.getpid(), "port": self.port, "extensions": self.ext_info}
        if cmd == "daemon.stop":
            asyncio.get_running_loop().call_later(0.2, self.stop_event.set)
            return {"stopping": True}

        ext = await self.find_extension(msg.get("mode") or "real", msg.get("profile"), float(msg.get("wait") or 0))

        rid = uuid.uuid4().hex
        fut = asyncio.get_running_loop().create_future()
        self.pending[rid] = (fut, ext)
        try:
            await ext.send(json.dumps({"id": rid, "cmd": cmd, "args": msg.get("args") or {}}))
            reply = await asyncio.wait_for(fut, float(msg.get("timeout") or 60))
        except TimeoutError:
            raise RuntimeError(f"timed out waiting for the browser ({cmd})") from None
        finally:
            self.pending.pop(rid, None)
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error") or "unknown browser error")
        return reply.get("result")

    async def find_extension(self, mode: str, profile: str | None, wait: float) -> ServerConnection:
        """The extension for this mode and profile, waiting up to `wait` seconds for it to connect."""

        def pick() -> ServerConnection | None:
            conns = self.extensions.get(mode, {})
            if profile:
                return conns.get(profile)
            return next(iter(conns.values())) if len(conns) == 1 else None

        def ambiguous() -> bool:
            return not profile and len(self.extensions.get(mode, {})) > 1

        if pick() is None and not ambiguous() and wait > 0:
            async with self.ext_changed:
                try:
                    await asyncio.wait_for(self.ext_changed.wait_for(lambda: pick() is not None or ambiguous()), wait)
                except TimeoutError:
                    pass
        if ext := pick():
            return ext
        names = ", ".join(sorted(self.extensions.get(mode, {})))
        if ambiguous():
            raise RuntimeError(f"several browser profiles are connected ({names}); choose one with --profile NAME "
                               "or WEBPILOT_PROFILE (see `webpilot profile list`)")
        if profile and names:
            raise RuntimeError(f"browser profile {profile!r} is not connected (connected: {names}); "
                               "see `webpilot profile list`")
        raise RuntimeError(NOT_CONNECTED.get(mode, f"no extension for mode {mode!r}"))

    async def run(self) -> None:
        async with serve(self.handler, "127.0.0.1", self.port, max_size=None):
            log.info("listening on ws://127.0.0.1:%d", self.port)
            await self.stop_event.wait()


def main(token: str, port: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(Daemon(token, port).run())
