"""Chart payloads must survive template rendering as executable JavaScript.

Jinja2 autoescapes plain strings, and HTML entities are *not* decoded inside a
``<script>`` block — so an escaped quote reaches the JS parser verbatim and kills
the whole block, leaving a blank chart with data sitting in the database.
"""
from __future__ import annotations

import json
import re

from dashboard.app import _tojson_safe


SERIES = {"13f_total": [{"x": "2025-09-30", "y": 9.65e9, "currency": "USD"}]}


def _render(value):
    """Render the filter through the real template environment."""
    from dashboard.app import templates

    tmpl = templates.env.from_string("var series = {{ v | tojson_safe }};")
    return tmpl.render(v=value)


def test_filter_output_is_not_html_escaped():
    out = _render(SERIES)
    assert "&#34;" not in out and "&quot;" not in out and "&amp;" not in out
    assert '"13f_total"' in out


def test_rendered_payload_parses_back_as_json():
    out = _render(SERIES)
    payload = re.search(r"var series = (.*);", out).group(1)
    assert json.loads(payload) == SERIES


def test_script_breaking_characters_are_escaped():
    """A name containing </script> or & must not break out of the tag."""
    out = _render({"a</script><b>": [{"x": "2025-09-30", "y": 1.0}], "R&D": []})
    assert "</script>" not in out
    assert "\\u003c/script\\u003e" in out
    assert "\\u0026" in out
    # still valid JSON once parsed by a JS/JSON parser
    payload = re.search(r"var series = (.*);", out).group(1)
    assert json.loads(payload)["R&D"] == []


def test_dates_are_serialised_not_repr():
    from datetime import date

    out = _render({"s": [{"x": date(2025, 9, 30), "y": 1.0}]})
    assert '"2025-09-30"' in out
