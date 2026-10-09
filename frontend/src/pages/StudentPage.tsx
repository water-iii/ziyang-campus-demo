import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Button, Chip, Empty, OrderChip, PageHeading, StatusChip, money, time } from '../components'
import type { PageProps } from '../App'
import type { Order } from '../types'

const merchantArt: Record<string, { symbol: string; tone: string; kind: string }> = {
  m1: { symbol: '🍱', tone: 'peach', kind: '盖饭·简餐' },
  m2: { symbol: '🍗', tone: 'amber', kind: '炸鸡·套餐' },
  m3: { symbol: '🥘', tone: 'blue', kind: '川味·家常菜' },
}
const productSymbols = ['🍚', '🥩', '🍱', '🍗', '🍛', '🍖', '🥘', '🌶️', '🍲']
const points = [
  { id: 'point-a', name: '指定交接点 A（演示）' },
  { id: 'point-b', name: '指定交接点 B（演示）' },
]

function savedOrderIds(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem('ziyang-stage2-order-ids') || '[]') as unknown
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

export function StudentPage({ summary, merchants, revision, refresh, notify }: PageProps) {
  const [merchantId, setMerchantId] = useState('m1')
  const [cart, setCart] = useState<Record<string, number>>({})
  const [pointId, setPointId] = useState('point-a')
  const [orders, setOrders] = useState<Order[]>([])
  const [busy, setBusy] = useState(false)
  const merchant = merchants.find((item) => item.id === merchantId) || merchants[0]
  const ids = useMemo(savedOrderIds, [revision])

  useEffect(() => {
    if (!ids.length) {
      setOrders([])
      return
    }
    void Promise.all(ids.map((id) => api.getOrder(id)))
      .then((items) => setOrders(items.reverse()))
      .catch((error: Error) => notify(error.message, true))
  }, [ids.join(','), revision, notify])

  const items = merchant.products.filter((product) => (cart[product.id] || 0) > 0)
  const total = items.reduce((sum, product) => sum + product.price * (cart[product.id] || 0), 0)

  function change(productId: string, delta: number) {
    setCart((current) => ({ ...current, [productId]: Math.max(0, Math.min(20, (current[productId] || 0) + delta)) }))
  }

  async function placeOrder() {
    setBusy(true)
    try {
      const result = await api.createOrder({
        merchant_id: merchant.id,
        delivery_point_id: pointId,
        student_alias: 'React演示用户',
        items: items.map((product) => ({ product_id: product.id, quantity: cart[product.id] })),
      })
      const nextIds = [...savedOrderIds(), result.order.id]
      localStorage.setItem('ziyang-stage2-order-ids', JSON.stringify([...new Set(nextIds)]))
      setCart({})
      setOrders((current) => [result.order, ...current])
      await refresh()
      notify(`订单 ${result.order.id} 已写入后端，商家端现在可见。`)
    } catch (error) {
      notify(error instanceof Error ? error.message : '下单失败。', true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeading eyebrow="STUDENT / ORDERING" title="学生预约午餐" description="订单提交后写入 SQLite；刷新页面会从后端重新读取状态。" extra={<Chip type="yellow">模拟支付 · 不扣款</Chip>} />
      <div className="layout-wide">
        <div>
          <section className="card">
            <div className="bento-head"><div className="icon-tile">🎓</div><div><h3>资阳环境科技职业学院</h3><p>单校区演示 · 学校准入和地点尚未确认</p></div></div>
            <div className="banner-soft"><div className="responsive-row"><strong>演示午餐 · 第1班</strong><StatusChip status={summary.batch.status} /></div><div className="grid cols3 mt16"><div><div className="small-note">下单截止</div><strong>{time(summary.batch.cutoff_at)}</strong></div><div><div className="small-note">城区发车</div><strong>{time(summary.batch.depart_at)}</strong></div><div><div className="small-note">计划餐袋</div><strong>{summary.counts.parcels} 袋</strong></div></div></div>
            <div className="section-heading"><h2>选择城区商家</h2><span className="minor">示例商家 / 非真实入驻</span></div>
            <div className="grid">
              {merchants.map((item) => <button key={item.id} className={`shop-card ${merchant.id === item.id ? 'selected' : ''}`} onClick={() => { setMerchantId(item.id); setCart({}) }}><span className={`shop-art ${merchantArt[item.id].tone}`}>{merchantArt[item.id].symbol}</span><span className="shop-detail"><strong>{item.name}</strong><p>{merchantArt[item.id].kind} · {item.zone}</p><small>本班固定线路 · 按时预约</small></span><span>→</span></button>)}
            </div>
          </section>
          <section className="card">
            <div className="card-title"><h3>{merchant.name} · 示例菜单</h3><small>一张订单仅限一家商户</small></div>
            {merchant.products.map((product, index) => <div className="menu-item" key={product.id}><div className="food-emoji">{productSymbols[(Number(product.id.slice(-1)) - 1 + (Number(product.id[1]) - 1) * 3) % productSymbols.length] || productSymbols[index]}</div><div className="menu-copy"><strong>{product.name}</strong><small>演示菜单 · 非真实门店报价</small><b>{money(product.price)}</b></div><div className="counter"><button disabled={!cart[product.id]} onClick={() => change(product.id, -1)}>−</button><span>{cart[product.id] || 0}</span><button disabled={summary.batch.status !== 'open'} onClick={() => change(product.id, 1)}>+</button></div></div>)}
          </section>
          {orders.length ? <section className="card"><div className="card-title"><h3>本浏览器创建的后端订单</h3><Button kind="ghost" small onClick={() => void refresh()}>刷新状态</Button></div><div className="order-list">{orders.map((order) => <div className="order-row" key={order.id}><div><strong>{order.id} · {merchants.find((item) => item.id === order.merchant_id)?.name}</strong><small>{order.items.map((item) => `${item.name} ×${item.quantity}`).join('，')}</small><small>{points.find((point) => point.id === order.delivery_point_id)?.name} · {order.parcels.length}袋</small></div><div className="r"><OrderChip status={order.status} /><small>{money(order.amount)}</small></div></div>)}</div></section> : null}
        </div>
        <div>
          <section className="card sticky-card">
            <div className="card-title"><h3>确认预约订单</h3><Chip type="green">API 下单</Chip></div>
            {items.length ? items.map((product) => <div className="mini-total" key={product.id}><span>{product.name} ×{cart[product.id]}</span><span>{money(product.price * cart[product.id])}</span></div>) : <Empty icon="🛍️" title="购物车还是空的" text="选择一个商家，添加想要演示的餐品。" />}
            <div className="line" />
            <div className="field"><label htmlFor="student-point">预约交付点（仅为模拟）</label><select id="student-point" value={pointId} onChange={(event) => setPointId(event.target.value)}>{points.map((point) => <option value={point.id} key={point.id}>{point.name}</option>)}</select></div>
            <div className="mini-total"><span>餐品合计</span><span>{money(total)}</span></div><div className="mini-total"><span>演示配送费</span><span>{money(items.length ? 2.5 : 0)}</span></div><div className="line" /><div className="two-between"><strong>合计（非实际扣款）</strong><div className="cart-total">{money(total + (items.length ? 2.5 : 0))}</div></div>
            <div className="mt16"><Button block disabled={!items.length || summary.batch.status !== 'open' || busy} onClick={() => void placeOrder()}>{summary.batch.status === 'open' ? '提交模拟订单' : '该班已截单'}</Button></div>
            <div className="small-note mt16">不接入微信支付，不产生真实交易；按钮只创建演示订单。</div>
          </section>
        </div>
      </div>
    </>
  )
}
