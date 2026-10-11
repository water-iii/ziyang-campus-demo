# Stage 4.5 履约修正实施与验收

**实施日期**：2026-10-11

**范围**：站点交接时间、延迟出餐、Demo 业务时钟、提前关闭授权、并发订单编号、订单商品快照

**结论**：通过，等待人工验收后再进入 Stage 5

## 1. 修改前基线

首次运行原 `scripts/run_acceptance.ps1` 的结果：

- 后端与迁移测试：5 passed。
- React TypeScript 检查：通过。
- Vite 生产构建：通过。
- 原业务引擎回归：PASS。
- 原静态 UI 回归：PASS。
- 双端冒烟：被已有项目 Uvicorn 占用 `8001` 拦截，因此该次完整脚本退出码为 1；不是代码测试失败。

后续确认 `8001` 和 `5173` 的监听进程都来自本项目，停止旧进程后完成最终全量验收。

## 2. Stage 4.5 实施内容

### 2.1 延迟出餐与部分交接

- `pickup_stops` 分别保存预计到店 `planned_pickup_at` 与最晚交接 `latest_handoff_at`。
- 固定种子为 S001 11:05/11:10、S002 11:15/11:20、S003 11:25/11:25；末站比 11:30 发车早 5 分钟，明确保留装车缓冲。
- 后端拒绝“最晚交接早于预计到店”或“未预留 5 分钟发车缓冲”的错误配置。
- 截止前司机可以勾选核对 `ready` 餐袋，但存在 `pending` 时不能自行关闭交接。
- 截止后司机只能把 `ready` 餐袋确认实装；`pending` 餐袋不能通过勾选或伪造数量绕过打包校验。
- 已打包但现场未装车仍使用原 `missing` 状态和 `merchant_handoff_shortage` 异常。
- 已接单但未完成打包使用新 `pickup_timeout` 状态和 `merchant_preparation_timeout` 异常。
- 截止前如运营明确授权提前关闭，未完成餐袋使用 `pickup_abandoned` 和 `merchant_preparation_early_close`，与自然超时区分。
- 各类未装车餐袋都不会进入 `picked → campus → out → delivered` 链路。
- 异常创建写入 `issue.open` 审计；只有运营角色可调用异常处理，处理时写入 `issue.resolve`，之后才转为演示 `refunded`，且明确 `real_payment_action=false`。
- 司机交接仍要求所有订单已接单、固定线路前序站点已完成、每袋结果完整且站点不能重复交接。

### 2.2 Demo 业务时钟与提前关闭授权

- 新增后端持久化 Demo 时钟，接口为 `GET/PUT/DELETE /api/demo/clock`。
- 路线和交接服务统一调用后端 `business_now()`；前端只能请求设置模拟时间，不能通过修改显示值绕过校验。
- `APP_ENV=demo|test` 时允许时间控制；`staging|production` 下三个时钟接口统一返回 404，业务判断使用服务器真实时间。
- 运营可调用 `POST /api/pickup-stops/{stop_id}/early-close-authorization`，必须填写原因。
- 司机角色不能授权；授权记录保存授权人、原因、业务时间，并写入 `pickup.early_close_authorize` 审计。

### 2.3 并发安全订单编号

- 删除扫描最大订单编号再加一的实现。
- 新订单和新异常使用带前缀的 96-bit UUID 随机标识，数据库主键继续作为最终唯一约束。
- SQLite 写请求在业务读取前执行 `BEGIN IMMEDIATE`，使容量检查、订单写入和审计位于同一串行写事务；连接增加 30 秒 busy timeout。
- 新增 8 路并发下单测试，验证订单 ID、餐袋 ID 均唯一，订单总数正确。

### 2.4 历史订单商品快照

- `order_items` 新增非空 `product_name` 快照，原有 `unit_price` 和 `orders.amount` 继续作为成交价与成交总额快照。
- 创建订单和固定种子都会写入商品名称快照。
- 订单查询不再从当前 `products.name` 读取历史名称。
- 新增 Alembic `0003_order_item_snapshot`：对既有数据先新增可空列、按商品表回填，再收紧非空约束。
- 新增测试验证商品改名、改价、下架后，历史订单名称、成交单价和金额不变。

### 2.5 前端兼容

- 运营总览展示后端业务时间，可模拟推进到某站截止、恢复真实时间或给出提前关闭授权。
- 司机端展示预计到店、最晚交接、已打包和制作中数量。
- 截止前仍可提前勾选已打包餐袋；关闭按钮在截止到达或获得运营授权前保持禁用。
- 交接请求对计划餐袋逐袋给出实装/未装车结果，后端根据原状态区分缺袋与出餐超时。
- 交接完成后显示应取、已取、异常、待取四项数量；已进入运输或配送的餐袋继续计入已取，不会误显示为尚未打包。
- 只有实际存在 `pending` 餐袋时才显示超时/授权提示。
- 异常中心区分“商家交接缺袋”“出餐超时未装车”和“运营提前关闭放弃未完成餐品”。

## 3. 新增自动化测试

