import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Button, Chip } from './components'
import { CampusPage } from './pages/CampusPage'
import { DashboardPage } from './pages/DashboardPage'
import { DriverPage } from './pages/DriverPage'
import { IssuesPage } from './pages/IssuesPage'
import { MerchantPage } from './pages/MerchantPage'
import { StudentPage } from './pages/StudentPage'
import type { BatchSummary, Merchant } from './types'

export type PageId = 'dashboard' | 'student' | 'merchant' | 'driver' | 'campus' | 'issues'

export interface PageProps {
  summary: BatchSummary
  merchants: Merchant[]
  revision: number
  refresh: () => Promise<void>
  notify: (message: string, error?: boolean) => void
  navigate: (page: PageId) => void
}

const navigation: Array<{ page: PageId; icon: string; name: string }> = [
  { page: 'dashboard', icon: '▦', name: '运营总览' },
  { page: 'student', icon: '◉', name: '学生下单端' },
  { page: 'merchant', icon: '▤', name: '商家工作台' },
  { page: 'driver', icon: '↗', name: '城区司机端' },
  { page: 'campus', icon: '⌂', name: '校园交付端' },
  { page: 'issues', icon: '◇', name: '异常与成本' },
]

export default function App() {
  const [page, setPage] = useState<PageId>('dashboard')
  const [summary, setSummary] = useState<BatchSummary | null>(null)
  const [merchants, setMerchants] = useState<Merchant[]>([])
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [connectionError, setConnectionError] = useState('')
  const [toast, setToast] = useState<{ message: string; error: boolean } | null>(null)

  const notify = useCallback((message: string, error = false) => {
    setToast({ message, error })
    window.setTimeout(() => setToast(null), 3500)
  }, [])

  const loadBase = useCallback(async () => {
    setLoading(true)
    try {
      const [nextSummary, nextMerchants] = await Promise.all([api.getSummary(), api.getMerchants()])
      setSummary(nextSummary)
      setMerchants(nextMerchants)
      setConnectionError('')
      setRevision((value) => value + 1)
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : '无法连接后端。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadBase()
  }, [loadBase])

  const currentName = useMemo(() => navigation.find((item) => item.page === page)?.name || '', [page])

  async function resetDemo() {
    if (!window.confirm('确定恢复到30笔、34袋初始演示数据吗？当前后端履约进度会清空。')) return
    try {
      const result = await api.reset()
      localStorage.removeItem('ziyang-stage2-order-ids')
      await loadBase()
      setPage('dashboard')
      notify(`已重置：${result.orders}单 / ${result.parcels}袋。`)
    } catch (error) {
      notify(error instanceof Error ? error.message : '重置失败。', true)
    }
  }

  function navigate(next: PageId) {
    setPage(next)
    window.scrollTo(0, 0)
  }

  const sharedProps = summary
    ? { summary, merchants, revision, refresh: loadBase, notify, navigate }
    : null

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">午</div>
          <div><strong>午点通</strong><small>CAMPUS LUNCH SHUTTLE</small></div>
        </div>
        <div className="side-tag"><i className="tag-dot" /> React + API 持久化演示</div>
        <div className="side-section-label">工作台切换</div>
        <nav>
          {navigation.map((item) => (
            <button
              key={item.page}
              className={`nav-link ${page === item.page ? 'active' : ''}`}
              onClick={() => navigate(item.page)}
            >
              <span className="ico">{item.icon}</span>{item.name}
              {item.page === 'issues' && summary?.counts.open_issues ? (
                <span className="nav-count">{summary.counts.open_issues}</span>
              ) : null}
            </button>
          ))}
        </nav>
        <div className="side-bottom">
          <div className="side-note">
            <strong>演示角色切换 ≠ 真实登录</strong>
            <span>每次操作通过统一后端 API 执行。正式上线仍需独立建设身份认证与权限体系。</span>
          </div>
          <p>学校准入、交付点与商户均待核实</p>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <span className="crumb">午点通 / <span>{currentName}</span></span>
            <span className="demo-pill"><i /> 本地演示 · 非真实交易</span>
          </div>
          <div className="topbar-right">
            <span className="date-info">API：127.0.0.1:8001</span>
            <Button kind="ghost" small onClick={() => void resetDemo()}>重置演示</Button>
          </div>
        </header>

        <main className="main">
          {loading && !summary ? <div className="card loading-panel">正在读取后端数据…</div> : null}
          {connectionError && !summary ? (
            <section className="card connection-panel">
              <Chip type="red">后端未连接</Chip>
              <h2>无法读取 8001 端口的业务数据</h2>
              <p>{connectionError}</p>
              <code>.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8001</code>
              <div className="mt16"><Button onClick={() => void loadBase()}>重新连接</Button></div>
            </section>
          ) : null}
          {sharedProps && page === 'dashboard' ? <DashboardPage {...sharedProps} /> : null}
          {sharedProps && page === 'student' ? <StudentPage {...sharedProps} /> : null}
          {sharedProps && page === 'merchant' ? <MerchantPage {...sharedProps} /> : null}
          {sharedProps && page === 'driver' ? <DriverPage {...sharedProps} /> : null}
          {sharedProps && page === 'campus' ? <CampusPage {...sharedProps} /> : null}
          {sharedProps && page === 'issues' ? <IssuesPage {...sharedProps} /> : null}
        </main>
        <footer className="footer">午点通 · 资阳校园集运 Demo v0.1　｜　全部数据为虚构测试数据，不构成真实服务承诺</footer>
      </div>
      {toast ? <div className={`toast show ${toast.error ? 'error' : ''}`}>{toast.message}</div> : null}
    </div>
  )
}
