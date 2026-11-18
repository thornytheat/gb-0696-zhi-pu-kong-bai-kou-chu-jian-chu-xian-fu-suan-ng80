import csv
import io
import json


def _point(value):
    return "" if value is None else f'{value["sample_id"]}@{value["line"]}'


def _side(row, name):
    return _point(row.get(name))


def evidence_csv(run):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "run_id", "sha256", "rule_version", "kind", "line", "source_line", "origin",
        "sample_id", "analyte", "batch", "dilution", "qualifier", "status", "bracket",
        "bracket_missing", "prev_standard", "next_standard", "blank_before", "blank_after",
        "value", "lod", "lod_valid", "releasable", "reason", "evidence",
    ])
    result = run["result"]
    handover = result.get("handover", {})
    writer.writerow([
        run["id"], run["digest"], run["rule_version"], "manifest",
        *([""] * 20),
        json.dumps({"balance": result["balance"], "handover": handover, "decision": run["decision"],
                    "scope": run.get("scope", ""), "revision": run["revision"],
                    "parent_id": run.get("parent_id", ""), "segments": run.get("segments", [])}, ensure_ascii=False),
    ])

    def row(category, item, value=""):
        writer.writerow([
            run["id"], run["digest"], run["rule_version"], category, item.get("line", ""),
            item.get("source_line", ""), item.get("origin", ""), item.get("sample_id", ""),
            item.get("analyte", ""), item.get("batch", ""), item.get("dilution", ""),
            item.get("qualifier", ""), item.get("status", ""), item.get("bracket", ""),
            "/".join(item.get("bracket_missing", [])), _side(item, "prev_standard"),
            _side(item, "next_standard"), _side(item, "blank_before"), _side(item, "blank_after"),
            value, item.get("lod", ""), item.get("lod_valid", ""), item.get("releasable", ""), "",
            json.dumps(item, ensure_ascii=False),
        ])

    for item in result.get("final", []):
        if not item.get("lod_valid"):
            category = "pending"
        elif item.get("releasable"):
            category = "result"
        else:
            category = "blocked"
        row(category, item, item.get("concentration", ""))
    for item in result.get("quarantine", []):
        writer.writerow([
            run["id"], run["digest"], run["rule_version"], "quarantine", item.get("line", ""),
            item.get("source_line", ""), item.get("origin", ""), item.get("id", ""),
            *([""] * 15), item["reason"], json.dumps(item, ensure_ascii=False),
        ])
    for event in run.get("review_events", []):
        writer.writerow([
            run["id"], run["digest"], run["rule_version"], "review",
            *([""] * 20), json.dumps(event, ensure_ascii=False),
        ])
    return "﻿" + out.getvalue()
