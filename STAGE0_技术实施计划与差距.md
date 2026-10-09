# Stage 0 技术实施计划与差距

## 现状结论

当前项目是一套可直接在浏览器运行的中文静态交互 Demo。`engine.js` 已实现 30 单/34 袋种子、学生下单、运营截单、三店接单打包、司机按序取货、缺袋异常、发车、到校、末端交付、模拟退款和成本测算；`app.js` 将同一份浏览器内状态渲染到六个工作台，并用 `localStorage` 持久化。现有测试覆盖主要正常与缺袋路径，适合作为后端迁移时的业务基准。

Stage 0 已运行 `node test_engine.cjs`，结果通过：`PASS: seed 30 orders / 34 parcels; student ordering, cutoff, merchant packing, route order, full delivery, shortage exception, refund, cost.` 原有 `index.html`、`app.js`、`engine.js`、`styles.css` 和测试文件在 Stage 0/1 保持不变。

## Stage 1 实施计划

1. 在独立 `backend/` 目录建立 FastAPI 应用，使用 SQLAlchemy 2.x 和 SQLite；提供 Alembic 初始迁移，开发环境可自动建库，正式迁移命令仍可复现数据库结构。
2. 将 School、DeliveryPoint、Merchant、Product、Batch、Order、OrderItem、Parcel、PickupRoute、PickupStop、PickupHandoff、DeliveryTask、Issue、CostRecord、AuditLog 分表建模；订单、餐袋、班次和异常状态互不替代。
3. 提供统一 REST API：演示重置与摘要、商家和商品查询、学生下单、截单、商家接单/打包、路线与逐站交接、发车、到校清点、配送分配/完成、异常查询/模拟退款、审计查询。
4. 所有变更在服务端事务内执行。状态机拒绝越序操作；`Idempotency-Key` 保存操作结果并防止重复提交；每次成功变更写入审计记录。演示角色头仅用于流程隔离，明确不是真实登录认证。
5. 固定种子恢复 3 家虚拟商户、30 单、34 袋、B001 班次和 R001 路线。缺袋只改变未装车餐袋，发车不会把异常餐袋推进运输状态；有未结异常时班次不能结束。
6. 使用 pytest + FastAPI TestClient 覆盖正常闭环、截单拒绝新单、缺袋闭环、路线越序、重复交接/重复退款和幂等键重放；保留并再次执行原 Node 测试，证明 Stage 1 未破坏静态 Demo。

## 与目标的主要差距

| 领域 | 当前静态 Demo | Stage 1 目标 | 后续阶段仍需完成 |
|---|---|---|---|
| 数据权威 | 浏览器 `localStorage` | SQLite 单一数据源、事务更新 | Stage 2 前端接入 API |
| 技术栈 | 原生 JS/CSS/HTML | FastAPI + SQLAlchemy + Alembic | React + TypeScript + Vite |
| 数据模型 | 单个嵌套对象 | 核心实体分表、外键约束 | 更细的交付凭证/扫码字段 |
| 状态校验 | 浏览器函数校验 | 后端状态机和 HTTP 冲突响应 | 更完整的人工审核策略 |
| 重复提交 | 按钮禁用和局部判断 | 幂等键 + 唯一约束 + 状态检查 | 分布式部署时的并发策略 |
| 权限 | 左侧角色切换，无认证 | 演示角色头和商家范围隔离 | Stage 3 的真实认证/授权设计 |
| 审计 | 文本事件数组 | 持久化 AuditLog | 查询筛选、导出和留存策略 |
| 异常 | 缺袋与模拟退款 | 关联订单/餐袋/商家并留痕 | 部分退款、补送、改班规则 |
| 运行 | 双击 HTML | 后端独立启动与 API 文档 | Stage 4 一键联调启动 |
| 外部能力 | 无 | 仍然无真实支付/短信/微信 | 上线前另行合规建设，不属于 Demo |

学校准入、真实交付点、真实商户、线路时长、温控和经营责任等仍是线下待核实项；代码和种子数据不会把这些占位信息表达为已获授权的事实。
