import { useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Chip, Empty, PageHeading, dateTime, money } from '../components'
import type { PageProps } from '../App'
import type { AuditLog, Issue } from '../types'

export function IssuesPage({ summary, merchants, revision, refresh, notify }: PageProps) {
  const [issues, setIssues] = useState<Issue[]>([])
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [fixedCost, setFixedCost] = useState(summary.economics.fixed_cost)
  const [busy, setBusy] = useState('')

  async function load() {
    try {
      const [nextIssues, nextLogs] = await Promise.all([api.getIssues(), api.getAuditLogs()])
      setIssues(nextIssues)
      setLogs(nextLogs)
      setFixedCost(summary.economics.fixed_cost)
    } catch (error) {
      notify(error instanceof Error ? error.message : '异常中心加载失败。', true)
    }
  }

  useEffect(() => {
    void load()
  }, [revision])

  async function resolve(issueId: string) {
    setBusy(issueId)
    try {
      await api.resolveIssue(issueId)
      await refresh()
      await load()
      notify('异常已模拟退款并留痕；没有发生真实资金动作。')
    } catch (error) {
      notify(error instanceof Error ? error.message : '异常处理失败。', true)
    } finally {
      setBusy('')
    }
  }

  async function saveCost() {
    setBusy('cost')
    try {
      await api.updateFixedCost(fixedCost)
      await refresh()
      notify('模拟固定成本已保存到后端。')
    } catch (error) {
      notify(error instanceof Error ? error.message : '成本更新失败。', true)
    } finally {
      setBusy('')
    }
  }

  const openCount = issues.filter((issue) => issue.status === 'open').length
  return (
    <>
      <PageHeading eyebrow="QUALITY / ECONOMICS" title="异常与经营核算" description="异常、模拟退款、成本和审计记录均持久化在后端。" />
      <div className="layout-main">
        <div>
          <section className="card">
            <div className="card-title"><h3>履约异常处理</h3><Chip type={openCount ? 'red' : 'green'}>{openCount} 项待处理</Chip></div>
            {issues.length ? issues.map((issue) => <div className="issue" key={issue.id}><div className="two-between"><strong>{issue.id} · 商家交接缺袋</strong><Chip type={issue.status === 'open' ? 'red' : 'green'}>{issue.status === 'open' ? '待处理' : '已结案'}</Chip></div><p>商家：{merchants.find((item) => item.id === issue.merchant_id)?.name}　订单：{issue.order_id}　餐袋：{issue.parcel_id}</p><p>记录时间：{dateTime(issue.created_at)}</p>{issue.status === 'open' ? <Button kind="danger" small disabled={busy === issue.id} onClick={() => void resolve(issue.id)}>标记为模拟退款并结案</Button> : <div className="banner-soft">处理结论：{issue.resolution} · {issue.resolved_at ? dateTime(issue.resolved_at) : ''}</div>}</div>) : <Empty title="目前没有异常" text="可在司机端第三站选择“模拟缺1袋并交接”。" />}
            <div className="banner-pink mt16">此处只有模拟退款状态，不会转账、扣费或影响真实消费者。</div>
          </section>
          <section className="card"><div className="card-title"><h3>业务审计记录</h3><small>最新操作优先</small></div><ul className="log-list">{logs.map((log) => <li key={log.id}><span className="log-time">{dateTime(log.created_at)}</span><span className="log-msg"><strong>{log.action}</strong> · {log.actor_role}/{log.actor_id} · {log.entity_id}</span></li>)}</ul></section>
        </div>
        <div>
          <section className="card">
            <div className="card-title"><h3>单班经济模型</h3><Chip type="blue">参数化假设</Chip></div>
            <table className="financial-table"><tbody><tr><td>模拟订单量</td><td>{summary.counts.orders} 单</td></tr><tr><td>餐品成交额（模拟）</td><td>{money(summary.economics.food_amount)}</td></tr><tr><td>收入小计</td><td>{money(summary.economics.revenue)}</td></tr><tr><td>订单变动成本</td><td>− {money(summary.economics.variable_cost)}</td></tr><tr><td>固定取货/干线/分拣成本</td><td>− {money(summary.economics.fixed_cost)}</td></tr><tr><td>班次贡献估算</td><td className={summary.economics.contribution < 0 ? 'red-text' : 'green-text'}>{money(summary.economics.contribution)}</td></tr></tbody></table>
            <div className="field"><label htmlFor="fixed-cost">调整每班固定成本（元）</label><input id="fixed-cost" type="number" min="0" max="2000" step="5" value={fixedCost} onChange={(event) => setFixedCost(Number(event.target.value))} /></div><Button kind="outline" block disabled={busy === 'cost'} onClick={() => void saveCost()}>保存模拟成本</Button>
            <div className="financial-callout">本模型未完整纳入获客、管理工资、保险和设备折旧，不能作为投资或盈利承诺。</div>
          </section>
          <section className="card"><div className="card-title"><h3>关键验收点</h3></div><ul className="notice-list"><li>未装车餐袋不进入运输状态</li><li>未解决异常时班次不结案</li><li>模拟退款不连接任何支付接口</li><li>刷新页面后数据从 SQLite 恢复</li></ul></section>
        </div>
      </div>
    </>
  )
}
