from __future__ import annotations

from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback, State
from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PORT,
    CONF_ENTITIES,
    SUPPORTED_DOMAINS,
    LOGGER
)
from .discovery import SSDPResponder
from .server import BridgeServer

class BridgeCoordinator:
    """Manages the lifecycle of the ST Bridge server and SSDP responder."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the BridgeCoordinator."""
        self.hass = hass
        self.entry = entry
        self.port: int = entry.data[CONF_PORT]
        self._unsub_state: Callable[[], None] | None = None
        self._ssdp: SSDPResponder | None = None
        self._server: BridgeServer | None = None

    async def async_start(self) -> None:
        """Start the ST Bridge server and SSDP responder."""
        self._ssdp = SSDPResponder(self.hass, self.entry, self.port)
        await self._ssdp.async_start()
        self._server = BridgeServer(
            hass=self.hass,
            port=self.port,
            get_entities=self.get_entities,
            call_service=self.call_service, # type: ignore
        )
        await self._server.start()
        self._unsub_state = self.hass.bus.async_listen("state_changed", self._on_state_changed)
        LOGGER.info("ST Bridge started on port %s (entities=%d)", self.port, len(self.entry.options.get(CONF_ENTITIES, [])))

    async def async_stop(self) -> None:
        """Stop the ST Bridge server and SSDP responder."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._ssdp:
            await self._ssdp.async_stop()
            self._ssdp = None
        if self._server:
            await self._server.async_close()
            self._server = None
        LOGGER.info("ST Bridge stopped")

    async def async_handle_entry_update(self) -> None:
        """Handle updates to the config entry."""
        if self._server:
            await self._server.broadcast_entity_list(self.get_entities())

    # =========== Entity features ===========

    def get_entities(self) -> list[dict[str, Any]]:
        """Get the list of entities to expose to the ST Bridge."""
        out: list[dict[str, Any]] = []
        selected = set(self.entry.options.get(CONF_ENTITIES, []))
        for ent_id in sorted(selected):
            st: State | None = self.hass.states.get(ent_id)
            if not st: 
                continue
            domain = ent_id.split(".")[0]
            if domain not in SUPPORTED_DOMAINS:
                continue
            out.append({
                "entity_id": ent_id,
                "domain": domain,
                "friendly_name": st.attributes.get("friendly_name", ent_id),
                "features": self._infer_features(domain, st.attributes),
            })
        return out

    def _infer_features(self, domain: str, a: dict[str, Any]) -> dict[str, Any]:
        """Infer the features of an entity based on its domain and attributes."""
        if domain == "light":
            return {
                "brightness": ("brightness" in a) or ("supported_color_modes" in a and "brightness" in a.get("supported_color_modes", [])),
                "color_temp_mireds": ("color_temp" in a),
                "color_temp_kelvin": ("color_temp_kelvin" in a),
                "min_mireds": a.get("min_mireds"), "max_mireds": a.get("max_mireds"),
                "color": any(k in a for k in ("rgb_color","hs_color","xy_color")),
                "supported_color_modes": a.get("supported_color_modes"),
                "effect_list": a.get("effect_list"),
                "transition": True  # allow transition seconds passthrough
            }
        if domain == "switch":
            return {}
        if domain == "fan":
            return {
                "percentage": "percentage" in a or "speed" in a,
                "preset_modes": a.get("preset_modes"),
                "oscillate": "oscillating" in a,
                "direction": "direction" in a
            }
        if domain == "climate":
            return {
                "hvac_modes": a.get("hvac_modes"),
                "fan_modes": a.get("fan_modes"),
                "swing_modes": a.get("swing_modes"),
                "preset_modes": a.get("preset_modes"),
                "min_temp": a.get("min_temp"), "max_temp": a.get("max_temp"),
                "target_temp_step": a.get("target_temp_step")
            }
        return {}

    # =========== Command routing (spec expanded) ===========

    async def call_service(self, entity_id: str, command: str, args: dict[str, Any]) -> None:
        """Call a service on the specified entity."""
        domain = entity_id.split(".")[0]
        data: dict[str, Any] = {"entity_id": entity_id}

        # ----- LIGHT (rich) -----
        if domain == "light":
            if command in ("turn_on","turn_off","toggle"):
                if command == "turn_on":
                    # brightness: 0-255 / brightness_pct:0-100 / level:0-100
                    if "brightness" in args: 
                        data["brightness"] = int(args["brightness"])
                    if "brightness_pct" in args: 
                        data["brightness"] = round(max(0,min(100,int(args["brightness_pct"])))*255/100)
                    if "level" in args: 
                        data["brightness"] = round(max(0,min(100,int(args["level"])))*255/100)
                    # color temp (mireds/kelvin)
                    if "color_temp_mireds" in args: 
                        data["color_temp"] = int(args["color_temp_mireds"])
                    if "color_temp_kelvin" in args: 
                        data["kelvin"] = int(args["color_temp_kelvin"])
                    if "color_temp" in args: 
                        data["color_temp"] = int(args["color_temp"])
                    # color (hs/rgb/xy) - HA가 알아서 모드 처리
                    if "hs_color" in args: 
                        data["hs_color"] = args["hs_color"]
                    if "rgb_color" in args: 
                        data["rgb_color"] = args["rgb_color"]
                    if "xy_color" in args: 
                        data["xy_color"] = args["xy_color"]
                    # effect / transition
                    if "effect" in args: 
                        data["effect"] = str(args["effect"])
                    if "transition" in args: 
                        data["transition"] = float(args["transition"])
                await self._ha_call("light", command, data)
                return

        # ----- SWITCH -----
        if domain == "switch":
            if command in ("turn_on","turn_off","toggle"):
                await self._ha_call("switch", command, data)
                return

        # ----- FAN (percentage/preset/oscillate/direction) -----
        if domain == "fan":
            if command in ("turn_on","turn_off","toggle"):
                await self._ha_call("fan", command, data)
                return
            if command in ("set_percentage","set_speed"):
                pct = args.get("percentage", args.get("level"))
                if pct is not None: 
                    data["percentage"] = max(0, min(100, int(pct)))
                await self._ha_call("fan", "set_percentage", data)
                return
            if command == "set_preset_mode" and "preset_mode" in args:
                data["preset_mode"] = str(args["preset_mode"])
                await self._ha_call("fan", "set_preset_mode", data)
                return
            if command == "oscillate" and "oscillating" in args:
                data["oscillating"] = bool(args["oscillating"])
                await self._ha_call("fan", "oscillate", data)
                return
            if command == "set_direction" and "direction" in args:
                data["direction"] = str(args["direction"])
                await self._ha_call("fan", "set_direction", data)
                return

        # ----- CLIMATE (mode/setpoint/fan/swing/preset) -----
        if domain == "climate":
            if command == "set_hvac_mode" and "hvac_mode" in args:
                data["hvac_mode"] = str(args["hvac_mode"])
                await self._ha_call("climate", "set_hvac_mode", data)
                return
            if command in ("turn_on","turn_off"):
                data["hvac_mode"] = "off" if command == "turn_off" else str(args.get("hvac_mode","auto"))
                await self._ha_call("climate", "set_hvac_mode", data)
                return
            if command == "set_temperature":
                # single / dual setpoint
                if "temperature" in args: 
                    data["temperature"] = float(args["temperature"])
                if "target_temp" in args: 
                    data["temperature"] = float(args["target_temp"])
                if "target_temp_low" in args: 
                    data["target_temp_low"] = float(args["target_temp_low"])
                if "target_temp_high" in args: 
                    data["target_temp_high"] = float(args["target_temp_high"])
                if "hvac_mode" in args: 
                    data["hvac_mode"] = str(args["hvac_mode"])
                await self._ha_call("climate", "set_temperature", data)
                return
            if command == "set_fan_mode" and "fan_mode" in args:
                data["fan_mode"] = str(args["fan_mode"])
                await self._ha_call("climate", "set_fan_mode", data)
                return
            if command == "set_swing_mode" and "swing_mode" in args:
                data["swing_mode"] = str(args["swing_mode"])
                await self._ha_call("climate", "set_swing_mode", data)
                return
            if command == "set_preset_mode" and "preset_mode" in args:
                data["preset_mode"] = str(args["preset_mode"])
                await self._ha_call("climate", "set_preset_mode", data)
                return

        LOGGER.warning("Unhandled command: %s %s %s", entity_id, command, args)

    async def _ha_call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        """Call a service on the specified domain and service with the given data."""
        await self.hass.services.async_call(domain, service, data, blocking=False)

    # =========== State forward ===========
    @callback
    async def _on_state_changed(self, event) -> None:
        """Handle state change events."""
        ent_id = event.data.get("entity_id")
        ns = event.data.get("new_state")
        if not ent_id or not ns: 
            return
        selected = set(self.entry.options.get(CONF_ENTITIES, []))
        if ent_id not in selected: 
            return
        payload = {
            "type": "state",
            "entity_id": ent_id,
            "state": ns.state,
            "attributes": ns.attributes,
            "ts": int(dt_util.utcnow().timestamp()),
        }
        if self._server: 
            await self._server.broadcast(payload)
