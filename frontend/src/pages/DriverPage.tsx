import { useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Chip, PageHeading, StatusChip, time } from '../components'
import type { PageProps } from '../App'
import type { PickupRoute, RouteStop } from '../types'

export function DriverPage({ summary, merchants, revision, refresh, notify }: PageProps) {
  const [route, setRoute] = useState<PickupRoute | null>(null)
  const [busyStop, setBusyStop] = useState('')
  const [pickedByStop, setPickedByStop] = useState<Record<string, string[]>>({})

  async function load() {
    try {
      const nextRoute = await api.getRoute()
      setRoute(nextRoute)
      setPickedByStop((current) => {
        const next = { ...current }
        for (const stop of nextRoute.stops) {
          if (!stop.handoff && !next[stop.id]) next[stop.id] = [...stop.ready_parcel_ids]
        }
        return next
      })
    } catch (error) {
      notify(error instanceof Error ? error.message : '线路加载失败。', true)
    }
  }

  useEffect(() => {
    void load()
  }, [revision])

  function toggleParcel(stopId: string, parcelId: string) {
    setPickedByStop((current) => {
      const selected = new Set(current[stopId] || [])
      if (selected.has(parcelId)) selected.delete(parcelId)
      else selected.add(parcelId)
      return { ...current, [stopId]: [...selected] }
    })
  }

  async function handoff(stop: RouteStop, mode: 'all' | 'shortage' | 'selected') {
    setBusyStop(stop.id)
    try {
      const picked = mode === 'all'
        ? [...stop.ready_parcel_ids]
        : mode === 'shortage'
          ? stop.ready_parcel_ids.slice(0, -1)
          : (pickedByStop[stop.id] || [])
      const pickedSet = new Set(picked)
      const missing = stop.parcel_manifest
        .map((parcel) => parcel.parcel_id)
        .filter((parcelId) => !pickedSet.has(parcelId))
      await api.handoff(stop.id, picked, missing)
      await refresh()
      await load()
      notify(missing.length ? `已逐袋登记：实装${picked.length}袋、异常${missing.length}袋。` : '该站逐袋核对完成，计划数与实装数一致。')
    } catch (error) {
      notify(error instanceof Error ? error.message : '取货交接失败。', true)
    } finally {
      setBusyStop('')
    }
  }

  async function depart() {
    setBusyStop('depart')
    try {
      await api.depart()
      await refresh()
      await load()
      notify('车辆已从后端确认发车；只有实际装车餐袋进入运输状态。')
    } catch (error) {
      notify(error instanceof Error ? error.message : '发车失败。', true)
    } finally {
      setBusyStop('')
    }
  }

  const allDone = Boolean(route?.stops.every((stop) => stop.handoff))
  const loaded = summary.counts.picked + summary.counts.campus + summary.counts.out + summary.counts.delivered
  return (
    <>
      <PageHeading eyebrow="DRIVER / CITY PICKUP" title="城区司机工作台" description="后端校验固定路线顺序、计划数量、实装数量和重复交接。" extra={<StatusChip status={summary.batch.status} />} />
      <div className="layout-wide">
        <div>
          <section className="card">
            <div className="card-title"><h3>R001 · 梅西—达高城区取货线</h3><Chip>固定顺序</Chip></div>
            <div className="grid cols3"><div className="stat"><div className="label">取货商家</div><span className="value">{route?.stops.length || 0}</span></div><div className="stat"><div className="label">计划餐袋</div><span className="value">{summary.counts.parcels}</span></div><div className="stat"><div className="label">已经实装</div><span className="value">{loaded}</span></div></div>
            <div className="section-heading"><h2>逐店取货清单</h2><span className="minor">计划 {time(summary.batch.depart_at)} 城区发车</span></div>
            {route?.stops.map((stop) => {
              const merchant = merchants.find((item) => item.id === stop.merchant_id)
              const allReady = stop.ready_parcel_ids.length === stop.planned_count
              const canPickup = ['cutoff', 'collecting'].includes(summary.batch.status)
                && (allReady || stop.partial_handoff_allowed)
              const selected = pickedByStop[stop.id] || []
              const pickedCount = ['picked', 'campus', 'out', 'delivered']
                .reduce((sum, status) => sum + (stop.parcel_status_counts[status] || 0), 0)
              const exceptionCount = ['missing', 'pickup_timeout', 'pickup_abandoned', 'refunded']
                .reduce((sum, status) => sum + (stop.parcel_status_counts[status] || 0), 0)
              const waitingCount = stop.parcel_status_counts.ready || 0
              const preparingCount = stop.parcel_status_counts.pending || 0
              return (
                <div className="route-line" key={stop.id}>
                  <div className="route-index">{stop.sequence}</div>
                  <div className="route-data">
                    <div className="head">
                      <strong>{merchant?.name}</strong>
                      {stop.handoff ? <Chip type="green">交接已记录</Chip> : <Chip type="yellow">等待取货</Chip>}
                    </div>
                    <p>
                      {merchant?.zone} · 预计 {time(stop.planned_pickup_at)} 到店 · 最晚 {time(stop.latest_handoff_at)} 交接
                      {' '}· 应取 {stop.planned_count} 袋 · {stop.handoff ? `已取 ${pickedCount} 袋` : `已打包 ${stop.ready_parcel_ids.length} 袋`}
                    </p>
                    {!stop.handoff && preparingCount > 0 && !stop.partial_handoff_allowed ? (
                      <div className="banner-warn">
                        仍有 {preparingCount} 袋制作中；可提前核对已打包餐袋，但关闭交接必须等待截止或取得运营授权。
                      </div>
                    ) : null}
                    {!stop.handoff && preparingCount > 0 && stop.deadline_reached ? (
                      <div className="banner-pink">
                        最晚交接时间已到：仅可勾选已打包餐袋，制作中餐袋将生成“出餐超时”异常。
                      </div>
                    ) : null}
                    {!stop.handoff && preparingCount > 0 && !stop.deadline_reached && stop.early_close_authorized ? (
                      <div className="banner-pink">
                        运营已授权提前关闭：{stop.early_close_reason}。制作中餐袋将记录为提前放弃异常。
                      </div>
                    ) : null}
                    <div className="parcel-check-grid">
                      {stop.parcel_manifest.map((parcel) => (
                        <label className={`parcel-check ${parcel.status}`} key={parcel.parcel_id}>
                          <input
                            type="checkbox"
                            disabled={Boolean(stop.handoff) || parcel.status !== 'ready'}
                            checked={stop.handoff ? ['picked', 'campus', 'out', 'delivered'].includes(parcel.status) : selected.includes(parcel.parcel_id)}
                            onChange={() => toggleParcel(stop.id, parcel.parcel_id)}
                          />
                          <span><code>{parcel.parcel_id}</code><small>{parcel.order_id}</small></span>
                          <Chip type={['missing', 'pickup_timeout', 'pickup_abandoned', 'refunded'].includes(parcel.status) ? 'red' : ['picked', 'campus', 'out', 'delivered'].includes(parcel.status) ? 'green' : 'yellow'}>{parcel.status}</Chip>
                        </label>
                      ))}
                    </div>
                    {stop.handoff ? (
                      <div className="grid cols4 mt8">
                        <div className="stat"><div className="label">应取</div><span className="value">{stop.planned_count}</span></div>
                        <div className="stat"><div className="label">已取</div><span className="value">{pickedCount}</span></div>
                        <div className="stat"><div className="label">异常</div><span className="value red">{exceptionCount}</span></div>
                        <div className="stat"><div className="label">待取</div><span className="value">{waitingCount}</span></div>
                      </div>
                    ) : (
                      <div className="actions">
                        <Button small disabled={!canPickup || Boolean(busyStop)} onClick={() => void handoff(stop, 'all')}>
                          {allReady ? '确认实际全数取货' : `确认已打包 ${stop.ready_parcel_ids.length} 袋`}
                        </Button>
                        <Button small kind="outline" disabled={!canPickup || Boolean(busyStop) || selected.length === stop.planned_count} onClick={() => void handoff(stop, 'selected')}>
                          按勾选结果交接（{selected.length}/{stop.planned_count}）
                        </Button>
                        <Button small kind="danger" disabled={!canPickup || !stop.ready_parcel_ids.length || Boolean(busyStop)} onClick={() => void handoff(stop, 'shortage')}>
                          模拟缺1袋并交接
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
            <div className="line" />
            <div className="responsive-row"><div><strong>本班准备发车</strong><div className="small-note">三站均有后端交接流水后才允许发车。</div></div><Button disabled={!allDone || summary.batch.status !== 'collecting' || Boolean(busyStop)} onClick={() => void depart()}>确认本班模拟发车 →</Button></div>
          </section>
        </div>
        <div>
          <section className="card"><div className="card-title"><h3>司机交接原则</h3></div><ol className="notice-list"><li>必须按 S001 → S002 → S003 顺序</li><li>可提前勾选核对已打包餐袋，但不能擅自关闭交接</li><li>截止前放弃制作中餐袋必须取得运营授权</li><li>截止后只能勾选已打包餐袋实装</li><li>缺袋、出餐超时和提前放弃都必须关联明确餐袋编号</li><li>未装车餐袋不会进入运输状态</li></ol></section>
          <section className="card"><div className="banner-warn">如按钮显示不可操作，请先到三家商家工作台分别完成接单和打包。正式运营还需核实车辆、温控、保险及驾驶安全。</div></section>
        </div>
      </div>
    </>
  )
}
