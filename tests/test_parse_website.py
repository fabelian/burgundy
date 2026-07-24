import pathlib
from datetime import date

from parsers.parse_website import parse_aum, parse_team

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_parse_team_extracts_people():
    html = (FIXTURES / "sample_team.html").read_text(encoding="utf-8")
    people = parse_team(html, valid_from=date(2024, 1, 1))
    by_name = {p.person_name: p for p in people}
    assert "Anne Mette de Place Filippini" in by_name
    assert by_name["Anne Mette de Place Filippini"].title == "Chief Investment Officer"
    assert by_name["Robert Sankey"].title == "Portfolio Manager"
    assert by_name["David Vanderwood"].title == "Senior Vice President"


def test_parse_team_empty_on_garbage():
    assert parse_team("<html><body><p>no team here</p></body></html>") == []


def test_parse_aum_billion():
    html = "<p>Burgundy manages approximately C$25.4 billion in assets.</p>"
    aum = parse_aum(html, as_of=date(2024, 1, 1))
    assert aum is not None
    assert aum.aum == 25_400_000_000.0
    assert aum.currency == "CAD"


def test_parse_aum_none_when_absent():
    assert parse_aum("<p>We are an investment firm.</p>") is None
