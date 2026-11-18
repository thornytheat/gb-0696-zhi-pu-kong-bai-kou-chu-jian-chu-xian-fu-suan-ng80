import csv
import io

from app.errors import BusinessError
from app.modules.m1_intake.rules import FIELDS


def _header_cells(line):
    try:
        cells = next(csv.reader(io.StringIO(line), strict=True))
    except (csv.Error, StopIteration):
        raise BusinessError("CSV", "补测内容结构错误")
    return [x.strip() for x in cells]


def merge(original, retest, prior=None):
    """把同一序列的前段与后段补测按物理顺序拼接。

    后段允许带表头；表头与前导空行会被跳过并记入 offset，使 source_line 仍是
    补测文件内的物理行号。原始文本一行不改，旧行号可复核。
    返回拼接文本、分段登记（start 为累计行数，offset 为该段跳过的行数）。
    """
    if not isinstance(retest, str) or not retest.strip():
        raise BusinessError("RETEST_EMPTY", "补测内容为空")
    lines = retest.lstrip("﻿").splitlines()
    skipped = 0
    while lines and not lines[0].strip():
        lines.pop(0)
        skipped += 1
    if not lines:
        raise BusinessError("RETEST_EMPTY", "补测内容为空")
    head = _header_cells(lines[0])
    if len(head) == len(FIELDS) and set(head) == set(FIELDS):
        lines = lines[1:]
        skipped += 1
        while lines and not lines[0].strip():
            lines.pop(0)
            skipped += 1
    if not lines or not any(x.strip() for x in lines):
        raise BusinessError("RETEST_EMPTY", "补测没有数据行")
    body = "\n".join(lines) + "\n"
    base = original
    if base and not base.endswith("\n"):
        base += "\n"
    start = len(base.splitlines())
    segments = list(prior or [{"start": 0, "offset": 0}])
    segments.append({"start": start, "offset": skipped})
    return base + body, segments


def tag(result, segments):
    """按分段登记标注 origin、segment 与各段文件内物理行号。"""
    def mark(row):
        if not isinstance(row, dict):
            return
        line = row.get("line")
        if not isinstance(line, int):
            return
        index = 0
        for position, segment in enumerate(segments):
            if line > segment["start"]:
                index = position
        segment = segments[index]
        row["origin"] = "原始" if index == 0 else "补测"
        row["segment"] = index
        row["source_line"] = line - segment["start"] + segment["offset"]

    for row in result.get("final", []):
        mark(row)
    for row in result.get("quarantine", []):
        mark(row)
    for report in result.get("reports", []):
        for row in report.get("rows", []):
            mark(row)
    return result


def retest_rows(result):
    return sum(1 for row in result.get("reports", [{}])[0].get("rows", []) if row.get("origin") == "补测")
