# 深度登记 · 雪后清道核量台

- 规模：中型
- 核心规则：按方向及有效作业窗口做线性里程区间并集，覆盖优先于有界缺证。结算按区间归属裁定：自营凭线路册责任班组与车辆名册，跨班组凭支援单；未核清只列待复核。
- 使用者：养护夜班领班按方向复核除雪里程，交接未扫路段与疑似定位缺口。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 线路册 | 确认可采信的责任方向 | `GET /api/routes/{sample}` | `app/modules/m1_routes/service.py` | `tests/test_routes.py` |
| M2 车辆轨迹 | 审查采集顺序、重传与冲突 | `GET /api/tracks/{sample}` | `app/modules/m2_tracks/service.py` | `tests/test_tracks.py` |
| M3 里程投影 | 查看可信桩位与偏移 | `GET /api/projection/{sample}` | `app/modules/m3_projection/service.py` | `tests/test_projection.py` |
| M4 清扫窗口 | 查看按时段、方向及铲位采信的轨迹段 | `GET /api/windows/{sample}` | `app/modules/m4_windows/service.py` | `tests/test_windows.py` |
| M5 覆盖合并 | 展开覆盖、待扫及缺证区间的证据 | `GET /api/coverage/{sample}` | `app/modules/m5_coverage/sweep.py` | `tests/test_coverage.py` |
| M6 缺扫对账 | 查逐方向差额及全部判定记录 | `GET /api/reconcile/{sample}` | `app/modules/m6_reconcile/ledger.py` | `tests/test_reconcile.py` |
| M7 工单凭证 | 重算、签收并下载冻结证据 | `POST /api/runs` | `app/modules/m7_archive/service.py` | `tests/test_archive.py` |
| M8 班组结算 | 裁定分段归属，形成可结算量与待复核清单 | `GET /api/settle/{sample}` | `app/modules/m8_settle/service.py` | `tests/test_settle.py` |

## 陷阱登记

| 陷阱 | 现象 | 朴素结果 | 处理 | 实现 | 测试 |
|---|---|---|---|---|---|
| TRAP-07 | 脏样例坐标为未知 | 错认原点 | 隔离原值 | `app/modules/m2_tracks/contract.py` | `tests/test_tracks.py::test_sentinel_is_quarantined` |
| TRAP-10 | 窗口裁切出分数米 | 多计边缘 | 分数精确裁切并向内取整 | `app/modules/m4_windows/intervals.py` | `tests/test_windows.py::test_exact_conservative_rounding` |
| TRAP-11 | 脏样例不同偏移同秒重传 | 重复采信 | UTC 秒去重 | `app/modules/m2_tracks/service.py` | `tests/test_tracks.py::test_duplicate_at_same_instant_across_offsets` |
| TRAP-13 | 脏样例补发早先消息 | 丢失原记录 | 排序后处理且保留原行 | `app/modules/m2_tracks/service.py` | `tests/test_tracks.py::test_late_samples_are_sorted` |
| TRAP-14 | 线路同键范围冲突 | 后写覆盖 | 两条都进隔离 | `app/modules/m1_routes/service.py` | `tests/test_routes.py::test_conflicting_definitions_all_quarantined` |
| TRAP-18 | 输入无责任方向 | 空批次也对平 | 需要复核 | `app/modules/m6_reconcile/service.py` | `tests/test_reconcile.py::test_empty_ledger_has_explicit_state` |
| TRAP-19 | 脏样例两车重复经过同向区间 | 重复累计 120 米 | 按区间并集计量 | `app/modules/m5_coverage/sweep.py` | `tests/test_coverage.py::test_two_vehicles_overlap_only_once` |
| TRAP-21 | 轨迹引用未登记的反向道路 | 借用顺向资料 | 隔离对应端点 | `app/modules/m3_projection/service.py` | `tests/test_projection.py::test_unknown_direction_does_not_borrow_axis` |
| TRAP-23 | 临界时刻恰好接触窗口 | 增加虚假交集 | 半开窗口边界 | `app/modules/m4_windows/intervals.py` | `tests/test_windows.py::test_half_open_contact_has_no_distance` |
| TRAP-25 | 脏样例两作业窗口重叠 | 同段两次采信 | 时间窗口归并 | `app/modules/m4_windows/service.py` | `tests/test_windows.py::test_windows_unioned_without_doubling` |
| TRAP-26 | 签收提交带陈旧摘要 | 签错快照 | 返回冲突 | `app/modules/m7_archive/service.py` | `tests/test_archive.py::test_signature_requires_current_digest` |
| TRAP-27 | 外援无支援单在本区作业 | 按车辆毛里程计费 | 只列待复核，不计结算 | `app/modules/m8_settle/attribute.py` | `tests/test_settle.py::test_support_without_dispatch_goes_to_review` |
| TRAP-28 | 同一区间多班组覆盖 | 随意归属一方 | 归属冲突待裁定 | `app/modules/m8_settle/attribute.py` | `tests/test_settle.py::test_shared_interval_attribution_conflict` |
| TRAP-29 | 名册同键定义冲突 | 后写覆盖 | 冲突双方皆隔离 | `app/modules/m8_settle/registry.py` | `tests/test_settle.py::test_conflicting_vehicle_registry_quarantined` |
| TRAP-30 | 同批重跑或断点续跑 | 重复计价或改归属 | 内容寻址复用，已核归属不变 | `app/modules/m7_archive/service.py` | `tests/test_settle.py::test_rerun_keeps_verified_attribution` |
