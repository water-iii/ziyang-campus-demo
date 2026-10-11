import type {
  AuditLog,
  BatchSummary,
  DeliveryTask,
  DemoClock,
  Issue,
  Merchant,
  MerchantDashboard,
  MutationResult,
  Order,
  PickupRoute,
  Role,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
  }
}

function idempotencyKey(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
  return `${prefix}-${suffix}`
}

function actorHeaders(role: Role, merchantId?: string): Record<string, string> {
  const headers: Record<string, string> = {
    'X-Demo-Role': role,
    'X-Demo-Actor': `react-${role}`,
  }
  if (merchantId) headers['X-Merchant-Id'] = merchantId
  return headers
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  role: Role = 'operations',
  merchantId?: string,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...actorHeaders(role, merchantId),
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`
    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) message = data.detail
    } catch {
      // 保留通用错误信息。
    }
    throw new ApiError(message, response.status)
  }
  return response.json() as Promise<T>
}

function post<T extends MutationResult>(path: string, role: Role, body?: unknown, merchantId?: string): Promise<T> {
  return request<T>(
    path,
    {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
      headers: { 'Idempotency-Key': idempotencyKey(path.replaceAll('/', '-')) },
    },
    role,
    merchantId,
  )
}

export const api = {
  baseUrl: API_BASE,
  getSummary: () => request<BatchSummary>('/batches/B001/summary'),
  getMerchants: () => request<Merchant[]>('/merchants'),
  reset: () => request<{ orders: number; parcels: number; merchants: number }>('/demo/reset', { method: 'POST' }),
  getDemoClock: () => request<DemoClock>('/demo/clock'),
  setDemoClock: (currentAt: string) =>
    request<DemoClock>(
      '/demo/clock',
      {
        method: 'PUT',
        body: JSON.stringify({ current_at: currentAt }),
      },
      'operations',
    ),
  resetDemoClock: () => request<DemoClock>('/demo/clock', { method: 'DELETE' }, 'operations'),
  createOrder: (payload: {
    merchant_id: string
    delivery_point_id: string
    student_alias: string
    items: Array<{ product_id: string; quantity: number }>
  }) => post<{ order: Order } & MutationResult>('/orders', 'student', { batch_id: 'B001', ...payload }),
  getOrder: (orderId: string) => request<Order>(`/orders/${orderId}`, {}, 'student'),
  cutoff: () => post<MutationResult>('/batches/B001/cutoff', 'operations'),
  getMerchantDashboard: (merchantId: string) =>
    request<MerchantDashboard>(
      `/batches/B001/merchants/${merchantId}/dashboard`,
      {},
      'merchant',
      merchantId,
    ),
  acceptMerchant: (merchantId: string) =>
    post<MutationResult>(`/batches/B001/merchants/${merchantId}/accept`, 'merchant', undefined, merchantId),
  packMerchant: (merchantId: string) =>
    post<MutationResult>(`/batches/B001/merchants/${merchantId}/pack`, 'merchant', undefined, merchantId),
  acceptOrder: (merchantId: string, orderId: string) =>
    post<MutationResult>(`/orders/${orderId}/accept`, 'merchant', undefined, merchantId),
  packParcel: (merchantId: string, parcelId: string) =>
    post<MutationResult>(`/parcels/${parcelId}/pack`, 'merchant', undefined, merchantId),
  getRoute: () => request<PickupRoute>('/batches/B001/route', {}, 'driver'),
  handoff: (stopId: string, pickedParcelIds: string[], missingParcelIds: string[]) =>
    post<MutationResult>(`/pickup-stops/${stopId}/handoff`, 'driver', {
      actual_count: pickedParcelIds.length,
      picked_parcel_ids: pickedParcelIds,
      missing_parcel_ids: missingParcelIds,
    }),
  authorizeEarlyClose: (stopId: string, reason: string) =>
    post<MutationResult>(`/pickup-stops/${stopId}/early-close-authorization`, 'operations', { reason }),
  depart: () => post<MutationResult>('/batches/B001/depart', 'driver'),
  campusReceive: () => post<MutationResult>('/batches/B001/campus-receive', 'campus'),
  assignDelivery: () => post<MutationResult>('/batches/B001/delivery/assign', 'campus'),
  completeDelivery: () => post<MutationResult>('/batches/B001/delivery/complete', 'campus'),
  getDeliveryTasks: () => request<DeliveryTask[]>('/batches/B001/delivery-tasks', {}, 'campus'),
  deliverParcel: (taskId: number, parcelId: string) =>
    post<MutationResult>(`/delivery-tasks/${taskId}/parcels/${parcelId}/deliver`, 'campus'),
  getIssues: () => request<Issue[]>('/batches/B001/issues'),
  resolveIssue: (issueId: string) =>
    post<MutationResult>(`/issues/${issueId}/resolve`, 'operations', {
      resolution: '模拟退款（无真实资金动作）',
    }),
  getAuditLogs: () => request<AuditLog[]>('/batches/B001/audit-logs'),
  updateFixedCost: (fixedCost: number) =>
    request<MutationResult>(
      '/batches/B001/costs/fixed',
      {
        method: 'PUT',
        body: JSON.stringify({ fixed_cost: fixedCost }),
        headers: { 'Idempotency-Key': idempotencyKey('fixed-cost') },
      },
      'operations',
    ),
}
