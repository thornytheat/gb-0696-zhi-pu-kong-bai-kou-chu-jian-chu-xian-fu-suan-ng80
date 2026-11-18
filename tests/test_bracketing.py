from decimal import Decimal

from app.pipeline import run, sample_text
from app.sequence import merge, tag


def segment(text, upto):
    return "\n".join(text.splitlines()[:upto]) + "\n"


def test_front_segment_is_not_bracketed(result):
    rows = result["final"]
    assert rows and all(r["bracket"] == "MISSING_AFTER" for r in rows)
    assert all(r["lod_valid"] is False for r in rows)
    assert all(r["releasable"] is False for r in rows)
    assert result["handover"]["verdict"] == "整批等齐"
    assert result["handover"]["pending_count"] == len(rows)


def test_back_segment_brackets_earlier_samples(sample):
    tail = "C6,standard,Pb,1300,100,6,1,ug/L,B01\nS052,sample,Pb,330,100,0,1,ug/L,B01\nC7,standard,Pb,1500,100,7,1,ug/L,B01\n"
    merged, segments = merge(segment(sample, 61), tail)
    r = tag(run(merged), segments)
    assert all(x["bracket"] == "BRACKETED" for x in r["final"])
    assert all(x["lod_valid"] for x in r["final"])
    assert r["handover"]["verdict"] == "可复核"
    assert r["handover"]["pending_count"] == 0
    assert next(x for x in r["final"] if x["sample_id"] == "S052")["origin"] == "补测"


def test_retest_rows_keep_source_line(sample):
    tail = "sample_id,kind,analyte,area,internal_area,level,dilution,unit,batch\nC6,standard,Pb,1300,100,6,1,ug/L,B01\nC7,standard,Pb,1500,100,7,1,ug/L,B01\n"
    merged, segments = merge(segment(sample, 61), tail)
    r = tag(run(merged), segments)
    standards = [x for x in r["reports"][0]["rows"] if x["kind"] == "standard" and x["origin"] == "补测"]
    assert [x["source_line"] for x in standards] == [2, 3]
    assert next(x for x in r["reports"][0]["rows"] if x["sample_id"] == "S001")["source_line"] == 11


def test_borrowed_standard_does_not_bracket_other_analyte(sample):
    extra = "\n".join(line.replace(",Pb,", ",As,") for line in sample.splitlines()[1:] if ",Pb," in line)
    r = run(sample + "\n" + extra + "\n")
    assert {x["analyte"] for x in r["final"]} == {"Pb", "As"}
    assert all(x["bracket"] == "MISSING_AFTER" for x in r["final"])


def test_quarantined_standard_cannot_bracket(sample):
    broken = sample.replace("C5,standard,Pb,1100,100,5", "C5,standard,Pb,N/A,100,5")
    r = run(broken)
    assert any(x["reason"] == "MISSING" for x in r["quarantine"])
    assert all(x["bracket"] == "MISSING_AFTER" for x in r["final"])
    assert all(x["prev_standard"]["sample_id"] != "C5" for x in r["final"] if x["prev_standard"])


def test_missing_front_side_reported():
    text = "sample_id,kind,analyte,area,internal_area,level,dilution,unit,batch\nS1,sample,Pb,300,100,0,1,ug/L,B01\nC1,standard,Pb,300,100,1,1,ug/L,B01\nC2,standard,Pb,500,100,2,1,ug/L,B01\nC3,standard,Pb,700,100,3,1,ug/L,B01\nB1,blank,Pb,100,100,0,1,ug/L,B01\n"
    r = run(text)
    row = next(x for x in r["final"] if x["sample_id"] == "S1")
    assert row["bracket"] == "MISSING_BEFORE"
    assert row["bracket_missing"] == ["前标样"]
    assert row["prev_standard"] is None and row["next_standard"]["sample_id"] == "C1"


def test_missing_both_sides_reported():
    from app.modules.m6_quality.rules import bracket
    row = {"sample_id": "S1", "line": 5, "level_value": Decimal(0)}
    sides = bracket(row, [], [])
    assert sides["bracket"] == "MISSING_BOTH"
    assert sides["bracket_missing"] == ["前标样", "后标样"]
    assert sides["prev_standard"] is None and sides["next_standard"] is None


def test_nearest_blank_recorded(result):
    row = next(x for x in result["final"] if x["sample_id"] == "S051")
    assert row["blank_before"]["sample_id"] == "B2"
    assert row["blank_after"] is None
    assert row["blank_before"]["line"] < row["line"]


def test_missing_blank_side_recorded():
    text = "sample_id,kind,analyte,area,internal_area,level,dilution,unit,batch\nC1,standard,Pb,300,100,1,1,ug/L,B01\nC2,standard,Pb,500,100,2,1,ug/L,B01\nC3,standard,Pb,700,100,3,1,ug/L,B01\nS1,sample,Pb,320,100,0,1,ug/L,B01\nB1,blank,Pb,100,100,0,1,ug/L,B01\n"
    r = run(text)
    row = next(x for x in r["final"] if x["sample_id"] == "S1")
    assert row["blank_before"] is None
    assert row["blank_after"]["sample_id"] == "B1"


def test_dilution_and_qualifier_stay_with_row(result):
    row = next(x for x in result["final"] if x["sample_id"] == "S002")
    assert Decimal(row["dilution_value"]) == 2
    assert row["qualifier"] == ""
    low = next(x for x in result["final"] if x["sample_id"] == "S001")
    assert low["status"] == "NEGATIVE_BLANK" and low["qualifier"] == ""
