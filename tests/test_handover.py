import uuid

import pytest
from fastapi.testclient import TestClient

from app import batches, store
from app.errors import BusinessError
from app.main import app
from app.pipeline import run, sample_text

client = TestClient(app, raise_server_exceptions=False)

def head_text(batch):
    base = "\n".join(sample_text().splitlines()[:61])
    return base.replace(",B01", f",{batch}") + "\n"


def tail_text(batch):
    return f"sample_id,kind,analyte,area,internal_area,level,dilution,unit,batch\nC6,standard,Pb,1300,100,6,1,ug/L,{batch}\nS052,sample,Pb,330,100,0,1,ug/L,{batch}\nC7,standard,Pb,1500,100,7,1,ug/L,{batch}\n"


def submit_head():
    return batches.submit({"text": head_text(uuid.uuid4().hex[:8])})


def submit_retest(item):
    batch = item["result"]["reports"][0]["rows"][0]["batch"]
    return batches.submit({"parent_id": item["id"], "retest": tail_text(batch)})


def test_pending_batch_blocks_whole_review():
    item, _ = submit_head()
    with pytest.raises(BusinessError) as caught:
        store.review(item["id"], item["revision"], "通过", "整批")
    assert caught.value.code == "SCOPE"


def test_partial_release_requires_released_rows():
    item, _ = submit_head()
    with pytest.raises(BusinessError) as caught:
        store.review(item["id"], item["revision"], "通过", "可证实部分")
    assert caught.value.code == "SCOPE"


def test_review_scope_must_be_known():
    item, _ = submit_head()
    with pytest.raises(BusinessError):
        store.review(item["id"], item["revision"], "退回", "后段")


def test_retest_unblocks_whole_batch():
    item, _ = submit_head()
    retest, reused = submit_retest(item)
    assert reused is False
    assert retest["result"]["handover"]["verdict"] == "可复核"
    assert retest["parent_id"] == item["id"]
    done = store.review(retest["id"], retest["revision"], "通过", "整批")
    assert done["decision"] == "通过"


def test_retest_is_idempotent():
    item, _ = submit_head()
    first, _ = submit_retest(item)
    again, reused = submit_retest(item)
    assert reused is True and again["id"] == first["id"]
    assert len(store.get(item["id"])["retests"]) == 1


def test_failed_retest_keeps_old_version():
    item, _ = submit_head()
    revision = item["revision"]
    with pytest.raises(BusinessError):
        batches.submit({"parent_id": item["id"], "retest": "C6,standard,Pb,1300\n"})
    after = store.get(item["id"])
    assert after["revision"] == revision
    assert after["result"]["handover"]["verdict"] == "整批等齐"
    assert after["retests"] == []


def test_empty_retest_keeps_old_version():
    item, _ = submit_head()
    with pytest.raises(BusinessError):
        batches.submit({"parent_id": item["id"], "retest": "\n\n"})
    assert store.get(item["id"])["retests"] == []


def test_retest_without_new_rows_keeps_old_version():
    item, _ = submit_head()
    batch = item["result"]["reports"][0]["rows"][0]["batch"]
    with pytest.raises(BusinessError):
        batches.submit({"parent_id": item["id"], "retest": f"S001,sample,Pb,600,100,0,1,ug/L,{batch}\n"})
    assert store.get(item["id"])["retests"] == []


def test_review_history_is_append_only():
    item, _ = submit_head()
    store.review(item["id"], item["revision"], "退回", "整批")
    current = store.get(item["id"])
    store.review(current["id"], current["revision"], "退回", "整批")
    history = store.get(item["id"])["review_events"]
    assert [e["revision"] for e in history] == [1, 2]
    assert [e["decision"] for e in history] == ["退回", "退回"]


def test_stale_review_cannot_overwrite():
    item, _ = submit_head()
    store.review(item["id"], item["revision"], "退回", "整批")
    with pytest.raises(BusinessError) as caught:
        store.review(item["id"], item["revision"], "通过", "可证实部分")
    assert caught.value.code == "STALE"


