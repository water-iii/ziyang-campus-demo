export type Role = 'student' | 'merchant' | 'driver' | 'campus' | 'operations'

export type BatchStatus =
  | 'open'
  | 'cutoff'
  | 'collecting'
  | 'transit'
  | 'campus'
  | 'delivering'
  | 'finished'

export interface Product {
  id: string
  name: string
  price: number
  active: boolean
}

export interface Merchant {
  id: string
  name: string
  zone: string
  address: string
  capacity: number
  status: string
  products: Product[]
}

export interface Parcel {
  id: string
  status: string
}

export interface OrderItem {
  product_id: string
  name: string
  quantity: number
  unit_price: number
}

export interface Order {
  id: string
  batch_id: string
  merchant_id: string
  delivery_point_id: string
  student_alias: string
  amount: number
  accepted_at: string | null
  created_at: string
  mock_paid: boolean
  status: string
  items: OrderItem[]
  parcels: Parcel[]
}

export interface BatchSummary {
  batch: {
    id: string
    name: string
    status: BatchStatus
    capacity: number
    cutoff_at: string
    depart_at: string
    delivery_window: [string, string]
  }
  counts: {
    orders: number
    parcels: number
    open_issues: number
    pending: number
    ready: number
    picked: number
    campus: number
    out: number
    delivered: number
    missing: number
    pickup_timeout: number
    pickup_abandoned: number
    refunded: number
  }
  economics: {
    food_amount: number
    revenue: number
    variable_cost: number
    fixed_cost: number
    contribution: number
    is_demo_estimate: boolean
  }
}

export interface MerchantDashboard {
  merchant: Pick<Merchant, 'id' | 'name' | 'zone' | 'status'>
  batch_id: string
  orders: Order[]
  production_summary: Array<{ product_id: string; name: string; quantity: number }>
}

export interface RouteStop {
  id: string
  merchant_id: string
  sequence: number
  planned_pickup_at: string
  latest_handoff_at: string
  latest_pickup_at: string
  deadline_reached: boolean
  timeout_handoff_allowed: boolean
  early_close_authorized: boolean
  early_close_reason: string | null
  partial_handoff_allowed: boolean
  planned_count: number
  ready_parcel_ids: string[]
  unready_parcel_ids: string[]
  parcel_status_counts: Record<string, number>
  parcel_manifest: Array<{ parcel_id: string; order_id: string; status: string }>
  handoff: null | {
    planned_count: number
    actual_count: number
    created_at: string
  }
}

export interface DeliveryTask {
  id: number
  batch_id: string
  delivery_point_id: string
  assigned_actor: string
  status: string
  parcels: Array<{
    parcel_id: string
    order_id: string
    parcel_status: string
    task_status: string
    delivered_at: string | null
  }>
}

export interface PickupRoute {
  id: string
  batch_id: string
  name: string
  business_time: string
  stops: RouteStop[]
}

export interface DemoClock {
  environment: string
  current_at: string
  frozen_at: string | null
  simulated: boolean
}

export interface Issue {
  id: string
  merchant_id: string
  order_id: string
  parcel_id: string
  type: string
  status: 'open' | 'resolved'
  resolution: string | null
  created_at: string
  resolved_at: string | null
}

export interface AuditLog {
  id: number
  actor_role: Role
  actor_id: string
  action: string
  entity_type: string
  entity_id: string
  details: Record<string, unknown>
  created_at: string
}

export interface MutationResult {
  idempotent_replay: boolean
  [key: string]: unknown
}
