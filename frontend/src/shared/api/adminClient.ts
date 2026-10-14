/** Cliente da área administrativa (somente Dev; o backend recusa os demais com 403). */
import { download, get, patch, post } from './http';
import type { Query } from './http';
import type { AdminUser, AuditFilters, AuditPage, SessionRow, UsageResponse, UsageSummary, UserDetail } from './types';

export function auditQuery(f: AuditFilters): Query {
  return {
    data_ini: f.dataIni,
    data_fim: f.dataFim,
    user_id: f.userId,
    username: f.username?.trim(),
    unit: f.unit,
    module: f.module,
    event: f.event,
    result: f.result,
    page: f.page,
    page_size: f.pageSize,
  };
}

export const adminApi = {
  listUsers: () => get<{ itens: AdminUser[]; unidades: { codigo: string; nome: string }[] }>('/api/admin/users'),
  createUser: (u: { username: string; password: string; display_name: string; unit: string; must_change_password: boolean }) =>
    post<AdminUser>('/api/admin/users', u),
  updateUser: (id: number, u: { display_name?: string; unit?: string }) => patch<AdminUser>(`/api/admin/users/${id}`, u),
  userDetail: (id: number) => get<UserDetail>(`/api/admin/users/${id}`),
  unlockUser: (id: number) => post<AdminUser>(`/api/admin/users/${id}/unlock`),
  setActive: (id: number, active: boolean) => post<AdminUser>(`/api/admin/users/${id}/active`, { active }),
  resetPassword: (id: number, password: string, mustChange: boolean) =>
    post<{ ok: boolean }>(`/api/admin/users/${id}/password`, { password, must_change_password: mustChange }),

  audit: (f: AuditFilters) => get<AuditPage>('/api/admin/audit', auditQuery(f)),
  summary: (f: AuditFilters) => get<UsageSummary>('/api/admin/audit/summary', auditQuery(f)),
  sessions: (f: AuditFilters) => get<{ itens: SessionRow[] }>('/api/admin/sessions', auditQuery(f)),
  usage: (f: AuditFilters) => get<UsageResponse>('/api/admin/usage', auditQuery(f)),
  exportAudit: (f: AuditFilters, format: 'xlsx' | 'csv') =>
    download('GET', '/api/admin/audit/export',
      { ...auditQuery({ ...f, page: undefined, pageSize: undefined }), format }, `auditoria.${format}`),
  exportUsage: (f: AuditFilters, format: 'xlsx' | 'csv') =>
    download('GET', '/api/admin/usage/export',
      { ...auditQuery({ ...f, page: undefined, pageSize: undefined }), format }, `uso.${format}`),
};
