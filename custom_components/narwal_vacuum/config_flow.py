"""Config flow for Narwal vacuum integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .narwal_client import NarwalClient, NarwalCommandError, NarwalConnectionError

from .const import CONF_MODEL, CONF_PRODUCT_KEY, DEFAULT_PORT, DOMAIN, NARWAL_MODELS

_LOGGER = logging.getLogger(__name__)

MODEL_OPTIONS = list(NARWAL_MODELS.keys())

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Optional("port", default=DEFAULT_PORT): int,
        vol.Required(CONF_MODEL, default=MODEL_OPTIONS[0]): vol.In(MODEL_OPTIONS),
    }
)


class NarwalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Narwal vacuum."""

    VERSION = 2

    def __init__(self) -> None:
        super().__init__()
        # Pre-filled host when discovery (zeroconf / DHCP) finds the
        # robot before the user starts the flow.
        self._discovered_host: str | None = None

    def _model_label_for_key(self, product_key: str) -> str:
        """Reverse-look up a product_key in the user-facing model table."""
        for label, key in NARWAL_MODELS.items():
            if key == product_key:
                return label
        return f"Narwal {product_key}" if product_key else "Narwal Vacuum"

    def _existing_product_key_for_host(self, host: str) -> str | None:
        """Reuse product_key from an earlier config entry that pointed
        at this host — e.g. when the user is re-adding the robot
        through discovery after a delete + reinstall."""
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get("host") == host:
                key = entry.data.get(CONF_PRODUCT_KEY)
                if key:
                    return key
        return None

    async def _resolve_model(self, host: str, port: int) -> str | None:
        """Try to name the discovered model for the discovery card.

        Cheapest path first — reuse an existing config entry's
        product_key when this host has been configured before. Only
        fall back to a live probe (which hangs if the robot is asleep
        or someone else owns its single WebSocket slot) if we have
        no cached info.

        Best-effort: errors are swallowed, returns None on failure.
        """
        cached = self._existing_product_key_for_host(host)
        if cached:
            return self._model_label_for_key(cached)

        client = NarwalClient(host=host, port=port)
        try:
            await client.connect()
            # Slightly longer than the user-step probe — a sleeping
            # robot needs ~10 s to wake. Errors are still swallowed.
            await client.discover_device_id(timeout=12.0)
            await client.drain_ws_buffer()
            info = await client.get_device_info()
        except Exception as ex:
            _LOGGER.debug("Discovery probe failed: %s", ex)
            return None
        finally:
            await client.disconnect()
        return self._model_label_for_key(info.product_key)

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Robot announces itself as `_narwal_sweeper._tcp` on the LAN."""
        self._discovered_host = str(discovery_info.host)
        await self.async_set_unique_id(discovery_info.hostname.rstrip("."))
        self._abort_if_unique_id_configured(updates={"host": self._discovered_host})
        # Probe quickly so the discovery card can name the actual model.
        model = await self._resolve_model(self._discovered_host, DEFAULT_PORT)
        self.context["title_placeholders"] = {
            "name": model or "Narwal Vacuum",
            "host": self._discovered_host,
        }
        return await self.async_step_user()

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Robot DHCP hostname matches NARWAL_* / narwal_* on the LAN."""
        self._discovered_host = str(discovery_info.ip)
        await self.async_set_unique_id(discovery_info.hostname or self._discovered_host)
        self._abort_if_unique_id_configured(updates={"host": self._discovered_host})
        model = await self._resolve_model(self._discovered_host, DEFAULT_PORT)
        self.context["title_placeholders"] = {
            "name": model or "Narwal Vacuum",
            "host": self._discovered_host,
        }
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — user enters IP, port, and model."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input["host"]
            port = user_input.get("port", DEFAULT_PORT)
            model_label = user_input[CONF_MODEL]
            product_key = NARWAL_MODELS[model_label]

            # If user selected a specific model, set topic prefix directly
            topic_prefix = None if product_key == "auto" else f"/{product_key}"

            client = NarwalClient(
                host=host, port=port, topic_prefix=topic_prefix,
            )
            try:
                await client.connect()
                # Discover device_id from broadcast, then query info
                await client.discover_device_id(timeout=15.0)
                # Drain any stale field5 responses left in the WebSocket
                # buffer from discover's wake probes before sending a
                # real command
                await client.drain_ws_buffer()
                device_info = await client.get_device_info()
            except Exception as ex:
                _LOGGER.warning(
                    "Setup failed: %s: %s", type(ex).__name__, ex,
                )
                errors["base"] = "cannot_connect"
            else:
                device_id = device_info.device_id
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()

                # Use the product key that actually worked (may have been
                # auto-detected during discovery even if user picked "auto")
                resolved_key = client.topic_prefix.lstrip("/")

                return self.async_create_entry(
                    title=model_label if product_key != "auto" else f"Narwal {resolved_key}",
                    data={
                        "host": host,
                        "port": port,
                        "device_id": device_id,
                        CONF_PRODUCT_KEY: resolved_key,
                        CONF_MODEL: model_label,
                    },
                )
            finally:
                await client.disconnect()

        # If we got here from a discovery step, pre-fill the host so the
        # user only has to confirm the model.
        schema = STEP_USER_DATA_SCHEMA
        if self._discovered_host and user_input is None:
            schema = vol.Schema({
                vol.Required("host", default=self._discovered_host): str,
                vol.Optional("port", default=DEFAULT_PORT): int,
                vol.Required(CONF_MODEL, default=MODEL_OPTIONS[0]): vol.In(MODEL_OPTIONS),
            })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
