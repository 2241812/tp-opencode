from opencode_telegram_bot.api.client import OpenCodeClient


def test_parse_sse_event_text():
    event_text = "event: text\ndata: {\"delta\": \"hello\"}"
    result = OpenCodeClient._parse_sse_event(event_text)
    assert result is not None
    assert result["type"] == "text"
    assert result["data"]["delta"] == "hello"


def test_parse_sse_event_tool_call():
    event_text = "event: tool_call\ndata: {\"tool\": \"bash\", \"input\": \"ls\"}"
    result = OpenCodeClient._parse_sse_event(event_text)
    assert result is not None
    assert result["type"] == "tool_call"
    assert result["data"]["tool"] == "bash"


def test_parse_sse_event_invalid():
    event_text = "event: text\ndata: not valid json"
    result = OpenCodeClient._parse_sse_event(event_text)
    assert result is None


def test_parse_sse_event_empty():
    result = OpenCodeClient._parse_sse_event("")
    assert result is None
