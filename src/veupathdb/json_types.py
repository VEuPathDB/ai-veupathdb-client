"""The JSON shapes the VEuPathDB services send and receive."""

from pydantic import JsonValue

type JSONValue = JsonValue
type JSONObject = dict[str, JsonValue]
type JSONArray = list[JsonValue]
