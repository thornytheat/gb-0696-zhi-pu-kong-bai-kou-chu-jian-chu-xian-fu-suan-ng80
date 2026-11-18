from decimal import Decimal

from app.report import report

BLOCKING = {"OVER_RANGE", "CONTROL_FAIL"}


def classify(value, lod, overrange=False, control_error=None):
    if overrange:return "OVER_RANGE"
    if control_error is not None and control_error>Decimal("0.20"):return "CONTROL_FAIL"
    if value<0:return "NEGATIVE_BLANK"
    if value<lod:return "BELOW_LOD"
    return "PASS"


def _point(row):
    return {"sample_id":row["sample_id"],"line":row["line"],"level":row["level_value"]}


def bracket(row, standards, blanks):
    """按同批同检测项的物理行序找夹住该样品的前后标样与相邻空白。

    只认同批同检测项、且已采信的标样；隔离的标样不参与，不能借来充数。
    """
    line=row["line"]
    before=[s for s in standards if s["line"]<line]
    after=[s for s in standards if s["line"]>line]
    prev=before[-1] if before else None
    nxt=after[0] if after else None
    if prev and nxt:state="BRACKETED"
    elif not prev and not nxt:state="MISSING_BOTH"
    elif not prev:state="MISSING_BEFORE"
    else:state="MISSING_AFTER"
    missing=[label for label,point in (("前标样",prev),("后标样",nxt)) if point is None]
    blank_before=[b for b in blanks if b["line"]<line]
    blank_after=[b for b in blanks if b["line"]>line]
    return {"bracket":state,"bracket_missing":missing,
            "prev_standard":_point(prev) if prev else None,
            "next_standard":_point(nxt) if nxt else None,
            "blank_before":blank_before[-1] if blank_before else None,
            "blank_after":blank_after[0] if blank_after else None}


def apply(ctx):
    out=[]
    for r in ctx["concentrations"]:
        c=ctx["curves"][(r["batch"],r["analyte"])];x=dict(r)
        error=abs(r["concentration"]-r["level_value"])/r["level_value"] if r["kind"]=="control" and r["level_value"] else None
        x["status"]=classify(r["concentration"],r["lod"],r["response"]>c["max_response"],error)
        key=(r["batch"],r["analyte"])
        x.update(bracket(r,ctx["standards"].get(key,[]),ctx["blank_points"].get(key,[])))
        x["lod_valid"]=x["bracket"]=="BRACKETED"
        x["releasable"]=x["lod_valid"] and x["status"] not in BLOCKING
        x["qualifier"]="<" if x["status"]=="BELOW_LOD" else ""
        x["note"]="" if x["lod_valid"] else "未夹持：缺"+"、".join(x["bracket_missing"])+"，浓度与检出限仅为参考"
        out.append(x)
    ctx["quality"]=out
    ctx.pop("standards",None);ctx.pop("blank_points",None)
    return report(out,通过=sum(r["status"]=="PASS" for r in out),
                  未夹持=sum(not r["lod_valid"] for r in out),
                  复核=sum(r["status"]!="PASS" for r in out))
