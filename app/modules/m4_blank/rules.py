from statistics import median
from app.report import report,quarantine
from decimal import Decimal

def corrected(response,curve,blank):
    return (response-curve["intercept"])/curve["slope"]-blank

def apply(ctx):
    blanks={};blank_points={}
    for r in ctx["normalized"]:
        key=(r["batch"],r["analyte"]);c=ctx["curves"].get(key)
        if c and r["kind"]=="blank":
            conc=(r["response"]-c["intercept"])/c["slope"]
            blanks.setdefault(key,[]).append(conc)
            blank_points.setdefault(key,[]).append({"line":r["line"],"sample_id":r["sample_id"],"concentration":conc})
    for points in blank_points.values():points.sort(key=lambda p:p["line"])
    ctx["blank_points"]=blank_points
    ctx["blanks"]={k:median(v) for k,v in blanks.items()};out=[]
    for r in ctx["normalized"]:
        if r["kind"] not in {"sample","control"}:continue
        key=(r["batch"],r["analyte"]);curve=ctx["curves"].get(key)
        if not curve:quarantine(ctx,r,"CURVE_MISSING");continue
        if key not in ctx["blanks"]:quarantine(ctx,r,"BLANK_MISSING");continue
        x=dict(r);x["net"]=corrected(r["response"],curve,ctx["blanks"][key]);out.append(x)
    ctx["corrected"]=out
    return report(out,样品=len(out),空白组=len(blanks))
