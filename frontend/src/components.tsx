import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { BatchStatus } from './types'

export const statusLabels: Record<BatchStatus, string> = {
  open: '开放预订',
  cutoff: '已截单',
  collecting: '城区取货中',
  transit: '干线运输中',
  campus: '到校交接完成',
  delivering: '校园配送中',
  finished: '已结束',
}

export const orderLabels: Record<string, string> = {
  awaiting_merchant_acceptance: '待商家接单',
  preparing: '制作中',
  ready_for_pickup: '已打包待取',
  loaded: '已装车',
  in_transit: '干线运输中',
  at_campus: '已到校交接点',
  out_for_delivery: '末端配送中',
  delivered: '已交付',
  pickup_exception: '取货异常',
  refunded: '已模拟退款',
  partially_refunded_completed: '部分退款完成',
  partial_exception: '部分异常',
}

export function money(value: number): string {
  return `¥${Number(value || 0).toFixed(2)}`
}

export function time(value: string): string {
  return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
}

export function dateTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

export function Chip({ children, type = 'dark' }: { children: ReactNode; type?: string }) {
  return <span className={`chip ${type}`}>{children}</span>
}

export function StatusChip({ status }: { status: BatchStatus }) {
  const type = status === 'open' || status === 'finished' || status === 'campus' || status === 'delivering'
    ? 'green'
    : status === 'cutoff'
      ? 'yellow'
      : 'blue'
  return <Chip type={type}>{statusLabels[status]}</Chip>
}

export function OrderChip({ status }: { status: string }) {
  const label = orderLabels[status] || status
  const type = status.includes('exception') || status.includes('refund')
    ? 'red'
    : status === 'delivered'
      ? 'green'
      : status === 'awaiting_merchant_acceptance'
        ? 'yellow'
        : 'blue'
  return <Chip type={type}>{label}</Chip>
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  kind?: 'primary' | 'dark' | 'outline' | 'ghost' | 'danger'
  small?: boolean
  block?: boolean
}

export function Button({ kind = 'primary', small, block, className = '', children, ...props }: ButtonProps) {
  return (
    <button
      className={`btn btn-${kind}${small ? ' btn-sm' : ''}${block ? ' btn-block' : ''} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function PageHeading({
  eyebrow,
  title,
  description,
  extra,
}: {
  eyebrow: string
  title: string
  description: string
  extra?: ReactNode
}) {
  return (
    <section className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {extra}
    </section>
  )
}

export function Empty({ icon = '✓', title, text }: { icon?: string; title: string; text: string }) {
  return (
    <div className="empty">
      <span className="empty-ico">{icon}</span>
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  )
}
