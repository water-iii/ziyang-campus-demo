import { useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Chip, PageHeading, StatusChip } from '../components'
import type { PageProps } from '../App'
import type { DeliveryTask } from '../types'

export function CampusPage({ summary, revision, refresh, notify, navigate }: PageProps) {
  const [busy, setBusy] = useState('')
  const [tasks, setTasks] = useState<DeliveryTask[]>([])

  async function loadTasks() {
    try {
      setTasks(await api.getDeliveryTasks())
    } catch (error) {
      notify(error instanceof Error ? error.message : '配送任务加载失败。', true)
    }
  }

  useEffect(() => {
    void loadTasks()
  }, [revision])

  async function act(kind: 'receive' | 'assign' | 'complete') {
    setBusy(kind)
    try {
      if (kind === 'receive') await api.campusReceive()
      if (kind === 'assign') await api.assignDelivery()
      if (kind === 'complete') await api.completeDelivery()
      await refresh()
      await loadTasks()
      notify({ receive: '已清点实际装车餐袋。', assign: '已按演示交接点生成配送任务。', complete: '正常餐袋已完成交付。' }[kind])
    } catch (error) {
      notify(error instanceof Error ? error.message : '校园交付操作失败。', true)
    } finally {
      setBusy('')
    }
  }

  async function deliverParcel(taskId: number, parcelId: string) {
    setBusy(parcelId)
    try {
      await api.deliverParcel(taskId, parcelId)
      await refresh()
      await loadTasks()
      notify(`餐袋 ${parcelId} 已逐袋确认交付。`)
    } catch (error) {
      notify(error instanceof Error ? error.message : '逐袋交付失败。', true)
    } finally {
      setBusy('')
    }
  }

  const loaded = summary.counts.picked + summary.counts.campus + summary.counts.out + summary.counts.delivered
  const received = summary.counts.campus + summary.counts.out + summary.counts.delivered
  return (
    <>
      <PageHeading eyebrow="CAMPUS / HANDOFF" title="校园交付工作台" description="仅清点司机实际装车餐袋；异常餐袋不会虚假到校。" extra={<StatusChip status={summary.batch.status} />} />
      <div className="layout-wide">
        <div>
          <section className="card">
            <div className="bento-head"><div className="icon-tile">📦</div><div><h3>校园到货交接</h3><p>资阳环境科技职业学院 · 校门或获准地点（未确认）</p></div></div>
            <div className="grid cols3"><div className="stat"><div className="label">干线实装</div><span className="value">{loaded}</span></div><div className="stat"><div className="label">到校清点</div><span className="value">{received}</span></div><div className="stat"><div className="label">已完成交付</div><span className="value">{summary.counts.delivered}</span></div></div>
            <div className="section-heading"><h2>校园任务</h2></div>
            <div className="flow-row"><span className="flow-order">1</span><div className="flow-main"><strong>到校清点交接</strong><small>仅接收状态为 picked 的实际装车餐袋</small></div><Button small disabled={summary.batch.status !== 'transit' || Boolean(busy)} onClick={() => void act('receive')}>模拟接收</Button></div>
            <div className="flow-row"><span className="flow-order">2</span><div className="flow-main"><strong>分配交付任务</strong><small>按照演示交接点在后端创建任务</small></div><Button small disabled={summary.batch.status !== 'campus' || Boolean(busy)} onClick={() => void act('assign')}>分配任务</Button></div>
            <div className="flow-row"><span className="flow-order">3</span><div className="flow-main"><strong>批量确认已交付</strong><small>保留快捷演示；也可在下方逐袋确认</small></div><Button small disabled={summary.batch.status !== 'delivering' || Boolean(busy)} onClick={() => void act('complete')}>全部完成交付</Button></div>
            {tasks.length ? <><div className="section-heading"><h2>逐袋配送任务</h2><span className="minor">{tasks.reduce((sum, task) => sum + task.parcels.length, 0)} 袋</span></div>{tasks.map((task) => <div className="delivery-task" key={task.id}><div className="two-between"><strong>任务 #{task.id} · {task.delivery_point_id}</strong><Chip type={task.status === 'completed' ? 'green' : 'blue'}>{task.status}</Chip></div><div className="parcel-check-grid mt8">{task.parcels.map((parcel) => <div className={`parcel-check ${parcel.parcel_status}`} key={parcel.parcel_id}><span><code>{parcel.parcel_id}</code><small>{parcel.order_id}</small></span><Chip type={parcel.task_status === 'delivered' ? 'green' : 'yellow'}>{parcel.task_status}</Chip>{parcel.task_status !== 'delivered' ? <Button kind="ghost" small disabled={Boolean(busy) || summary.batch.status !== 'delivering'} onClick={() => void deliverParcel(task.id, parcel.parcel_id)}>确认交付</Button> : null}</div>)}</div></div>)}</> : null}
            <div className="section-heading"><h2>交付点分拣看板</h2></div>
            {['指定交接点 A（演示）', '指定交接点 B（演示）'].map((point, index) => <div className="flow-row" key={point}><span className="flow-order">{index ? 'B' : 'A'}</span><div className="flow-main"><strong>{point}</strong><small>配置占位符，不代表校方已许可</small></div><Chip type="yellow">待校方确认</Chip></div>)}
          </section>
        </div>
        <div>
          <section className="card"><div className="card-title"><h3>校园准入约束</h3><Chip type="yellow">尚未核实</Chip></div><div className="banner-warn">是否允许校外餐饮进入、配送员活动区域和交接点位置，均须通过正式渠道确认。</div><ul className="notice-list mt16"><li>没有许可前，不默认进入宿舍区</li><li>末端人员需明确报酬和责任</li><li>餐袋交接与温控需可追踪</li><li>损坏餐品不得强行交付</li></ul></section>
          <section className="card"><div className="card-title"><h3>未装车异常</h3></div><div className={`highlight-value ${summary.counts.missing ? 'red-text' : 'green-text'}`}>{summary.counts.missing} <small>袋</small></div><div className="small-note">这些餐袋不会进入校园清点数。</div><Button kind="outline" block disabled={!summary.counts.open_issues} onClick={() => navigate('issues')}>前往异常中心 →</Button></section>
        </div>
      </div>
    </>
  )
}
