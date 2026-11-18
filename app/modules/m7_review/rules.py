from app.report import report

from app.modules.m6_quality.rules import BLOCKING


def ready(rows, errors):
    return bool(rows) and not errors and not any(r["status"] in BLOCKING for r in rows)


def handover(rows, errors):
    """交接裁决：已夹持且非阻断的样品可先交；未夹持样品单独挂起。

    没被前后标样夹住的样品保留参考值，但不计入已校正、不计入可放行数。
    """
    blocked = not ready(rows, errors)
    released = [r for r in rows if r["releasable"]]
    pending = [r for r in rows if not r["lod_valid"]]
    if blocked:
        verdict = "阻断"
    elif pending and released:
        verdict = "先交可证实部分"
    elif pending:
        verdict = "整批等齐"
    else:
        verdict = "可复核"
    missing = {}
    for r in pending:
        for side in r["bracket_missing"]:
            missing[side] = missing.get(side, 0) + 1
    return {
        "verdict": verdict,
        "blocked": blocked,
        "releasable": len(released) == len(rows) and bool(rows) and not blocked,
        "released_count": len(released),
        "pending_count": len(pending),
        "missing": missing,
    }


def apply(ctx):
    rows = ctx["quality"]
    ctx["final"] = rows
    ctx["blocked"] = not ready(rows, ctx["curve_errors"])
    ctx["handover"] = handover(rows, ctx["curve_errors"])
    excluded = {r["line"] for r in ctx["quarantine"]}
    accepted = ctx["input_count"] - len(excluded) - ctx["blank_rows"]
    ctx["balance"] = {"input": ctx["input_count"], "accepted": accepted, "quarantined": len(excluded), "blank": ctx["blank_rows"]}
    return report(rows, 结论=ctx["handover"]["verdict"], 可证实=ctx["handover"]["released_count"],
                  未夹持=ctx["handover"]["pending_count"], 隔离=len(excluded))
