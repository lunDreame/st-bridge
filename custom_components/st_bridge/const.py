from __future__ import annotations
import logging

DOMAIN = "st_bridge"

CONF_TOKEN = "token"
CONF_PORT = "port"
CONF_ENTITIES = "entities"

DEFAULT_PORT = 8323

SUPPORTED_DOMAINS = {"light", "switch", "fan", "climate"}

LOGGER = logging.getLogger(__package__)