def test_api_review_scope_and_events():
    item, _ = submit_head()
    response = client.post("/api/review", json={"id": item["id"], "revision": item["revision"], "decision": "通过", "scope": "整批"})
    assert response.status_code == 409
    response = client.post("/api/review", json={"id": item["id"], "revision": item["revision"], "decision": "退回", "scope": "整批"})
    assert response.status_code == 200
    assert response.json()["review_events"][-1]["scope"] == "整批"


def test_api_retest_reuses_and_flags():
    item, _ = submit_head()
    batch = item["result"]["reports"][0]["rows"][0]["batch"]
    body = {"parent_id": item["id"], "retest": tail_text(batch)}
    first = client.post("/api/run", json=body)
    second = client.post("/api/run", json=body)
    assert first.status_code == 200 and first.headers["X-Retest-Reused"] == "0"
    assert second.headers["X-Retest-Reused"] == "1"
    assert first.json()["id"] == second.json()["id"]


def test_export_separates_pending_rows():
    item, _ = submit_head()
    from app.exporter import evidence_csv
    text = evidence_csv(store.get(item["id"]))
    header = text.splitlines()[0].lstrip("﻿")
    assert "prev_standard" in header and "bracket_missing" in header
    lines = [x for x in text.splitlines() if ",pending," in x]
    assert lines and all("MISSING_AFTER" in x for x in lines)
    assert any(",manifest," in x for x in text.splitlines())
    assert "kind" in header
    assert "review" not in header


def test_export_marks_origin_and_source_line():
    item, _ = submit_head()
    retest, _ = submit_retest(item)
    from app.exporter import evidence_csv
    text = evidence_csv(store.get(retest["id"]))
    assert "补测" in text and "原始" in text


def test_second_retest_appends_to_latest_child():
    item, _ = submit_head()
    batch = item["result"]["reports"][0]["rows"][0]["batch"]
    first, _ = submit_retest(item)
    tail = f"C7,standard,Pb,1500,100,7,1,ug/L,{batch}\n"
    second, reused = batches.submit({"parent_id": item["id"], "retest": tail})
    assert reused is False
    assert second["parent_id"] == first["id"]
    assert second["result"]["handover"]["verdict"] == "可复核"
    assert all(x["bracket"] == "BRACKETED" for x in second["result"]["final"])
    origin = [x for x in second["result"]["reports"][0]["rows"] if x["origin"] == "补测"]
    assert [(x["sample_id"], x["segment"], x["source_line"]) for x in origin] == [
        ("C6", 1, 2), ("S052", 1, 3), ("C7", 1, 4)]
    assert second["result"]["handover"]["pending_count"] == 0


def test_retry_of_earlier_retest_reuses_anywhere_in_chain():
    item, _ = submit_head()
    batch = item["result"]["reports"][0]["rows"][0]["batch"]
    first, _ = submit_retest(item)
    batches.submit({"parent_id": first["id"], "retest": f"C7,standard,Pb,1500,100,7,1,ug/L,{batch}\n"})
    again, reused = batches.submit({"parent_id": item["id"], "retest": tail_text(batch)})
    assert reused is True and again["id"] == first["id"]
    assert len(store.chain_of(item["id"])) == 3


def test_export_rows_share_one_width():
    import csv
    import io

    item, _ = submit_head()
    store.review(item["id"], item["revision"], "退回", "整批")
    from app.exporter import evidence_csv
    rows = list(csv.reader(io.StringIO(evidence_csv(store.get(item["id"])).lstrip("﻿"))))
    assert len({len(r) for r in rows}) == 1
    assert {"manifest", "pending", "review"} <= {r[3] for r in rows[1:]}
    manifest = next(r for r in rows[1:] if r[3] == "manifest")
    assert "整批等齐" in manifest[-1]
    review = next(r for r in rows[1:] if r[3] == "review")
    assert "整批" in review[-1]
