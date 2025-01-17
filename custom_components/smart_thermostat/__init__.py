"""The Smart Thermostat integration."""
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry

_LOGGER = logging.getLogger(__name__)

DOMAIN = "smart_thermostat"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Smart Thermostat component."""
    
    async def async_handle_turn_on(call: ServiceCall) -> None:
        """Handle the turn_on service call."""
        entity_id = call.data.get("entity_id")
        if entity_id is None:
            raise ValueError("entity_id must be provided for turn_on service")

        ent_reg = entity_registry.async_get(hass)
        entity = ent_reg.async_get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        try:
            thermostat = hass.data[DOMAIN][entity.unique_id]
            await thermostat.async_turn_on()
        except KeyError:
            _LOGGER.error("Thermostat %s not found in smart_thermostat component", entity_id)
            raise
        except HomeAssistantError as err:
            _LOGGER.error("Failed to turn on thermostat %s: %s", entity_id, str(err))
            raise

    async def async_handle_turn_off(call: ServiceCall) -> None:
        """Handle the turn_off service call."""
        entity_id = call.data.get("entity_id")
        if entity_id is None:
            raise ValueError("entity_id must be provided for turn_off service")

        ent_reg = entity_registry.async_get(hass)
        entity = ent_reg.async_get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        try:
            thermostat = hass.data[DOMAIN][entity.unique_id]
            await thermostat.async_turn_off()
        except KeyError:
            _LOGGER.error("Thermostat %s not found in smart_thermostat component", entity_id)
            raise
        except HomeAssistantError as err:
            _LOGGER.error("Failed to turn off thermostat %s: %s", entity_id, str(err))
            raise

    async def async_handle_force_mode(call: ServiceCall) -> None:
        """Handle forcing a specific heat source."""
        entity_id = call.data.get("entity_id")
        force_mode = call.data.get("force_mode")
        
        if entity_id is None:
            raise ValueError("entity_id must be provided")

        ent_reg = entity_registry.async_get(hass)
        entity = ent_reg.async_get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        try:
            thermostat = hass.data[DOMAIN][entity.unique_id]
            await thermostat.async_force_heat_source(force_mode)
        except KeyError:
            _LOGGER.error("Thermostat %s not found", entity_id)
            raise
        except HomeAssistantError as err:
            _LOGGER.error("Failed to set force mode for %s: %s", entity_id, str(err))
            raise

    try:
        # Register our services with error handling
        hass.services.async_register(
            DOMAIN, "turn_on", async_handle_turn_on
        )
        hass.services.async_register(
            DOMAIN, "turn_off", async_handle_turn_off
        )
        hass.services.async_register(
            DOMAIN, "force_mode", async_handle_force_mode
        )
        return True
    except Exception as e:
        _LOGGER.error("Failed to register smart_thermostat services: %s", str(e))
        return False 