from __future__ import annotations

import asyncio
import socket
import struct
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import LOGGER

SSDP_GROUP = ("239.255.255.250", 1900)
SSDP_ST = "urn:st-bridge:service:bridge:1"


class SSDPResponder:
    """Responds to SSDP M-SEARCH for st-bridge only."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, port: int) -> None:
        """Initialize the responder."""
        self.hass = hass
        self.entry = entry
        self.port = port
        self._transport: Optional[asyncio.DatagramTransport] = None

    async def async_start(self) -> None:
        """Start the SSDP responder."""
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", SSDP_GROUP[1]))
        except OSError:
            sock.bind(("", 0))
        mreq = struct.pack("=4sl", socket.inet_aton(SSDP_GROUP[0]), socket.INADDR_ANY)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError:
            pass
        sock.setblocking(False)
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _SSDPProtocol(self._on_datagram), sock=sock
        )
        LOGGER.info("SSDP responder started for st-bridge on port %s", self.port)

    async def async_stop(self) -> None:
        """Stop the SSDP responder."""
        if self._transport:
            self._transport.close()
            self._transport = None
            LOGGER.info("SSDP responder stopped")

    def _on_datagram(self, data: bytes, addr) -> None:
        """Handle incoming SSDP datagrams."""
        try:
            text = data.decode(errors="ignore")
        except Exception:
            return
        first = text.split("\r\n", 1)[0].upper()
        if not first.startswith("M-SEARCH"):
            return

        headers = {}
        for line in text.split("\r\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().upper()] = v.strip()

        st = headers.get("ST", "")
        man = headers.get("MAN", "")
        if not (st in (SSDP_ST, "ssdp:all") and "ssdp:discover" in man):
            return

        ip, port = addr[0], addr[1]
        usn = f"uuid:st-bridge-{self.entry.entry_id}"
        payload = (
            "HTTP/1.1 200 OK\r\n"
            "CACHE-CONTROL: max-age=60\r\n"
            "EXT:\r\n"
            f"ST: {SSDP_ST}\r\n"
            f"USN: {usn}\r\n"
            "SERVER: st-bridge/1.1 UPnP/1.1 HomeAssistant\r\n"
            f"BRIDGE-ID: {self.entry.entry_id}\r\n"
            f"BRIDGE-NAME: ST Bridge\r\n"
            f"BRIDGE-PORT: {self.port}\r\n"
            # LOCATION은 정보 제공용(허브는 응답의 송신자 IP를 씀)
            f"LOCATION: stbridge://{ip}:{self.port}\r\n"
            "\r\n"
        ).encode()

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setblocking(False)
                s.sendto(payload, (ip, port))
        except Exception:
            pass


class _SSDPProtocol(asyncio.DatagramProtocol):
    """SSDP Protocol for handling incoming datagrams."""
    def __init__(self, cb):
        """Initialize the protocol."""
        self._cb = cb
    def datagram_received(self, data, addr):
        """Handle incoming datagrams."""
        self._cb(data, addr)
