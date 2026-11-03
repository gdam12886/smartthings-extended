"""Configuration for SmartThings Extended."""

DOMAIN = "smartthings_extended"
NATIVE_DOMAIN = "smartthings"
NAME = "SmartThings Extended"
CONF_SOURCE = "native_entry_id"
CONF_DEVICES = "device_ids"
CONF_FEATURES = "features"
CONF_TIMER_MAX = "timer_max_minutes"
FEATURES = ("appliance", "light", "fan", "timer")
DEFAULT_TIMER_MAX = 60
HOOD = "hood"

ENTITY_KEYS = {
    "light": ("light",),
    "fan": ("fan",),
    "timer": ("timer_duration", "timer_start", "timer_cancel", "timer_status", "timer_remaining"),
}
