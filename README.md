# 午点通｜资阳校园午餐集运 Demo

一个用于验证“城区商家集中取餐 → 干线运输 → 校园交接配送”业务闭环的本地交互 Demo。项目包含可持久化的 FastAPI 后端、React 管理界面、SQLite 数据库、Alembic 迁移和自动化验收脚本。

> 本项目仅供产品与技术演示。商家、订单、金额、学校和交付地点均为虚构或待核实数据；不包含真实支付、退款、身份认证或学校系统接口，不能直接用于生产运营。

## 已实现能力

- 学生、商家、城区司机、校园负责人、运营五类演示视角
- 固定午餐班次的下单、截单、接单、打包、逐袋交接、发车、到校与配送
- 缺袋异常留痕、模拟退款、班次结案、审计日志与成本面板
- 后端状态机、角色范围隔离、幂等操作和 SQLite 持久化
- 固定演示种子：3 家商户、30 笔订单、34 个餐袋
- 后端测试、数据库迁移、TypeScript、生产构建和双端冒烟验收

## 技术栈

- 前端：React 19、TypeScript、Vite
- 后端：FastAPI、SQLAlchemy、Pydantic
- 数据：SQLite、Alembic
- 测试：Pytest、Node.js 回归脚本、PowerShell 集成验收

## 目录说明

```text
backend/              FastAPI 应用、数据模型、迁移和测试
frontend/             React + TypeScript 正式 Demo 前端
scripts/              Windows 启动、重置和验收脚本
index.html/app.js/... 原静态原型，保留用于视觉和业务回归
PRD_*.md              产品需求文档
STAGE*.md             各阶段实施与验收记录
```

## Windows 快速开始

环境要求：Python 3.11+、Node.js 20+、Chrome 或 Edge。Python 安装在哪个磁盘都可以。

首次安装：

```powershell
# 也可以把 py -3.13 替换为本机 Python 解释器的绝对路径
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
npm --prefix .\frontend install

Set-Location .\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
Set-Location ..
```

安装完成后双击 `start_demo.bat`，或在项目根目录运行：

```powershell
.\start_demo.bat
```

启动后访问：

- Demo 前端：<http://127.0.0.1:5173>
- API 文档：<http://127.0.0.1:8001/docs>
- 健康检查：<http://127.0.0.1:8001/api/health>

## 重置与验收

```powershell
# 恢复为 30 单 / 34 袋的标准演示数据
.\reset_demo.bat

# 执行后端、迁移、类型检查、生产构建、旧版回归和双端冒烟测试
.\acceptance_test.bat
```

当前集成验收结论为通过；详细结果见 [STAGE4 集成验收报告](./STAGE4_集成验收报告.md)。

## 推荐阅读顺序

1. [产品需求文档](./PRD_资阳校园集运Demo_v0.1.md)
2. [运行手册](./README_运行手册.md)
3. [Stage 0 技术计划与差距](./STAGE0_技术实施计划与差距.md)
4. [Stage 3 实施与验收](./STAGE3_实施与验收.md)
5. [Stage 4 集成验收报告](./STAGE4_集成验收报告.md)
6. [后端说明](./backend/README.md)与[前端说明](./frontend/README.md)

## 安全边界

`X-Demo-Role`、`X-Merchant-Id` 等请求头只用于本地演示，不是真实认证机制。正式上线前还需要另行完成身份认证与授权、学校准入、商户资质、食品安全与温控、保险、支付结算及隐私合规。本仓库不应提交 `.venv`、`node_modules`、本地数据库、日志或环境变量文件；这些内容已写入 `.gitignore`。
