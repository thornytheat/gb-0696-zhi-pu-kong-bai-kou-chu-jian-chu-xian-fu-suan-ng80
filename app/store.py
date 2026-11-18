import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from app.config import DATA_DIR, RULE_VERSION
from app.errors import BusinessError

SCOPES = {"整批", "可证实部分"}


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / "runs.sqlite", timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, decision TEXT NOT NULL DEFAULT '待复核', created TEXT NOT NULL)")
    columns = {row["name"] for row in db.execute("PRAGMA table_info(runs)")}
    for name, ddl in (("input", "TEXT NOT NULL DEFAULT ''"), ("parent_id", "TEXT NOT NULL DEFAULT ''"), ("retest_digest", "TEXT NOT NULL DEFAULT ''"), ("scope", "TEXT NOT NULL DEFAULT ''"), ("segments", "TEXT NOT NULL DEFAULT ''")):
        if name not in columns:
            db.execute(f"ALTER TABLE runs ADD COLUMN {name} {ddl}")
    db.execute("CREATE TABLE IF NOT EXISTS review_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, revision INTEGER NOT NULL, decision TEXT NOT NULL, scope TEXT NOT NULL, released INTEGER NOT NULL, pending INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '', created TEXT NOT NULL)")
    db.commit()
    return db


def digest_of(text):
    return hashlib.sha256((RULE_VERSION + "\n" + text).encode()).hexdigest()


def save(text, result, parent_id="", retest_digest="", segments=None):
    digest = digest_of(text)
    ident = digest[:16]
    created = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO runs(id,digest,result,revision,decision,created,input,parent_id,retest_digest,segments) VALUES(?,?,?,0,'待复核',?,?,?,?,?)",
            (ident, digest, json.dumps(dict(result, rule_version=RULE_VERSION), ensure_ascii=False), created, text, parent_id, retest_digest, json.dumps(segments or [{"start": 0, "offset": 0}])),
        )
        db.execute("UPDATE runs SET input=? WHERE id=? AND input=''", (text, ident))
    return get(ident)


def get(ident):
    with connect() as db:
        row = db.execute("SELECT * FROM runs WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise BusinessError("NOT_FOUND", "批次不存在", 404)
        events = [dict(e) for e in db.execute("SELECT seq,revision,decision,scope,released,pending,note,created FROM review_events WHERE run_id=? ORDER BY seq", (ident,))]
        children = [dict(c) for c in db.execute("SELECT id,revision,decision,created FROM runs WHERE parent_id=? ORDER BY created", (ident,))]
    item = dict(row)
    item["result"] = json.loads(item["result"])
    item["result"].setdefault("handover", {"verdict": "待重算", "blocked": False, "releasable": False,
                                          "released_count": 0, "pending_count": len(item["result"].get("final", [])), "missing": {}})
    item["rule_version"] = item["result"].get("rule_version", "2026.11.18.1")
    item["segments"] = json.loads(item.get("segments") or '[{"start": 0, "offset": 0}]')
    item["review_events"] = events
    item["retests"] = children
    item["superseded"] = bool(children)
    return item


def history():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT id,parent_id,revision,decision,scope,created FROM runs ORDER BY created DESC LIMIT 40")]


def root_of(ident):
    """沿 parent_id 回溯到原始序列批次。"""
    seen = set()
    current = ident
    with connect() as db:
        while True:
            if current in seen:
                raise BusinessError("PARENT_LOOP", "批次链存在循环", 409)
            seen.add(current)
            row = db.execute("SELECT parent_id FROM runs WHERE id=?", (current,)).fetchone()
            if row is None:
                raise BusinessError("NOT_FOUND", "批次不存在", 404)
            if not row["parent_id"]:
                return current
            current = row["parent_id"]


def chain_of(ident):
    """同一序列的全部批次，按父到子排序。"""
    root = root_of(ident)
    with connect() as db:
        rows = [dict(r) for r in db.execute("SELECT id,parent_id FROM runs ORDER BY rowid")]
    children = {}
    for row in rows:
        children.setdefault(row["parent_id"], []).append(row["id"])
    chain, queue = [], [root]
    while queue:
        current = queue.pop(0)
        chain.append(current)
        queue.extend(children.get(current, []))
    return chain


def latest_of(ident):
    return chain_of(ident)[-1]


def find_retest(parent_id, retest_digest):
    """同一次补测重试不新增结果：整条序列内按补测摘要查找。"""
    with connect() as db:
        for ident in chain_of(parent_id):
            row = db.execute("SELECT id FROM runs WHERE id=? AND retest_digest=? AND retest_digest<>''", (ident, retest_digest)).fetchone()
            if row:
                return get(row["id"])
    return None


def review(ident, revision, decision, scope="整批"):
    if not isinstance(decision, str) or decision not in {"通过", "退回"}:
        raise BusinessError("DECISION", "复核决定无效")
    if not isinstance(scope, str) or scope not in SCOPES:
        raise BusinessError("SCOPE", "复核范围无效")
    current = get(ident)
    if revision != current["revision"]:
        raise BusinessError("STALE", "版本已更新，请刷新", 409)
    handover = current["result"].get("handover") or {}
    released = int(handover.get("released_count", 0))
    pending = int(handover.get("pending_count", 0))
    if decision == "通过":
        if current["result"].get("blocked"):
            raise BusinessError("BLOCKED", "存在阻断项，请先修正数据", 409)
        if scope == "整批" and pending:
            raise BusinessError("SCOPE", "存在未夹持样品，不能整批通过；请选择先交可证实部分或退回等齐", 409)
        if scope == "可证实部分" and not released:
            raise BusinessError("SCOPE", "没有可证实样品，不能放行", 409)
    created = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        changed = db.execute(
            "UPDATE runs SET revision=revision+1,decision=?,scope=? WHERE id=? AND revision=?",
            (decision, scope, ident, revision),
        ).rowcount
        if not changed:
            raise BusinessError("STALE", "版本已更新，请刷新", 409)
        db.execute(
            "INSERT INTO review_events(run_id,revision,decision,scope,released,pending,created) VALUES(?,?,?,?,?,?,?)",
            (ident, revision + 1, decision, scope, released, pending, created),
        )
    return get(ident)
