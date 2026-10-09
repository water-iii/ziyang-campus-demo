# Stage 1 后端运行手册

本目录是《资阳校园集运 Demo v0.1》的 FastAPI + SQLAlchemy + SQLite 后端。它只用于本地演示，不连接真实支付、退款、微信、短信、学校或商家系统。请求头 `X-Demo-Role` 只是演示流程隔离，不是真实身份认证。

## Windows 首次安装

在项目根目录打开 PowerShell：

```powershell
# 如果 Python 已加入 PATH
py -3.13 -m venv .venv

# 当前开发机也可以直接使用 D 盘解释器
# & 'D:\Anaconda\python.exe' -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

Python 安装在哪个盘没有影响；关键是用解释器绝对路径或把它加入 PATH。依赖只安装在项目根目录的 `.venv` 中。

## 启动后端（端口 8001）

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8001
```

- 健康检查：<http://127.0.0.1:8001/api/health>
- Swagger API 文档：<http://127.0.0.1:8001/docs>
- SQLite 文件：`backend/data/demo.db`

应用首次启动会自动建表并填充 30 单/34 袋。也可以从 `backend` 目录运行 Alembic：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
Set-Location ..
```

当前迁移版本为 `0002_parcel_traceability`。已有 Stage 1 数据库也应执行上述命令，以增加逐袋交接和逐袋配送追踪表。

## 启动 Stage 2 React 前端

保持后端运行，打开另一个 PowerShell：

```powershell
Set-Location .\frontend
npm install
npm run dev
```

然后访问 <http://127.0.0.1:5173>。该前端的所有状态操作均调用 8001 端口 API。

## 启动原静态前端（仅作回归）

Stage 1 刻意保留原静态 Demo，不让它半迁移。可以双击根目录 `index.html`，或在另一个 PowerShell 窗口运行：

```powershell
.\.venv\Scripts\python.exe -m http.server 8000
```

然后访问 <http://127.0.0.1:8000>。这是未接后端的旧版静态原型，仅用于视觉和业务规则对照。

## 重置演示数据

```powershell
$headers = @{ 'X-Demo-Role' = 'operations'; 'X-Demo-Actor' = 'local-demo' }
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8001/api/demo/reset' -Headers $headers
```

响应中的 `orders=30`、`parcels=34`、`merchants=3` 表示重置成功。

## 自动化测试

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest .\backend\tests -q
node .\test_engine.cjs
node .\test_ui.cjs
```

后端测试使用独立临时 SQLite 文件，不会修改 `backend/data/demo.db`。

## 演示角色请求头

| 角色 | `X-Demo-Role` | 说明 |
|---|---|---|
| 学生 | `student` | 创建模拟订单 |
| 商家 | `merchant` | 还需 `X-Merchant-Id: m1/m2/m3`，仅能访问本店工作台 |
| 城区司机 | `driver` | 逐站交接、发车 |
| 校园负责人 | `campus` | 到校接收、分配、完成交付 |
| 运营 | `operations` | 截单、异常处理、审计、重置 |

所有写接口都具备后端状态校验；可发送 `Idempotency-Key` 获得同一操作的安全重放。即使不发送幂等键，重复交接、重复发车和重复模拟退款也会被状态机拒绝。
