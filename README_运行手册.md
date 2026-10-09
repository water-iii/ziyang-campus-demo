# 午点通 · 资阳校园集运 Demo 运行手册

本项目是本地业务演示系统，不是生产交易平台。所有学校、商家、菜单、订单、金额、退款和交付点均为虚构或待核实数据；没有真实支付、微信、短信、分账或学校系统接口。

## 1. 环境要求

- Windows 10/11
- Python 3.11 或更高版本
- Node.js 20 或更高版本
- Chrome 或 Edge

Python 安装在哪个磁盘都不影响运行。当前开发机使用 `D:\Anaconda\python.exe`，项目依赖安装在根目录 `.venv`，运行时无需把 Anaconda 加入 PATH。

## 2. 首次安装

在项目根目录打开 PowerShell：

```powershell
# 当前开发机可用；其他电脑替换成自己的 Python 路径
& 'D:\Anaconda\python.exe' -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
npm --prefix .\frontend install

Set-Location .\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
Set-Location ..
```

## 3. 一键启动（推荐）

双击根目录 `start_demo.bat`。

脚本会：

1. 检查 Python 虚拟环境、Node.js、前端依赖和端口。
2. 在后台启动 FastAPI（8001）与 React/Vite（5173）。
3. 等待健康检查通过后打开浏览器。
4. 在启动窗口按 Enter 时，只关闭本次脚本创建的两个进程。

访问地址：

- 演示系统：<http://127.0.0.1:5173>
- API 文档：<http://127.0.0.1:8001/docs>
- 日志目录：`logs/`

请不要直接关闭启动窗口后继续重复启动。如果异常退出后提示端口占用，可执行：

```powershell
netstat -ano | Select-String ':8001|:5173'
```

确认是本项目旧进程后，再使用 `Stop-Process -Id <PID>`。

## 4. 手动启动

终端一（项目根目录）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8001
```

终端二（项目根目录）：

```powershell
Set-Location .\frontend
npm run dev
```

分别在两个终端按 `Ctrl+C` 停止。

## 5. 重置为标准演示数据

双击 `reset_demo.bat`：

- 后端正在运行时，通过统一 API 重置。
- 后端未运行时，直接在事务中重置本地 SQLite。
- 重置后固定为 3 家虚拟商户、30 单、34 袋、开放预订状态。

重置会清空当前演示进度，不能恢复；请只对本项目的演示数据库使用。

## 6. 推荐演示顺序

1. 学生端新增一单，切换商家端确认同一订单已经出现。
2. 运营总览截单，再回学生端验证无法新增订单。
3. 三家商家逐单或批量接单，逐袋或批量打包。
4. 司机按 S001 → S002 → S003 逐店核对；第三站可模拟缺一袋。
5. 确认发车；校园端接收实际装车餐袋、分配任务并逐袋或批量交付。
6. 异常中心确认缺袋仍未运输，执行无真实资金动作的模拟退款。
7. 查看班次结案、审计日志和成本面板。

## 7. 自动化验收

双击 `acceptance_test.bat`，或执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_acceptance.ps1
```

验收包括后端/迁移测试、TypeScript、生产构建、旧引擎/UI 回归和双端启动冒烟检查。冒烟检查不会打开浏览器，结束后会关闭自己创建的进程。

测试临时数据库统一创建在项目内的 `.test-runtime/`，不依赖 Windows 用户目录下的 `%TEMP%\pytest-of-*`，可避免公司安全策略、残留目录所有者或系统 Temp 权限造成的 `WinError 5`。

## 8. 数据与安全边界

- SQLite：`backend/data/demo.db`
- 商家范围隔离已在后端实现，但 `X-Demo-Role`/`X-Merchant-Id` 只是演示头，不是真实认证。
- 正式上线前必须另行完成身份认证、授权、学校准入、商户资质、食品安全、温控、保险、支付结算和隐私合规。
- 不要把此 Demo 用于真实订单、收款、退款或学生个人信息。

## 9. 常见问题

### `WinError 10013`

通常表示端口已被旧进程占用。先用 `netstat` 检查，不要反复启动。也可手动改用其他端口，但前端的 `VITE_API_BASE_URL` 需要同步修改。

### 页面显示“后端未连接”

检查 <http://127.0.0.1:8001/api/health>，并查看 `logs/backend.err.log`。

### 前端依赖不存在

```powershell
npm --prefix .\frontend install
```

### 恢复 30 单/34 袋

双击 `reset_demo.bat`，或在页面右上角点击“重置演示”。
