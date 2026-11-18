import hashlib

from app import store
from app.errors import BusinessError
from app.pipeline import run, sample_text
from app.sequence import merge, retest_rows, tag


def retest_digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def submit(payload):
    text = payload.get("text", sample_text())
    if not isinstance(text, str):
        raise BusinessError("TEXT", "输入须为文本")
    parent_id = payload.get("parent_id")
    if parent_id is None:
        segments = [{"start": 0, "offset": 0}]
        return store.save(text, tag(run(text), segments), segments=segments), False
    if not isinstance(parent_id, str) or not parent_id:
        raise BusinessError("PARENT", "父批次编号须为文本")
    retest = payload.get("retest")
    if retest is None:
        retest = text
    elif not isinstance(retest, str):
        raise BusinessError("RETEST", "补测内容须为文本")
    store.get(parent_id)
    digest = retest_digest(retest)
    existing = store.find_retest(parent_id, digest)
    if existing:
        return existing, True
    base = store.get(store.latest_of(parent_id))
    if not base.get("input"):
        raise BusinessError("PARENT_INPUT", "父批次缺少原始输入，无法拼接补测", 409)
    merged, segments = merge(base["input"], retest, base["segments"])
    result = tag(run(merged), segments)
    if not retest_rows(result):
        raise BusinessError("RETEST_UNUSED", "补测未产生任何采信行，旧版保留")
    return store.save(merged, result, parent_id=base["id"], retest_digest=digest, segments=segments), False
