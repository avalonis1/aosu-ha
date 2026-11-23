"""Constants for the Aosu Cameras Home Assistant integration."""

DOMAIN = "aosu"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_COMPREFACE_URL = "compreface_url"
CONF_COMPREFACE_API_KEY = "compreface_api_key"
CONF_FACE_THRESHOLD = "face_threshold"

DEFAULT_REGION = "eu"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_FACE_THRESHOLD = 0.75

EVENT_PERSON_DETECTED = "aosu_person_detected"
EVENT_DOORBELL_RING = "aosu_doorbell_ring"
EVENT_FACE_RECOGNIZED = "aosu_face_recognized"

PLATFORMS = ["camera", "sensor", "binary_sensor", "button"]
