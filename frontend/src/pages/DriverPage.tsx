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
      const missing = stop.ready_parcel_ids.filter((parcelId) => !pickedSet.has(parcelId))
      await api.handoff(stop.id, picked, missing)
      await refresh()
      await load()
      notify(missing.length ? `已逐袋登记：实装${picked.length}袋、缺${missing.length}袋。` : '该站逐袋核对完成，计划数与实装数一致。')
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
              const canPickup = ['cutoff', 'collecting'].includes(summary.batch.status) && allReady
              const selected = pickedByStop[stop.id] || []
              return <div className="route-line" key={stop.id}><div className="route-index">{stop.sequence}</div><div className="route-data"><div className="head"><strong>{merchant?.name}</strong>{stop.handoff ? <Chip type="green">交接已记录</Chip> : <Chip type="yellow">等待取货</Chip>}</div><p>{merchant?.zone} · 预计 {time(stop.planned_pickup_at)} 到店 · 应取 {stop.planned_count} 袋 · 当前待取 {stop.ready_parcel_ids.length} 袋</p><div className="parcel-check-grid">{stop.parcel_manifest.map((parcel) => <label className={`parcel-check ${parcel.status}`} key={parcel.parcel_id}><input type="checkbox" disabled={Boolean(stop.handoff) || parcel.status !== 'ready'} checked={stop.handoff ? parcel.status === 'picked' : selected.includes(parcel.parcel_id)} onChange={() => toggleParcel(stop.id, parcel.parcel_id)} /><span><code>{parcel.parcel_id}</code><small>{parcel.order_id}</small></span><Chip type={parcel.status === 'missing' ? 'red' : parcel.status === 'picked' ? 'green' : 'yellow'}>{parcel.status}</Chip></label>)}</div>{stop.handoff ? <div className="banner-soft">实际取货 {stop.handoff.actual_count}/{stop.handoff.planned_count} 袋 {stop.handoff.actual_count < stop.handoff.planned_count ? '· 已生成缺袋异常' : '· 数量一致'}</div> : <div className="actions"><Button small disabled={!canPickup || Boolean(busyStop)} onClick={() => void handoff(stop, 'all')}>确认实际全数取货</Button><Button small kind="outline" disabled={!canPickup || Boolean(busyStop) || selected.length === stop.planned_count} onClick={() => void handoff(stop, 'selected')}>按勾选结果交接（{selected.length}/{stop.planned_count}）</Button><Button small kind="danger" disabled={!canPickup || !stop.ready_parcel_ids.length || Boolean(busyStop)} onClick={() => void handoff(stop, 'shortage')}>模拟缺1袋并交接</Button></div>}</div></div>
            })}
            <div className="line" />
            <div className="responsive-row"><div><strong>本班准备发车</strong><div className="small-note">三站均有后端交接流水后才允许发车。</div></div><Button disabled={!allDone || summary.batch.status !== 'collecting' || Boolean(busyStop)} onClick={() => void depart()}>确认本班模拟发车 →</Button></div>
          </section>
        </div>
        <div>
          <section className="card"><div className="card-title"><h3>司机交接原则</h3></div><ol className="notice-list"><li>必须按 S001 → S002 → S003 顺序</li><li>核对后端计划餐袋和现场实装数</li><li>缺袋必须关联明确餐袋编号</li><li>缺袋餐袋不会进入运输状态</li><li>同一站点不能重复确认交接</li></ol></section>
          <section className="card"><div className="banner-warn">如按钮显示不可操作，请先到三家商家工作台分别完成接单和打包。正式运营还需核实车辆、温控、保险及驾驶安全。</div></section>
        </div>
      </div>
    </>
  )
}
