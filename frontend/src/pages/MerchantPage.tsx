import { useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Chip, Empty, OrderChip, PageHeading, money, time } from '../components'
import type { PageProps } from '../App'
import type { MerchantDashboard } from '../types'

const merchantArt: Record<string, { symbol: string; tone: string }> = {
  m1: { symbol: '🍱', tone: 'peach' },
  m2: { symbol: '🍗', tone: 'amber' },
  m3: { symbol: '🥘', tone: 'blue' },
}

export function MerchantPage({ summary, merchants, revision, refresh, notify }: PageProps) {
  const [merchantId, setMerchantId] = useState('m1')
  const [dashboard, setDashboard] = useState<MerchantDashboard | null>(null)
  const [busy, setBusy] = useState(false)
  const merchant = merchants.find((item) => item.id === merchantId) || merchants[0]

  async function load() {
    try {
      setDashboard(await api.getMerchantDashboard(merchantId))
    } catch (error) {
      notify(error instanceof Error ? error.message : '商家数据加载失败。', true)
    }
  }

  useEffect(() => {
    void load()
  }, [merchantId, revision])

  async function act(kind: 'accept' | 'pack') {
    setBusy(true)
    try {
      if (kind === 'accept') await api.acceptMerchant(merchantId)
      else await api.packMerchant(merchantId)
      await refresh()
      await load()
      notify(kind === 'accept' ? '本店订单已由后端确认。' : '本店餐袋已由后端标记为待取。')
    } catch (error) {
      notify(error instanceof Error ? error.message : '商家操作失败。', true)
    } finally {
      setBusy(false)
    }
  }

  async function acceptSingle(orderId: string) {
    setBusy(true)
    try {
      await api.acceptOrder(merchantId, orderId)
      await refresh()
      await load()
      notify(`订单 ${orderId} 已单独接单并写入审计。`)
    } catch (error) {
      notify(error instanceof Error ? error.message : '逐单接单失败。', true)
    } finally {
      setBusy(false)
    }
  }

  async function packSingle(parcelId: string) {
    setBusy(true)
    try {
      await api.packParcel(merchantId, parcelId)
      await refresh()
      await load()
      notify(`餐袋 ${parcelId} 已单独确认打包。`)
    } catch (error) {
      notify(error instanceof Error ? error.message : '逐袋打包失败。', true)
    } finally {
      setBusy(false)
    }
  }

  const orders = dashboard?.orders || []
  const accepted = orders.filter((order) => order.accepted_at).length
  const parcels = orders.flatMap((order) => order.parcels)
  const ready = parcels.filter((parcel) => ['ready', 'picked', 'campus', 'out', 'delivered'].includes(parcel.status)).length
  const canOperate = ['cutoff', 'collecting'].includes(summary.batch.status)
  const allAccepted = orders.length > 0 && accepted === orders.length
  const hasPending = parcels.some((parcel) => parcel.status === 'pending')

  return (
    <>
      <PageHeading eyebrow="MERCHANT / WORKSPACE" title="商家出餐工作台" description="商家请求带有演示范围头；A 店无法读取 B 店工作台。" extra={<Chip type="yellow">演示商家非真实入驻</Chip>} />
      <div className="segment">{merchants.map((item) => <button key={item.id} className={merchantId === item.id ? 'active' : ''} onClick={() => setMerchantId(item.id)}>{item.name}</button>)}</div>
      <div className="layout-main">
        <div>
          <section className="card">
            <div className="bento-head"><div className={`shop-art ${merchantArt[merchant.id].tone} merchant-avatar`}>{merchantArt[merchant.id].symbol}</div><div><h3>{merchant.name}</h3><p>{merchant.zone} · 固定线路取货</p></div></div>
            <div className="grid cols3"><div className="stat"><div className="label">本班订单</div><span className="value">{orders.length}</span></div><div className="stat"><div className="label">已接单</div><span className="value">{accepted}</span></div><div className="stat"><div className="label">已打包袋数</div><span className="value">{ready}/{parcels.length}</span></div></div>
            <div className="section-heading"><h2>本班生产清单</h2><span className="minor">来自后端订单明细</span></div>
            {dashboard?.production_summary.length ? dashboard.production_summary.map((item, index) => <div className="flow-row" key={item.product_id}><div className="flow-order">{['🍚', '🥩', '🍱'][index] || '🍴'}</div><div className="flow-main"><strong>{item.name}</strong><small>按 SKU 聚合</small></div><div className="flow-right"><strong>× {item.quantity} 份</strong></div></div>) : <Empty title="暂无生产清单" text="等待学生订单或后端数据。" />}
            <div className="banner-warn mt16">实际出餐、食品安全、打包标签和交接时间仍需线下确认。本页仅演示履约状态。</div>
            <div className="btns mt16"><Button disabled={!canOperate || allAccepted || busy} onClick={() => void act('accept')}>① 确认本班订单</Button><Button kind="dark" disabled={!canOperate || !allAccepted || !hasPending || busy} onClick={() => void act('pack')}>② 全部模拟打包</Button></div>
          </section>
        </div>
        <div>
          <section className="card">
            <div className="card-title"><h3>订单清单</h3><Chip type="blue">{orders.length} 单</Chip></div>
            <div className="order-list">{orders.map((order) => <div className="order-row order-row-trace" key={order.id}><div className="order-main"><strong>{order.id}</strong><small>{order.items.map((item) => `${item.name} ×${item.quantity}`).join('，')}</small><small>{order.delivery_point_id} · {order.parcels.length}袋</small><div className="parcel-actions">{order.parcels.map((parcel) => <span className="parcel-action" key={parcel.id}><code>{parcel.id}</code><Chip type={['missing', 'pickup_timeout', 'pickup_abandoned', 'refunded'].includes(parcel.status) ? 'red' : parcel.status === 'pending' ? 'yellow' : 'green'}>{parcel.status}</Chip>{order.accepted_at && parcel.status === 'pending' ? <Button kind="ghost" small disabled={!canOperate || busy} onClick={() => void packSingle(parcel.id)}>确认打包</Button> : null}</span>)}</div>{!order.accepted_at ? <Button kind="outline" small disabled={!canOperate || busy} onClick={() => void acceptSingle(order.id)}>单独接单</Button> : null}</div><div className="r"><OrderChip status={order.status} /><small>{money(order.amount)}</small></div></div>)}</div>
          </section>
          <section className="card"><div className="card-title"><h3>接口范围说明</h3></div><div className="small-note">当前请求角色：merchant / {merchant.id}。这是演示权限隔离，不代表真实身份认证。计划截单：{time(summary.batch.cutoff_at)}。</div></section>
        </div>
      </div>
    </>
  )
}
