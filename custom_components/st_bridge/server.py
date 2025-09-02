from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from .const import LOGGER

JsonObj = dict[str, Any]
GetEntitiesCB = Callable[[], list[JsonObj]]
CallServiceCB = Callable[[str, str, dict[str, Any]], asyncio.Future | None]

class BridgeServer:
    """TCP server for st-bridge protocol."""

    def __init__(self, hass, port: int, token: str, get_entities: GetEntitiesCB, call_service: CallServiceCB) -> None:
        """Initialize the BridgeServer."""
        self._hass = hass
        self._port = port
        self._token = token
        self._get = get_entities
        self._call = call_service
        self._server: asyncio.base_events.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the ST Bridge server."""
        self._server = await asyncio.start_server(self._handle, "0.0.0.0", self._port)
        LOGGER.info("ST Bridge TCP server listening on %d", self._port)

    async def async_close(self) -> None:
        """Close the ST Bridge server."""
        async with self._lock:
            for w in list(self._clients):
                try: 
                    w.close()
                except Exception: 
                    pass
            self._clients.clear()
        if self._server:
            self._server.close()
            try: 
                await self._server.wait_closed()
            except Exception: 
                pass
            self._server = None

    async def broadcast(self, obj: JsonObj) -> None:
        """Broadcast a message to all connected clients."""
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        async with self._lock:
            for w in list(self._clients):
                try:
                    w.write(data)
                    await w.drain()
                except Exception:
                    self._clients.discard(w)

    async def broadcast_entity_list(self, entities: list[JsonObj]) -> None:
        """Broadcast the current entity list to all connected clients."""
        await self.broadcast({"type":"entity_list","entities": entities})

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle a new client connection."""
        peer = writer.get_extra_info("peername")
        LOGGER.info("Client connected: %s", peer)
        await self._send(writer, {"type":"hello","bridge":"st-bridge","version":"1.1","token_required":True})
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=30)
        except asyncio.TimeoutError:
            writer.close()
            await writer.wait_closed()
            return
        if not line: 
            writer.close()
            await writer.wait_closed()
            return
        try:
            msg = json.loads(line.decode().strip() or "{}")
        except Exception:
            await self._send(writer, {"type":"error","code":"bad_json"})
            writer.close()
            await writer.wait_closed()
            return
        if msg.get("type")!="auth" or msg.get("token")!=self._token:
            await self._send(writer, {"type":"error","code":"unauthorized"})
            writer.close()
            await writer.wait_closed()
            return
        await self._send(writer, {"type":"auth_ok"})
        async with self._lock: 
            self._clients.add(writer)
        await self._send(writer, {"type":"entity_list","entities": self._get()})
        try:
            buf = b""
            while not reader.at_eof():
                chunk = await reader.read(1024)
                if not chunk:
                    await asyncio.sleep(0.05)
                    continue
                buf += chunk
                while True:
                    nl = buf.find(b"\n")
                    if nl < 0: 
                        break
                    line = buf[:nl].decode(errors="ignore").strip() # type: ignore
                    buf = buf[nl+1:]
                    if not line: 
                        continue
                    await self._on_line(writer, line)
        finally:
            async with self._lock: 
                self._clients.discard(writer)
            try: 
                writer.close()
                await writer.wait_closed()
            except Exception: 
                pass
            LOGGER.info("Client disconnected: %s", peer)

    async def _on_line(self, writer: asyncio.StreamWriter, line: str) -> None:
        """Handle a line of input from a client."""
        try:
            msg = json.loads(line)
        except Exception:
            await self._send(writer, {"type":"error","code":"bad_json"})
            return
        t = msg.get("type")
        if t=="ping": 
            await self._send(writer, {"type":"pong"})
            return
        if t=="command":
            ent = msg.get("entity_id")
            cmd = msg.get("command")
            args = msg.get("args",{}) or {}
            if isinstance(ent,str) and isinstance(cmd,str):
                await self._call(ent, cmd, args) # type: ignore
            else:
                await self._send(writer, {"type":"error","code":"bad_command"})
            return

    async def _send(self, writer: asyncio.StreamWriter, obj: JsonObj) -> None:
        """Send a JSON object to a client."""
        try:
            writer.write((json.dumps(obj, ensure_ascii=False)+"\n").encode())
            await writer.drain()
        except Exception: 
            pass
