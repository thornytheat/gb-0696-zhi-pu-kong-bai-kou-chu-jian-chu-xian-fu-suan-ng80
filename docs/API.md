# 接口

`POST /api/run`：{"text":"CSV内容"}。同规则版本与输入摘要只产生一条批次。

补测：{"parent_id":"批次","retest":"后段CSV"}。按物理顺序接在该序列最新批次之后重新计算，返回新批次；
同一段补测重复提交返回已有结果并带 `X-Retest-Reused: 1`，不新增结果。补测没有任何采信行时返回409，旧版保留。
也可用 {"parent_id":"批次","text":"后段CSV"}；仅给出 text 而无 parent_id 即新批次。

`GET/POST /api/1` 至 `/api/7`：独立样例或自定义文件计算。各模块返回 report、quarantine、balance。

`POST /api/review`：id、整数revision、decision取通过或退回，scope取整批或可证实部分（缺省整批）。
旧版本409；阻断项不能通过；有未夹持样品时整批通过409；可证实部分须确有可放行样品。
复核成功追加一条不可变事件，响应 `review_events` 可查全部历史。

`GET /api/export/{id}`：唯一证据CSV。`GET /health`：存活检查。

错误：结构/数值422，版本冲突409，不存在404，文件过大413。逐行异常进入quarantine。
