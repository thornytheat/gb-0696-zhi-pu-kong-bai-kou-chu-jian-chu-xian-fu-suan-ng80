# 深度登记 质谱空白扣除与检出限复算

- 规模：中型
- 核心规则：最小二乘标曲必须满秩，空白扣除保留负值，浓度按稀释倍数复算；低于检出限保留限定符

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 仪器接收 | 运行仪器接收并核对证据 | `POST /api/1` | `app/modules/m1_intake/rules.py` | `tests/test_intake.py` |
| M2 内标归一 | 运行内标归一并核对证据 | `POST /api/2` | `app/modules/m2_internal/rules.py` | `tests/test_internal.py` |
| M3 标曲拟合 | 运行标曲拟合并核对证据 | `POST /api/3` | `app/modules/m3_curve/rules.py` | `tests/test_curve.py` |
| M4 空白扣除 | 运行空白扣除并核对证据 | `POST /api/4` | `app/modules/m4_blank/rules.py` | `tests/test_blank.py` |
| M5 浓度复算 | 运行浓度复算并核对证据 | `POST /api/5` | `app/modules/m5_concentration/rules.py` | `tests/test_concentration.py` |
| M6 质控判定 | 运行质控判定并核对证据 | `POST /api/6` | `app/modules/m6_quality/rules.py` | `tests/test_quality.py` |
| M7 结果复核 | 运行结果复核并核对证据 | `POST /api/7` | `app/modules/m7_review/rules.py` | `tests/test_review.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | GB18030中文 | 静默采信错误值 | 编码回退链 | `app/modules/m1_intake/rules.py` | `tests/test_intake.py::test_intake_encoding` |
| TRAP-05 | 不齐列 | 静默采信错误值 | 列数校验隔离 | `app/modules/m1_intake/rules.py` | `tests/test_intake.py::test_intake_column_isolation` |
| TRAP-06 | 全角与千分位 | 静默采信错误值 | NFKC后Decimal | `app/modules/m2_internal/rules.py` | `tests/test_internal.py::test_internal_fullwidth` |
| TRAP-07 | 空值哨兵 | 静默采信错误值 | 拒绝参与运算 | `app/modules/m2_internal/rules.py` | `tests/test_internal.py::test_internal_sentinel` |
| TRAP-10 | 浮点误差 | 静默采信错误值 | Decimal精确计算 | `app/modules/m2_internal/rules.py` | `tests/test_internal.py::test_internal_decimal_exact` |
| TRAP-14 | 业务键冲突 | 静默采信错误值 | 保留首条并隔离冲突 | `app/modules/m1_intake/rules.py` | `tests/test_intake.py::test_intake_conflicting_key` |
| TRAP-15 | 单位混合 | 静默采信错误值 | 浓度单位归一 | `app/modules/m2_internal/rules.py` | `tests/test_internal.py::test_internal_units` |
| TRAP-19 | 多个质控标记 | 静默采信错误值 | 显式优先级 | `app/modules/m6_quality/rules.py` | `tests/test_quality.py::test_quality_priority` |
| TRAP-20 | 后段标样未到 | 借用相邻或跨批标样，浓度与检出限失真 | 只认同批本项前后标样；未夹持标记并挂起 | `app/modules/m6_quality/rules.py` | `tests/test_bracketing.py` |
| TRAP-21 | 未夹持冒充已校正 | 交接时把参考值当已校正放行 | 检出限无效、不可放行；整批通过被拒 | `app/modules/m7_review/rules.py` | `tests/test_handover.py::test_pending_batch_blocks_whole_review` |
| TRAP-22 | 补测重试重复计数 | 同一补测多次提交产生多版 | 按补测摘要幂等，链内复用 | `app/batches.py` | `tests/test_handover.py::test_retry_of_earlier_retest_reuses_anywhere_in_chain` |
| TRAP-23 | 补测失败覆盖旧版 | 坏补测写库后无法恢复 | 先计算后落库，失败保留旧版 | `app/batches.py` | `tests/test_handover.py::test_failed_retest_keeps_old_version` |
| TRAP-24 | 复核覆盖历史 | 后一次结论抹掉前一次 | 追加不可变 review_events | `app/store.py` | `tests/test_handover.py::test_review_history_is_append_only` |

## 对账规则

输入记录=采信记录+隔离记录+空行；重复记录归隔离；算法输出另记业务单位，不冒充输入行数。金额/浓度/时长使用Decimal；证据含原始行号。

## 已知不覆盖

不支持超过2MB输入，不执行生产自动放行；异常值需人员复核。
