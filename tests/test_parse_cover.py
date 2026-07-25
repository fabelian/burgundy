import pathlib

from parsers.parse_13f import parse_cover

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_parse_nt_cover():
    xml = (FIXTURES / "sample_13f_nt.xml").read_text(encoding="utf-8")
    cover = parse_cover(xml)
    assert cover["report_type"] == "13F NOTICE"
    assert cover["other_managers"] == "BANK OF MONTREAL /CAN/"


def test_parse_hr_cover_has_no_other_managers():
    # the info-table fixture is not a cover page; parser must not crash
    xml = (FIXTURES / "sample_13f.xml").read_text(encoding="utf-8")
    cover = parse_cover(xml)
    assert cover["other_managers"] is None
