# Stage 2 React 前端

这是连接 FastAPI/SQLite 后端的正式 Demo 前端。原根目录静态 Demo 保留不变，用于视觉和业务回归。

## Windows 启动

先在项目根目录启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8001
```

再打开第二个 PowerShell：

```powershell
Set-Location .\frontend
npm install
npm run dev
```

浏览器访问 <http://127.0.0.1:5173>。API 文档仍位于 <http://127.0.0.1:8001/docs>。

Stage 3 已支持商家逐单接单/逐袋打包、司机逐袋勾选实装与缺袋、校园逐袋确认交付；批量按钮仍保留用于快速演示。

Stage 4.5 为每个站点分别显示预计到店和最晚交接时间。司机可以提前勾选核对已打包餐袋，但截止前关闭交接必须先由运营填写原因并授权；到达截止后，制作中的餐袋会生成“出餐超时”异常。运营总览还提供后端 Demo 业务时钟控制，便于无需等待真实时间完成验收。

如果需要修改后端地址，在 `frontend` 目录新建 `.env.local`：

```text
VITE_API_BASE_URL=http://127.0.0.1:8001/api
```

## 构建检查

```powershell
Set-Location .\frontend
npm run typecheck
npm run build
```

页面中的角色切换只是演示。虽然请求按学生、商家、司机、校园和运营角色发送，仍不具备可用于真实上线的身份认证。
