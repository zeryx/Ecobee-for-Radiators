"""Smart Thermostat Climate Platform"""
from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    ClimateEntityFeature,
    HVACAction,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
import logging
from datetime import datetime, timezone, timedelta
from collections import deque

_LOGGER = logging.getLogger(__name__)

DOMAIN = "smart_thermostat"
DEFAULT_NAME = "Smart Thermostat"

async def async_setup_platform(hass: HomeAssistant, config: ConfigType, async_add_entities, discovery_info=None):
    """Set up the smart thermostat platform."""
    name = config.get("name", DEFAULT_NAME)
    temp_sensors = config.get("temperature_sensors", [])
    hvac_entity = config.get("hvac_entity")
    min_temp = config.get("min_temp", 16)
    max_temp = config.get("max_temp", 25)
    target_temp = config.get("target_temp", 20)
    tolerance = config.get("tolerance", 0.5)
    minimum_on_time = config.get("minimum_on_time", 5) * 60  # Convert to seconds
    maximum_on_time = config.get("maximum_on_time", 30) * 60  # Convert to seconds
    off_time = config.get("off_time", 20) * 60  # Convert to seconds

    async_add_entities([
        SmartThermostat(
            hass, name, temp_sensors, hvac_entity,
            min_temp, max_temp, target_temp, tolerance,
            minimum_on_time, maximum_on_time, off_time
        )
    ])

