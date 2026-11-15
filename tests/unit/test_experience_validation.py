"""Phase 13: safe CSV/JSON validation (schema, types, duplicates, ids, timestamps, limits, safe paths)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import pytest

from trichurn_experience.config import parse_config
from trichurn_experience.schemas import DatasetKind
from trichurn_experience.validation import (
    PayloadTooLarge,
    UnreadableContent,
    UnsafePath,
    parse_timestamp,
    quality_summary,
    resolve_safe_path,
    schema_for,
    validate_content,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
CFG = parse_config({})


def run(kind, text, fmt="csv", cfg=CFG, **kw):
    return validate_content(kind, text, fmt, cfg, now=NOW, **kw)


FEEDBACK = (
    "feedback_id,customer_id,feedback_text,submitted_at,channel\n"
    "f1,C001,Great service,2026-10-01,email\n"
    "f2,C002,Slow support,2026-10-02T09:30:00Z,chat\n"
)


def test_valid_feedback_csv():
    report, rows = run(DatasetKind.FEEDBACK, FEEDBACK)
    assert report.valid and report.rows_total == 2 and report.rows_valid == 2 and len(rows) == 2
    assert report.error_count == 0 and report.persisted is False


def test_valid_feedback_json_array_and_records_object():
    records = [{"feedback_id": "f1", "customer_id": "C1", "feedback_text": "ok", "submitted_at": "2026-10-01"}]
    assert run(DatasetKind.FEEDBACK, json.dumps(records), "json")[0].valid
    assert run(DatasetKind.FEEDBACK, json.dumps({"records": records}), "json")[0].valid


def test_missing_required_column_is_reported():
    report, _ = run(DatasetKind.FEEDBACK, "feedback_id,customer_id,submitted_at\nf1,C1,2026-10-01\n")
    assert not report.valid and report.missing_required_columns == ["feedback_text"]
    assert report.issue_counts["missing_required_column"] == 1


def test_missing_values_are_counted_per_column():
    text = (
        "feedback_id,customer_id,feedback_text,submitted_at,channel\nf1,C1,,2026-10-01,\nf2,C2,hello,2026-10-02,chat\n"
    )
    report, rows = run(DatasetKind.FEEDBACK, text)
    assert not report.valid and report.missing_value_counts["feedback_text"] == 1
    assert report.missing_value_counts["channel"] == 1  # optional columns are counted but not errors
    assert report.rows_valid == 1 and len(rows) == 1


def test_duplicate_records_are_detected():
    text = (
        "ticket_id,customer_id,category,severity,status,created_at\n"
        "T1,C1,billing,high,open,2026-10-01\nT1,C2,billing,low,open,2026-10-02\n"
    )
    report, rows = run(DatasetKind.TICKETS, text)
    assert report.duplicate_records == 1 and report.issue_counts["duplicate_record"] == 1
    assert not report.valid and len(rows) == 1


def test_duplicate_events_without_id_use_the_composite_key():
    text = (
        "customer_id,event_type,event_timestamp,channel\n"
        "C1,login,2026-10-01T10:00:00Z,app\nC1,login,2026-10-01T10:00:00Z,app\nC1,login,2026-10-01T10:00:00Z,web\n"
    )
    report, _ = run(DatasetKind.EVENTS, text)
    assert report.duplicate_records == 1


@pytest.mark.parametrize("bad_id", ["bad id!", "-leading", "x" * 65, "a/b", "C1;DROP"])
def test_invalid_customer_ids(bad_id):
    text = f"response_id,customer_id,score,survey_date\nr1,{bad_id},9,2026-10-01\n"
    report, _ = run(DatasetKind.NPS, text)
    assert report.invalid_customer_ids == 1 and not report.valid


@pytest.mark.parametrize(
    "value,code",
    [
        ("not-a-date", "invalid_timestamp"),
        ("2026-13-40", "invalid_timestamp"),
        ("31/12/2026", "invalid_timestamp"),
        ("2030-01-01", "timestamp_in_future"),
        ("1980-01-01", "timestamp_too_early"),
    ],
)
def test_invalid_timestamps(value, code):
    text = f"response_id,customer_id,score,survey_date\nr1,C1,9,{value}\n"
    report, _ = run(DatasetKind.NPS, text)
    assert report.invalid_timestamps == 1 and report.issue_counts == {code: 1}


@pytest.mark.parametrize(
    "value", ["2026-10-01", "2026-10-01T10:00:00", "2026-10-01T10:00:00Z", "2026-10-01T10:00:00+05:30"]
)
def test_valid_timestamp_forms(value):
    assert parse_timestamp(value) is not None
    text = f"response_id,customer_id,score,survey_date\nr1,C1,9,{value}\n"
    assert run(DatasetKind.NPS, text)[0].valid


def test_timestamps_are_normalised_to_utc():
    assert parse_timestamp("2026-10-01T10:00:00+05:30") == datetime(2026, 10, 1, 4, 30, tzinfo=UTC)


def test_out_of_order_events_warn_but_remain_valid():
    text = (
        "customer_id,event_type,event_timestamp,channel\n"
        "C1,login,2026-10-02T10:00:00Z,app\nC1,purchase,2026-10-01T10:00:00Z,app\n"
    )
    report, rows = run(DatasetKind.EVENTS, text)
    assert report.valid and report.out_of_order_records == 1 and len(rows) == 2
    assert report.warning_count == 1


def test_unknown_customer_ids_warn_against_reference_list():
    text = "response_id,customer_id,score,survey_date\nr1,KNOWN,9,2026-10-01\nr2,STRANGER,8,2026-10-01\n"
    report, _ = run(DatasetKind.NPS, text, known_customer_ids=["KNOWN"])
    assert report.valid and report.unknown_customer_ids == 1


def test_unexpected_columns_warn_and_are_listed():
    report, _ = run(DatasetKind.NPS, "response_id,customer_id,score,survey_date,extra\nr1,C1,9,2026-10-01,x\n")
    assert report.valid and report.unexpected_columns == ["extra"]


def test_ragged_csv_rows_are_errors():
    report, rows = run(DatasetKind.NPS, "response_id,customer_id,score,survey_date\nr1,C1,9\nr2,C2,8,2026-10-01\n")
    assert report.issue_counts["ragged_row"] == 1 and len(rows) == 1 and not report.valid


def test_duplicate_and_blank_header_columns_are_errors():
    report, _ = run(DatasetKind.NPS, "response_id,customer_id,score,score\nr1,C1,9,9\n")
    assert report.issue_counts.get("duplicate_column") == 1
    report2, _ = run(DatasetKind.NPS, "response_id,customer_id,score,survey_date,\nr1,C1,9,2026-10-01,\n")
    assert report2.issue_counts.get("blank_column_name") == 1


def test_invalid_categories():
    text = (
        "ticket_id,customer_id,category,severity,status,created_at\n"
        "T1,C1,billing,urgent,open,2026-10-01\nT2,C1,billing,high,pending,2026-10-01\n"
    )
    report, _ = run(DatasetKind.TICKETS, text)
    assert report.issue_counts["invalid_category"] == 2
    ok = "feedback_id,customer_id,feedback_text,submitted_at,sentiment_label\nf1,C1,hi,2026-10-01,angry\n"
    assert run(DatasetKind.FEEDBACK, ok)[0].issue_counts["invalid_category"] == 1


def test_category_matching_is_case_insensitive():
    text = "ticket_id,customer_id,category,severity,status,created_at\nT1,C1,billing,HIGH,Open,2026-10-01\n"
    assert run(DatasetKind.TICKETS, text)[0].valid


def test_sla_field_validation():
    text = (
        "ticket_id,customer_id,category,severity,status,created_at,resolved_at,sla_due_at\n"
        "T1,C1,x,high,resolved,2026-10-05,2026-10-01,2026-10-10\n"
        "T2,C1,x,high,open,2026-10-05,,2026-10-01\n"
        "T3,C1,x,high,open,2026-10-05,2026-10-06,2026-10-10\n"
    )
    report, _ = run(DatasetKind.TICKETS, text)
    assert report.issue_counts["resolved_before_created"] == 1
    assert report.issue_counts["sla_before_created"] == 1
    assert report.issue_counts["resolved_at_with_open_status"] == 1


def test_survey_scores_must_be_finite_numbers_in_scale():
    text = (
        "response_id,customer_id,score,survey_date\nr1,C1,abc,2026-10-01\nr2,C1,11,2026-10-01\n"
        "r3,C1,-1,2026-10-01\nr4,C1,nan,2026-10-01\nr5,C1,inf,2026-10-01\nr6,C1,10,2026-10-01\n"
    )
    report, rows = run(DatasetKind.NPS, text)
    assert report.issue_counts["invalid_number"] == 3 and report.issue_counts["score_out_of_scale"] == 2
    assert len(rows) == 1


def test_csat_scale_is_separate_from_nps():
    text = "response_id,customer_id,score,survey_date\nr1,C1,7,2026-10-01\n"
    assert run(DatasetKind.NPS, text)[0].valid
    assert not run(DatasetKind.CSAT, text)[0].valid


def test_event_metadata_must_be_a_json_object():
    text = (
        "customer_id,event_type,event_timestamp,channel,metadata\n"
        'C1,login,2026-10-01T10:00:00Z,app,"{""k"": 1}"\nC1,login,2026-10-02T10:00:00Z,app,[1]\n'
    )
    report, _ = run(DatasetKind.EVENTS, text)
    assert report.issue_counts == {"invalid_json_object": 1}


def test_formula_prefix_in_free_text_is_a_warning_not_executed():
    text = "feedback_id,customer_id,feedback_text,submitted_at\nf1,C1,\"=cmd|' /C calc'!A0\",2026-10-01\n"
    report, rows = run(DatasetKind.FEEDBACK, text)
    assert report.valid and report.issue_counts == {"possible_formula": 1} and rows[0]["feedback_text"].startswith("=")


def test_empty_content_and_header_only():
    with pytest.raises(UnreadableContent):
        run(DatasetKind.NPS, "")
    report, _ = run(DatasetKind.NPS, "response_id,customer_id,score,survey_date\n")
    assert not report.valid and report.issue_counts["no_records"] == 1


def test_json_shapes_and_constants():
    for bad in ('{"records": 5}', '"text"', "42", "not json", "[1, 2]x"):
        with pytest.raises(UnreadableContent):
            run(DatasetKind.NPS, bad, "json")
    with pytest.raises(UnreadableContent):
        run(DatasetKind.NPS, '[{"score": NaN}]', "json")
    report, _ = run(DatasetKind.NPS, "[1, 2]", "json")
    assert report.issue_counts["record_not_object"] == 2
    assert not run(DatasetKind.NPS, "[]", "json")[0].valid


def test_unsupported_format_is_rejected():
    with pytest.raises(UnreadableContent):
        run(DatasetKind.NPS, "<xml/>", "xml")


def test_binary_and_non_utf8_content_is_rejected():
    with pytest.raises(UnreadableContent):
        validate_content(DatasetKind.NPS, b"a,b\n\x00\x01", "csv", CFG, now=NOW)
    with pytest.raises(UnreadableContent):
        validate_content(DatasetKind.NPS, b"\xff\xfe\xfa", "csv", CFG, now=NOW)


def test_utf8_bom_is_handled():
    data = ("\ufeffresponse_id,customer_id,score,survey_date\nr1,C1,9,2026-10-01\n").encode()
    assert validate_content(DatasetKind.NPS, data, "csv", CFG, now=NOW)[0].valid


def test_size_row_column_and_field_limits():
    small = parse_config({"limits": {"max_bytes": 100}})
    with pytest.raises(PayloadTooLarge):
        run(DatasetKind.NPS, "a" * 101, cfg=small)
    rows = parse_config({"limits": {"max_rows": 2}})
    text = "response_id,customer_id,score,survey_date\n" + "r,C,9,2026-10-01\n" * 3
    with pytest.raises(PayloadTooLarge):
        run(DatasetKind.NPS, text, cfg=rows)
    cols = parse_config({"limits": {"max_columns": 3}})
    with pytest.raises(PayloadTooLarge):
        run(DatasetKind.NPS, "a,b,c,d\n1,2,3,4\n", cfg=cols)
    with pytest.raises(PayloadTooLarge):
        run(DatasetKind.NPS, json.dumps([{"a": 1, "b": 2, "c": 3, "d": 4}]), "json", cfg=cols)
    with pytest.raises(PayloadTooLarge):
        run(DatasetKind.NPS, json.dumps([{}] * 3), "json", cfg=rows)
    fields = parse_config({"limits": {"max_field_chars": 10}})
    report, _ = run(
        DatasetKind.FEEDBACK,
        "feedback_id,customer_id,feedback_text,submitted_at\nf1,C1," + "x" * 11 + ",2026-10-01\n",
        cfg=fields,
    )
    assert report.issue_counts["field_too_long"] == 1 and not report.valid


def test_issue_list_is_truncated_but_counts_stay_complete():
    cfg = parse_config({"limits": {"max_issues_reported": 5}})
    text = "response_id,customer_id,score,survey_date\n" + "".join(f"r{i},C1,99,2026-10-01\n" for i in range(20))
    report, _ = run(DatasetKind.NPS, text, cfg=cfg)
    assert len(report.issues) == 5 and report.issues_truncated and report.issue_counts["score_out_of_scale"] == 20


def test_messages_never_contain_cell_values():
    secret = "SECRET-VALUE-123"
    text = (
        f"ticket_id,customer_id,category,severity,status,created_at\nT1,{secret},billing,{secret},{secret},{secret}\n"
    )
    report, _ = run(DatasetKind.TICKETS, text)
    assert report.error_count == 3  # severity, status, timestamp (the id format is legal)
    assert secret not in json.dumps(report.to_dict())


def test_validation_never_writes_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(DatasetKind.FEEDBACK, FEEDBACK)
    assert list(tmp_path.iterdir()) == []


def test_schema_exposes_required_and_optional_columns():
    s = schema_for(DatasetKind.FEEDBACK, CFG)
    assert s.required_columns == ("feedback_id", "customer_id", "feedback_text", "submitted_at")
    assert "sentiment_label" in s.optional_columns


def test_quality_summary_rates():
    text = (
        "ticket_id,customer_id,category,severity,status,created_at,resolved_at\n"
        "T1,C1,a,high,open,2026-10-01,\nT1,C2,a,high,open,2026-10-02,\nT3,C3,a,low,open,2026-10-03,\n"
        "T4,C4,a,low,open,2026-10-04,\n"
    )
    report, rows = run(DatasetKind.TICKETS, text)
    q = quality_summary(report, rows, schema_for(DatasetKind.TICKETS, CFG))
    assert q["rows_total"] == 4 and q["valid_row_pct"] == 75.0 and q["duplicate_pct"] == 25.0
    assert q["completeness_pct_by_column"]["resolved_at"] == 0.0
    assert q["timestamp_range"]["earliest"].startswith("2026-10-01")


def test_quality_summary_of_empty_file_has_no_rates():
    report, rows = run(DatasetKind.NPS, "response_id,customer_id,score,survey_date\n")
    q = quality_summary(report, rows, schema_for(DatasetKind.NPS, CFG))
    assert q["valid_row_pct"] is None and q["duplicate_pct"] is None


# ---------------------------------------------------------------------------------------------- safe paths
def test_safe_path_accepts_files_inside_the_directory(tmp_path):
    (tmp_path / "sub").mkdir()
    assert resolve_safe_path(tmp_path, "sub/feedback.csv") == (tmp_path / "sub" / "feedback.csv").resolve()


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "/etc/passwd.csv",
        "\\windows\\x.csv",
        "C:\\x.csv",
        "../x.csv",
        "a/../../x.csv",
        "..\\x.csv",
        "x.exe",
        "x.csv\x00.exe",
        "noext",
    ],
)
def test_safe_path_rejects_unsafe_values(tmp_path, bad):
    with pytest.raises(UnsafePath):
        resolve_safe_path(tmp_path, bad)


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_safe_path_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.csv").write_text("x", encoding="utf-8")
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "link.csv").symlink_to(outside / "secret.csv")
    with pytest.raises(UnsafePath):
        resolve_safe_path(inside, "link.csv")