| 测试 | 关键断言 |
|---|---|
| `test_concurrent_order_creation_uses_unique_ids` | 8 路并发全部成功；8 个订单 ID 和餐袋 ID 均唯一 |
| `test_order_item_name_price_and_amount_are_historical_snapshots` | 商品改名、改价、下架后历史订单不变 |
| `test_seed_student_order_cutoff_and_normal_fulfillment` | m3 的 9 袋全部打包并正常交接；末站最晚交接早于发车至少 5 分钟 |
| `test_shortage_keeps_unloaded_order_exception_until_resolution` | 9 袋全部打包、实取 8 袋，生成 `merchant_handoff_shortage` |
| `test_seven_of_nine_parcels_timeout_at_stop_deadline_and_require_operations_resolution` | 9 袋中 7 袋打包、2 袋制作中；截止前拒绝且不生成异常；模拟到截止后 7 袋实装、2 袋超时；32 袋正常交付，异常处理后结案 |
| `test_early_close_requires_operations_authorization_and_audit` | 司机无权授权；运营填写原因后才可提前关闭，2 袋记录为 `pickup_abandoned` 并审计 |
| `test_demo_clock_is_disabled_in_production` | production 环境读取、设置、恢复 Demo 时钟均返回 404 |

原正常流程、已打包缺袋、逐袋追踪、权限、重置和迁移测试均继续保留。

## 4. 修正后的异常履约演示流程

1. 重置到固定 30 单/34 袋；m3 固定为 9 个计划餐袋。
2. 运营截单；m3 接单，只完成其中 7 袋打包，保留 2 袋 `pending`。
3. 司机可以提前勾选核对 7 袋，但在 S003 最晚交接时间之前直接提交会返回 409，且不会提前创建异常。
4. 在运营总览点击“模拟到达截止时间”；前端调用后端 Demo 时钟接口，后端业务时间到达 S003 的 `latest_handoff_at`。
5. 司机确认 7 袋实装；2 袋变为 `pickup_timeout`，生成两个 `merchant_preparation_timeout` 异常和审计记录。
6. 全线路完成交接后可以按固定时间发车；只有 `picked` 餐袋到校、分配并交付。
7. 2 袋超时餐袋保持取货异常，不会自动进入配送或退款，班次也不会提前结案。
8. 运营在异常中心逐项给出处置结论；当前 Demo 使用“模拟退款（无真实资金动作）”。全部正常袋已交付且所有异常处理后，班次结案。

如需在截止前放弃未完成餐品，运营必须先在总览填写原因并授权；这类餐袋记录为 `pickup_abandoned`，不会伪装成自然超时或现场缺袋。

## 5. 数据迁移结果

- 已在迁移前备份本地演示库：`backend/data/demo.pre-stage45-20261010-000328.db`（被 `.gitignore` 排除）。
- 时间规则迁移前再次备份：`backend/data/demo.pre-stage45-time-rules-20261011-150906.db`（被 `.gitignore` 排除）。
- 实际演示库已从 `0002_parcel_traceability` 依次升级到 `0003_order_item_snapshot` 和 `0004_pickup_deadlines_clock`。
- 迁移时保留当前演示进度：32 单、37 袋；32 条订单明细商品名称快照完成回填。
- `0004` 回填 S001/S002/S003 最晚交接为 11:10/11:20/11:25，并新增 Demo 时钟与提前关闭授权表。
- 未执行数据重置。自动化测试继续验证重置后固定为 30 单/34 袋。

## 6. 最终真实验收结果

执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_acceptance.ps1
```

结果：

| 检查 | 结果 |
|---|---|
| FastAPI 工作流与 Alembic | 10 passed（2.34s） |
| TypeScript 严格检查 | 通过 |
| Vite 生产构建 | 通过（38 modules，约 0.61s） |
| 原业务引擎回归 | PASS |
| 原静态六视图 UI 回归 | PASS |
| 后端 8001 / 前端 5173 启动与健康检查 | 通过 |
| 冒烟结束后的测试进程回收 | 通过 |
| 完整验收脚本退出码 | 0 |

非阻断警告：FastAPI TestClient 提示未来迁移到 `httpx2`；当前 Windows `.pytest_cache` 目录权限产生缓存写入警告。两者均未影响 10 项测试和完整验收结果。

## 7. 改动文件

- 后端：`backend/app/main.py`、`database.py`、`models.py`、`schemas.py`、`services.py`、`api.py`、`seed.py`
- 迁移：`backend/alembic/versions/0003_order_item_snapshot.py`、`0004_pickup_deadlines_clock.py`
- 测试：`backend/tests/test_workflows.py`、`backend/tests/test_migrations.py`
- 前端：`frontend/src/api.ts`、`types.ts`、`pages/DashboardPage.tsx`、`DriverPage.tsx`、`IssuesPage.tsx`、`MerchantPage.tsx`
- 文档：`README.md`、`backend/README.md`、`frontend/README.md`、本报告、`STAGE5_技术实施方案.md`

## 8. 现有架构风险

- `X-Demo-Role` 等请求头仍只是演示隔离，且默认角色是 operations；应用不能直接暴露公网。Stage 5 必须先完成真实认证并默认拒绝未认证访问。
- SQLite 通过单写锁改善本地并发，但不适合作为正式多实例运营数据库；生产建议 PostgreSQL。
- 站点时间目前仍来自固定演示种子；未来正式运营需要可配置班次模板、线路实测和时区策略。
- 提前关闭授权当前是一站一次的 Demo 记录，没有审批流、撤销、双人复核或通知机制。
- Demo 时钟保存在本地数据库且只适用于 `demo/test`；部署时必须显式设置 `APP_ENV=production`，不能依赖默认值。
- 早期 Alembic 迁移引用当前 ORM 元数据，历史结构可重复性不足；Stage 5 应改为冻结的显式 DDL 迁移。
- UUID 订单号不再按数字连续递增；任何报表和前端都不应依赖订单 ID 的自然排序表达创建顺序。
- 当前异常处置仍只有模拟退款一种结果，不代表真实资金操作或完整售后状态机。

Stage 4.5 到此停止。Stage 5 仅提供设计文档，尚未实施。
