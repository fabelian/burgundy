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


def _render_aum_tab(table):
    from dashboard.app import templates

    return templates.get_template("aum.html").render(
        aum_series=SERIES, table=table, filing_status=None
    )


def _row(as_of, aum, source="13f_total", **kw):
    from datetime import date, datetime

    base = {"as_of_date": date.fromisoformat(as_of), "source": source, "aum": aum,
            "currency": "USD", "fetched_at": datetime(2026, 7, 25, 0, 40),
            "accession_no": None, "source_url": None, "prev_aum": None,
            "ratio": None, "suspect": False}
    return {**base, **kw}


def test_aum_tab_lists_each_observation_with_its_source():
    html = _render_aum_tab([
        _row("2025-09-30", 9.65e9),
        _row("2025-06-30", 1.02e10, source="form_adv",
             accession_no="0001234567-25-000001",
             source_url="https://www.sec.gov/Archives/edgar/data/1315868/x.xml"),
    ])
    assert "2025-09-30" in html and "9,650,000,000" in html
    assert "13F 합계" in html and "Form ADV" in html
    assert 'href="https://www.sec.gov/Archives/edgar/data/1315868/x.xml"' in html


def test_aum_tab_flags_order_of_magnitude_jumps():
    """A mis-scaled filing must be visible as data, not just a flattened axis."""
    normal = _row("2025-06-30", 1.0e10, ratio=1.03)
    spike = _row("2025-09-30", 7.7e15, ratio=770000.0, suspect=True)
    html = _render_aum_tab([spike, normal])
    assert "이상치?" in html
    assert "&times;770000.00" in html
    assert "+3.0%" in html


def test_dates_are_serialised_not_repr():
    from datetime import date

    out = _render({"s": [{"x": date(2025, 9, 30), "y": 1.0}]})
    assert '"2025-09-30"' in out
