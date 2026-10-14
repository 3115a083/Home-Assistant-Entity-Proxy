"""Constants for Entity Proxy."""

DOMAIN = "entity_proxy"
SUPPORTED_DOMAINS = frozenset({
    "light", "switch", "climate", "sensor", "binary_sensor",
    "fan", "cover", "number", "select",
})
# Proxy commands only target Home Assistant's ordinary entity-control services.
# Never allow integration/system/shell/script/automation calls through user rules.
ALLOWED_SERVICES = {
    "light": frozenset({"turn_on", "turn_off", "toggle"}),
    "switch": frozenset({"turn_on", "turn_off", "toggle"}),
    "climate": frozenset({"turn_on", "turn_off", "set_temperature", "set_hvac_mode", "set_humidity", "set_fan_mode", "set_preset_mode", "set_swing_mode", "set_swing_horizontal_mode", "set_aux_heat"}),
    "fan": frozenset({"turn_on", "turn_off", "toggle", "set_percentage", "set_preset_mode", "set_direction", "set_oscillating", "increase_speed", "decrease_speed"}),
    "cover": frozenset({"open_cover", "close_cover", "stop_cover", "toggle", "set_cover_position", "open_cover_tilt", "close_cover_tilt", "stop_cover_tilt", "set_cover_tilt_position"}),
    "number": frozenset({"set_value"}),
    "select": frozenset({"select_option", "select_next", "select_previous", "select_first", "select_last"}),
    "input_boolean": frozenset({"turn_on", "turn_off", "toggle"}),
    "input_number": frozenset({"set_value", "increment", "decrement"}),
    "button": frozenset({"press"}),
}
MAX_RULE_TEXT = 16000
MAX_STATE_RULES = 48
MAX_ACTION_RULES = 30
MAX_STEPS = 12
MAX_ERRORS = 20
ACTION_TIMEOUT = 15
SNAPSHOT_KEYS = (
    "brightness", "rgb_color", "rgbw_color", "rgbww_color", "hs_color",
    "xy_color", "color_temp_kelvin", "color_temp", "effect",
)
# Data accepted on the light.turn_on call when restoring its former appearance.
RESTORE_COLOR_KEYS = (
    "rgbww_color", "rgbw_color", "rgb_color", "hs_color", "xy_color", "color_temp_kelvin", "color_temp",
)