class SmartThermostat(ClimateEntity):
    """Smart Thermostat Climate Entity."""
    
    def __init__(self, hass, name, temp_sensors, hvac_entity,
                 min_temp, max_temp, target_temp, tolerance,
                 minimum_on_time, maximum_on_time, off_time):
        """Initialize the thermostat."""
        self._hass = hass
        self._name = name
        self._hvac_entity = hvac_entity
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._target_temperature = target_temp
        self._tolerance = tolerance
        self._temp_sensors = temp_sensors
        
        # HVAC State
        self._hvac_mode = HVACMode.OFF
        self._hvac_action = HVACAction.OFF
        self._is_heating = False
        
        # Add supported features
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
        )
        
        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        
        # Initialize action history
        self._action_history = deque(maxlen=50)  # Keep last 50 actions
        self._last_update = datetime.now()
        self._sensor_temperatures = {}
        
        # Initialize temperature tracking
        self._current_temperature = None
        self._sensor_temperatures = {}
        
        # Initialize cycle tracking
        self._heating_start_time = None
        self._cooling_start_time = None
        self._learning_heating_duration = minimum_on_time  # Default heating duration
        self._minimum_heating_duration = minimum_on_time
        self._maximum_heating_duration = maximum_on_time
        self._off_time = off_time
        self._cycle_status = "initializing"
        self._time_remaining = 0

    def _add_action(self, action: str):
        """Add an action to the history."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._action_history.appendleft(f"[{timestamp}] {action}")
        
    def _is_sensor_fresh(self, sensor_id: str) -> bool:
        """Check if sensor data is fresh (within last 5 minutes)."""
        state = self._hass.states.get(sensor_id)
        if not state:
            self._add_action(f"Sensor {sensor_id} not found")
            # Remove from sensor_temperatures if not found
            self._sensor_temperatures.pop(sensor_id, None)
            return False
            
        try:
            last_updated = state.last_updated
            if isinstance(last_updated, str):
                last_updated = datetime.strptime(last_updated, "%Y-%m-%dT%H:%M:%S.%f%z")
            
            now = datetime.now(timezone.utc)
            time_diff = (now - last_updated).total_seconds()
            
            if time_diff > 300:  # 5 minutes
                self._add_action(f"Sensor {sensor_id} data is stale: {time_diff:.1f}s old")
                # Remove stale data from sensor_temperatures
                self._sensor_temperatures.pop(sensor_id, None)
                return False
            return True
        except Exception as e:
            self._add_action(f"Error checking freshness for {sensor_id}: {str(e)}")
            self._sensor_temperatures.pop(sensor_id, None)
            return False

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._attr_temperature_unit

    @property
    def current_temperature(self):
        """Return the average current temperature from fresh sensors only."""
        fresh_temperatures = {}  # Use dictionary to track both temp and source
        
        for sensor_id in self._temp_sensors:
            try:
                if not self._is_sensor_fresh(sensor_id):
                    continue
                    
                state = self._hass.states.get(sensor_id)
                if state and state.state not in ('unknown', 'unavailable'):
                    try:
                        temp = float(state.state)
                        fresh_temperatures[sensor_id] = temp
                    except ValueError:
                        self._add_action(f"Invalid temperature value from {sensor_id}: {state.state}")
                        continue
                else:
                    self._add_action(f"Invalid state from {sensor_id}: {state.state if state else 'No state'}")
            except Exception as e:
                self._add_action(f"Unexpected error with {sensor_id}: {str(e)}")
                continue

        if fresh_temperatures:
            # Update the sensor_temperatures dictionary
            self._sensor_temperatures = fresh_temperatures.copy()
            avg_temp = sum(fresh_temperatures.values()) / len(fresh_temperatures)
            self._current_temperature = avg_temp
            return avg_temp
        else:
            self._add_action("No fresh temperature data available")
            return None  # Return None instead of self._current_temperature when no data is available

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation ie. heat, cool mode."""
        return self._hvac_mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac operation modes."""
        return self._attr_hvac_modes

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._max_temp

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._attr_supported_features

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running hvac operation."""
        return self._hvac_action

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        now = datetime.now()
        
        # Calculate time remaining in current cycle
        if self._heating_start_time and self._is_heating:
            elapsed = (now - self._heating_start_time).total_seconds()
            self._time_remaining = max(0, self._learning_heating_duration - elapsed)
            cycle_type = "heating"
        elif self._cooling_start_time and not self._is_heating:
            elapsed = (now - self._cooling_start_time).total_seconds()
            self._time_remaining = max(0, self._off_time - elapsed)
            cycle_type = "cooling"
        else:
            self._time_remaining = 0
            cycle_type = "idle"

        return {
            "action_history": list(self._action_history),
            "sensor_temperatures": self._sensor_temperatures,
            "average_temperature": self._current_temperature,
            "fresh_sensor_count": len(self._sensor_temperatures),
            "available_sensors": self._temp_sensors,
            "last_update": now.strftime("%H:%M:%S"),
            "learning_duration": round(self._learning_heating_duration / 60, 1),
            "cycle_status": self._cycle_status,
            "time_remaining": round(self._time_remaining / 60, 1),
            "cycle_type": cycle_type
        }

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._target_temperature = temp
            self._add_action(f"Set temperature to {temp}°C")
            await self._control_heating()
            self.async_write_ha_state()
            self._add_action(f"Set temperature to {temp}°C")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode not in self.hvac_modes:
            return
            
        self._hvac_mode = hvac_mode
        
        # Control underlying HVAC
        if self._hvac_entity:
            if hvac_mode == HVACMode.OFF:
                await self._hass.services.async_call(
                    'climate', 'set_hvac_mode',
                    {
                        'entity_id': self._hvac_entity,
                        'hvac_mode': 'off'
                    }
                )
                self._hvac_action = HVACAction.OFF
                self._is_heating = False
            else:
                await self._hass.services.async_call(
                    'climate', 'set_hvac_mode',
                    {
                        'entity_id': self._hvac_entity,
                        'hvac_mode': 'heat'
                    }
                )
                # Set temperature to max_temp when turning on (Ecobee override)
                await self._hass.services.async_call(
                    'climate', 'set_temperature',
                    {
                        'entity_id': self._hvac_entity,
                        'temperature': self._max_temp  # Changed from fixed 23.0 to max_temp
                    }
                )
                
        await self.async_update_ha_state()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)
        await self.async_set_temperature(self.max_temp)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def _control_heating(self):
        """Control the heating based on temperature."""
        if not self._hvac_entity or self._hvac_mode == HVACMode.OFF:
            self._add_action("Control skipped: HVAC is off or no entity")
            return

        current_temp = self.current_temperature
        if current_temp is None:
            self._add_action("No temperature reading available")
            return

        now = datetime.now()
        
        # Add status check logging
        self._add_action(f"Current status: {self._cycle_status}, Temp: {current_temp:.1f}°C, Target: {self._target_temperature}°C")

        # Check if heating cycle is complete
        if self._heating_start_time and self._is_heating:
            heating_elapsed = (now - self._heating_start_time).total_seconds()
            if heating_elapsed >= self._learning_heating_duration:
                self._cycle_status = "off_period"  # Changed from "cooling"
                await self._hass.services.async_call(
                    'climate', 'set_hvac_mode',
                    {'entity_id': self._hvac_entity, 'hvac_mode': 'off'}
                )
                self._is_heating = False
                self._cooling_start_time = now
                self._add_action(f"Completed heating cycle, reached {current_temp:.1f}°C, starting off period")
                return

        # Check if off period is complete
        if self._cooling_start_time and not self._is_heating:
            cooling_elapsed = (now - self._cooling_start_time).total_seconds()
            self._add_action(f"Off period elapsed: {cooling_elapsed:.1f}s of {self._off_time}s required")
            
            if cooling_elapsed >= self._off_time:
                self._cycle_status = "ready"
                self._add_action("Off period complete - system ready for next cycle")
                # Only adjust learning duration after full cooling period
                temp_diff = self._target_temperature - current_temp
                
                # Calculate adjustment proportional to temperature difference
                # Each degree of difference adjusts by 2 minutes (120 seconds)
                adjustment = abs(temp_diff) * 120
                
                if temp_diff > 0:  # We undershot
                    new_duration = min(
                        self._learning_heating_duration + adjustment,
                        self._maximum_heating_duration
                    )
                    if new_duration != self._learning_heating_duration:
                        self._add_action(f"Undershot by {temp_diff:.1f}°C - Increasing duration to {new_duration/60:.1f}min (was {self._learning_heating_duration/60:.1f}min)")
                        self._learning_heating_duration = new_duration
                elif temp_diff < 0:  # We overshot
                    new_duration = max(
                        self._learning_heating_duration - adjustment,
                        self._minimum_heating_duration
                    )
                    if new_duration != self._learning_heating_duration:
                        self._add_action(f"Overshot by {abs(temp_diff):.1f}°C - Decreasing duration to {new_duration/60:.1f}min (was {self._learning_heating_duration/60:.1f}min)")
                        self._learning_heating_duration = new_duration
                
                self._cooling_start_time = None  # Reset cooling period

        # Log conditions for starting new heating cycle
        if not self._is_heating:
            temp_diff = self._target_temperature - current_temp
            self._add_action(f"Checking heating conditions: Temp diff: {temp_diff:.1f}°C (Need > {self._tolerance}°C)")
            if self._cooling_start_time:
                cooling_elapsed = (now - self._cooling_start_time).total_seconds()
                self._add_action(f"Off period status: {cooling_elapsed:.1f}s elapsed of {self._off_time}s required")

        # Start new heating cycle if needed and cooling period is complete
        if (current_temp < (self._target_temperature - self._tolerance) and 
            not self._is_heating and 
            (self._cooling_start_time is None or 
             (now - self._cooling_start_time).total_seconds() >= self._off_time)):
            
            # Update cycle status before starting new heating cycle
            self._cycle_status = "starting new cycle"
            
            await self._hass.services.async_call(
                'climate', 'set_hvac_mode',
                {'entity_id': self._hvac_entity, 'hvac_mode': 'heat'}
            )
            await self._hass.services.async_call(
                'climate', 'set_temperature',
                {'entity_id': self._hvac_entity, 'temperature': self._max_temp}
            )
            self._is_heating = True
            self._heating_start_time = now
            self._cooling_start_time = None
            self._add_action(f"Started heating cycle at {current_temp:.1f}°C targeting {self._target_temperature}°C for {self._learning_heating_duration/60:.1f}min")

        else:
            # Log why we're not starting a new heating cycle
            if not (current_temp < (self._target_temperature - self._tolerance)):
                self._add_action(f"Waiting for temperature to drop: Current {current_temp:.1f}°C needs to be below {(self._target_temperature - self._tolerance):.1f}°C")
            elif self._is_heating:
                self._add_action("Already heating")
            elif self._cooling_start_time is not None and (now - self._cooling_start_time).total_seconds() < self._off_time:
                remaining = self._off_time - (now - self._cooling_start_time).total_seconds()
                self._add_action(f"Still in off period: {remaining:.1f}s remaining")

    async def async_update(self):
        """Update the current temperature and control heating."""
        # Update temperature before controlling heating
        self.current_temperature
        await self._control_heating()
        # Schedule next update sooner
        self.async_schedule_update_ha_state(True) 