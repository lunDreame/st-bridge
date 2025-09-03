from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Optional

from .const import LOGGER

JsonObj = dict[str, Any]
GetEntitiesCB = Callable[[], list[JsonObj]]
GetStateMsgsCB = Callable[[], list[JsonObj]]
CallServiceCB = Callable[[str, str, dict[str, Any]], asyncio.Future | None]

class BridgeServer:
    """TCP server for st-bridge protocol."""

    def __init__(
        self,
        hass,
        port: int,
        get_entities: GetEntitiesCB,
        call_service: CallServiceCB,
        get_state_messages: Optional[GetStateMsgsCB] = None,
    ) -> None:
        """Initialize the BridgeServer."""
        self._hass = hass
        self._port = port
        self._get = get_entities
        self._call = call_service
        self._get_states = get_state_messages
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
        #LOGGER.info("Client connected: %s", peer)

        async with self._lock: 
            self._clients.add(writer)
        await self._send(writer, {"type":"hello","bridge":"st-bridge","version":"0.0.4"})
        await self._send(writer, {"type":"entity_list","entities": self._get()})
        if self._get_states:
            try:
                await asyncio.sleep(0.8)
                for msg in self._get_states():
                    await self._safe_send(writer, msg)
            except Exception:
                pass

        buffer = b""
        try:
            while not reader.at_eof():
                try:
                    chunk = await reader.read(1024)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    break
                except Exception as e:
                    LOGGER.debug("Read error from %s: %r", peer, e)
                    break

                if not chunk:
                    break

                buffer += chunk
                while True:
                    nl = buffer.find(b"\n")
                    if nl < 0:
                        break
                    line = buffer[:nl].decode(errors="ignore").strip()
                    buffer = buffer[nl + 1 :]
                    if not line:
                        continue
                    await self._on_line(writer, line)
        finally:
            await self._safe_close(writer, peer)

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

    async def _safe_send(self, writer: asyncio.StreamWriter, obj: JsonObj) -> None:
        """Send a JSON object to a client, ignoring errors."""
        try:
            writer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
            await writer.drain()
        except Exception:
            pass

    async def _safe_close(self, writer: asyncio.StreamWriter, peer) -> None:
        """Close the connection to a client, ignoring errors."""
        async with self._lock:
            self._clients.discard(writer)
        try:
            writer.close()
        except Exception:
            pass
        try:
            if hasattr(writer, "wait_closed"):
                await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
        except Exception:
            pass
        #LOGGER.info("Client disconnected: %s", peer)

    async def _send(self, writer: asyncio.StreamWriter, obj: JsonObj) -> None:
        """Send a JSON object to a client."""
        try:
            writer.write((json.dumps(obj, ensure_ascii=False)+"\n").encode())
            await writer.drain()
        except Exception: 
            pass
