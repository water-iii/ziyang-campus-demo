import { useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Chip, PageHeading, StatusChip, dateTime, money, time } from '../components'
import type { PageProps } from '../App'
import type { AuditLog, PickupRoute } from '../types'

const statusOrder = ['open', 'cutoff', 'collecting', 'transit', 'campus', 'delivering', 'finished'] as const
const steps = [
  ['开放预订 / 学生模拟下单', '选择单店餐品和演示交接点。'],
  ['10:40 截单 / 商家集中备餐', '锁定本班订单并生成出餐清单。'],
  ['城区逐店取货', '梅西两站、达高一站，逐店核对餐袋。'],
  ['11:30 计划发车', '仅实际装车餐袋进入干线运输。'],
  ['校门许可交接点清点', '地点仅示意，尚未经校方确认。'],
  ['校园末端配送', '按预先配置的交付点分配任务。'],
  ['班次结案', '所有餐袋完成交付或有售后处理结论。'],
]

export function DashboardPage({ summary, merchants, revision, refresh, notify, navigate }: PageProps) {
  const [route, setRoute] = useState<PickupRoute | null>(null)
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [busy, setBusy] = useState(false)
  const stage = statusOrder.indexOf(summary.batch.status)

  useEffect(() => {
    void Promise.all([api.getRoute(), api.getAuditLogs()])
      .then(([nextRoute, nextLogs]) => {
        setRoute(nextRoute)
        setLogs(nextLogs)
      })
      .catch((error: Error) => notify(error.message, true))
  }, [revision, notify])

  async function cutoff() {
    setBusy(true)
    try {
      await api.cutoff()
      await refresh()
      notify('本班已截单，后端将拒绝新的学生订单。')
    } catch (error) {
      notify(error instanceof Error ? error.message : '截单失败。', true)
    } finally {
      setBusy(false)
    }
  }

  const loaded = summary.counts.picked + summary.counts.campus + summary.counts.out + summary.counts.delivered
  return (
    <>
      <PageHeading
        eyebrow="OPERATIONS / OVERVIEW"
        title="今日运营总览"
        description="所有角色现在读取同一个 SQLite 数据源，刷新页面后状态仍然保留。"
        extra={<StatusChip status={summary.batch.status} />}
      />
      <div className="hero">
        <div className="hero-content">
          <div className="overline">LUNCH SHUTTLE · 资阳环境科技职业学院</div>
          <h2>让一车城区美食，<br />按约定时间到达校园。</h2>
          <p>梅西商圈 · 达高商圈 → 校园指定交接点　｜　计划发车 {time(summary.batch.depart_at)}　｜　地点均待核实</p>
          <div className="hero-facts"><span><strong>01</strong> 固定午餐班次</span><span><strong>03</strong> 演示商家</span><span><strong>R001</strong> 取货线路</span></div>
        </div>
        <div className="hero-watermark">✦</div>
      </div>
      <div className="grid cols4">
        <div className="stat"><div className="label">◉ 本班订单</div><span className="value">{summary.counts.orders}<small> 单</small></span><div className="meta">容量上限 {summary.batch.capacity} 单</div></div>
        <div className="stat"><div className="label">▣ 计划餐袋</div><span className="value">{summary.counts.parcels}<small> 袋</small></span><div className="meta">已交付 {summary.counts.delivered} 袋</div></div>
        <div className="stat"><div className="label">↗ 已实装餐袋</div><span className="value">{loaded}<small> 袋</small></span><div className="meta">以逐店后端交接为准</div></div>
        <div className="stat"><div className="label">◇ 待处理异常</div><span className={`value ${summary.counts.open_issues ? 'red' : 'green'}`}>{summary.counts.open_issues}</span><div className="meta">{summary.counts.open_issues ? '请前往异常中心处理' : '暂无开放异常'}</div></div>
      </div>

      <div className="layout-main mt16">
        <div>
          <section className="card">
            <div className="card-title"><h3>班次控制台</h3><StatusChip status={summary.batch.status} /></div>
            <div className="responsive-row">
              <div><div className="small-note">批次 B001 · 取货线 R001</div><div className="console-time">{time(summary.batch.cutoff_at)} 截单　/　{time(summary.batch.depart_at)} 发车</div></div>
              <Button disabled={summary.batch.status !== 'open' || busy} onClick={() => void cutoff()}>确认本班截单</Button>
            </div>
            <div className="stage-track">{steps.map((_, index) => <span className={index <= stage ? 'done' : ''} key={index} />)}</div>
            <ul className="step-list">
              {steps.map(([title, text], index) => (
                <li key={title}>
                  <div className={`step-icon ${index <= stage ? 'done' : ''}`}>{index < stage ? '✓' : index + 1}</div>
                  <div className="step-copy"><strong>{title}</strong><p>{text}</p></div>
                  {index === stage ? <Chip type="green">当前阶段</Chip> : null}
                </li>
              ))}
            </ul>
          </section>
          <section className="card">
            <div className="card-title"><h3>后端审计记录</h3><small>最新操作优先</small></div>
            <ul className="log-list">
              {logs.slice(0, 8).map((log) => <li key={log.id}><span className="log-time">{dateTime(log.created_at)}</span><span className="log-msg">{log.action} · {log.entity_id}</span></li>)}
            </ul>
          </section>
        </div>
        <div>
          <section className="card">
            <div className="card-title"><h3>城区路线 R001</h3><Chip type="blue">固定顺序</Chip></div>
            {route?.stops.map((stop) => {
              const merchant = merchants.find((item) => item.id === stop.merchant_id)
              return <div className="flow-row" key={stop.id}><span className="flow-order">{stop.sequence}</span><div className="flow-main"><strong>{merchant?.name}</strong><small>{merchant?.zone} · {time(stop.planned_pickup_at)} 预计取货</small></div><div className="flow-right"><strong>{stop.planned_count}袋</strong><small>{stop.handoff ? `实装${stop.handoff.actual_count}袋` : '未交接'}</small></div></div>
            })}
            <div className="banner-warn mt16">取货顺序、路程及时间均为演示配置，尚未完成线下实测。</div>
          </section>
          <section className="card">
            <div className="card-title"><h3>班次模拟贡献</h3><Chip>仅作测算</Chip></div>
            <div className="small-note">模拟成交额 {money(summary.economics.food_amount)} · 非真实收款</div>
            <div className={`highlight-value ${summary.economics.contribution < 0 ? 'red-text' : 'green-text'}`}>{money(summary.economics.contribution)}</div>
            <div className="small-note">收入减模拟变动成本和固定成本后的估算值，非净利润。</div>
            <div className="line" />
            <Button kind="outline" block onClick={() => navigate('issues')}>查看异常与成本明细 →</Button>
          </section>
        </div>
      </div>
    </>
  )
}
