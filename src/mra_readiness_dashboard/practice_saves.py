"""Finite presentation metadata for browser-local fictional practice saves."""
from copy import deepcopy
from urllib.parse import urlencode

from .guided_practice import EXERCISE_OPTIONS, evaluate_practice
from .interactive_tutorial import CONTROL_KEYS, CONTROL_OPTIONS

SCHEMA = "local-fictional-practice-saves-ui/1"
EXPORT_SCHEMA = "local-fictional-practice-saves/1"
STORAGE_KEY = "mra.demo-practice-saves.v1"
PAGE_PATH = "/practice-saves"
SCRIPT_PATH = "/assets/practice-saves.js"
MAX_ENTRIES = 20
MAX_NAME_LENGTH = 80
MAX_FILE_BYTES = 65536
SAVES_CSP = "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"


def library_payload(values=None, exercise=None):
    """Return fresh finite UI metadata, optionally one complete applied case.

    Browser names, saved libraries, files and authority claims are never inputs.
    An omitted candidate is distinct from an explicitly complete practice case.
    """
    candidate = None
    title = None
    if values is not None or exercise is not None:
        if type(values) is not dict or set(values) != set(CONTROL_KEYS):
            raise ValueError("A saved-demo candidate needs all twelve choices")
        if any(type(key) is not str or type(value) is not str for key, value in values.items()):
            raise ValueError("Saved-demo choices must be finite text values")
        if type(exercise) is not str or exercise not in dict(EXERCISE_OPTIONS):
            raise ValueError("Unknown saved-demo exercise")
        practice = evaluate_practice(values, exercise)
        candidate = {"exercise": practice["id"], "assumptions": deepcopy(practice["assumptions"])}
        title = practice["title"]
    return {
        "schema": SCHEMA, "storage_key": STORAGE_KEY, "export_schema": EXPORT_SCHEMA,
        "max_entries": MAX_ENTRIES, "max_name_length": MAX_NAME_LENGTH,
        "max_file_bytes": MAX_FILE_BYTES,
        "exercises": [{"id": key, "title": label} for key, label in EXERCISE_OPTIONS],
        "controls": [{"key": row["key"], "label": row["label"],
                      "values": [value for value, _ in row["options"]]}
                     for row in CONTROL_OPTIONS],
        "candidate": candidate, "candidate_title": title,
    }


def practice_save_url(values, exercise):
    """Carry complete applied finite choices to the separate saved-demo page."""
    candidate = library_payload(values, exercise)["candidate"]
    fields = [("exercise", candidate["exercise"])]
    fields.extend((key, candidate["assumptions"][key]) for key in CONTROL_KEYS)
    return PAGE_PATH + "?" + urlencode(fields)
