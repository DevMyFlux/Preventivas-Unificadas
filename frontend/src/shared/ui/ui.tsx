/* Componentes de interface compartilhados — pequenos, sem dependências, acessíveis. */
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import Icon from './Icon';
import type { IconName } from './Icon';
import type { Tone } from '../utils/status';

// ── Botão ────────────────────────────────────────────────────────────────────

type Variant = 'primary' | 'secondary' | 'ghost' | 'success' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: 'md' | 'sm';
  icon?: IconName;
  loading?: boolean;
}

export function Button({ variant = 'secondary', size = 'md', icon, loading, children, className = '', disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={`btn btn-${variant}${size === 'sm' ? ' btn-sm' : ''}${!children ? ' btn-icon' : ''} ${className}`.trim()}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="spin" aria-hidden="true" /> : icon ? <Icon name={icon} size={16} /> : null}
      {children}
    </button>
  );
}

// ── Chip de status ───────────────────────────────────────────────────────────

export function Chip({ tone = 'neutral', children, title }: { tone?: Tone; children: ReactNode; title?: string; dot?: boolean }) {
  return (
    <span className={`chip c-${tone}`} title={title}>
      {children}
    </span>
  );
}

// ── Estados ──────────────────────────────────────────────────────────────────

export function Spinner({ label }: { label?: string }) {
  return (
    <span role="status" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span className="spin" aria-hidden="true" />
      {label ? <span>{label}</span> : <span className="sr-only">Carregando</span>}
    </span>
  );
}

export function Skeleton({ width = '100%', height = 14 }: { width?: number | string; height?: number | string }) {
  return <div className="skeleton" style={{ width, height }} aria-hidden="true" />;
}

export function TableSkeleton({ rows = 6, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="table-wrap" aria-busy="true" aria-label="Carregando dados">
      <table className="table">
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((__, c) => (
                <td key={c}><Skeleton width={c === 0 ? 70 : `${55 + ((r + c) % 4) * 10}%`} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Alert({ tone = 'info', children, action, role }: {
  tone?: 'info' | 'warning' | 'danger' | 'success';
  children: ReactNode;
  action?: ReactNode;
  role?: 'alert' | 'status';
}) {
  const icon: IconName = tone === 'danger' ? 'alert' : tone === 'warning' ? 'alert' : tone === 'success' ? 'checkCircle' : 'info';
  return (
    <div className={`alert alert-${tone}`} role={role ?? (tone === 'danger' ? 'alert' : 'status')}>
      <Icon name={icon} size={17} />
      <div>{children}</div>
      {action}
    </div>
  );
}

export function EmptyState({ icon = 'inbox', title, children, action }: { icon?: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <Icon name={icon} size={30} />
      <b>{title}</b>
      {children && <div>{children}</div>}
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}

// ── Indicador (faixa de números; clicável quando filtra a tela) ─────────────

interface KpiProps {
  label: string;
  value: number | string | null;
  tone?: 'success' | 'info' | 'warning' | 'danger' | 'purple' | 'primary';
  hint?: string;
  onClick?: () => void;
  pressed?: boolean;
  loading?: boolean;
}

export function KpiCard({ label, value, tone = 'primary', hint, onClick, pressed, loading }: KpiProps) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      className={`kpi t-${tone}`}
      {...(onClick ? { onClick, type: 'button' as const, 'aria-pressed': !!pressed } : {})}
    >
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{loading || value === null ? <Skeleton width={48} height={22} /> : typeof value === 'number' ? value.toLocaleString('pt-BR') : value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </Tag>
  );
}

// ── Paginação ────────────────────────────────────────────────────────────────

export function Pagination({ page, pageSize, total, onPage, onPageSize }: {
  page: number; pageSize: number; total: number; onPage: (p: number) => void; onPageSize?: (n: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav className="pager" aria-label="Paginação">
      <span>{total === 0 ? 'Nenhum registro' : `${from.toLocaleString('pt-BR')}–${to.toLocaleString('pt-BR')} de ${total.toLocaleString('pt-BR')}`}</span>
      <span className="row">
        {onPageSize && (
          <label className="row" style={{ gap: 6 }}>
            <span className="muted">Por página</span>
            <select className="select" style={{ width: 'auto' }} value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}>
              {[50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
        <Button size="sm" icon="chevronLeft" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Página anterior" />
        <span aria-live="polite">Página {page} de {pages}</span>
        <Button size="sm" icon="chevronRight" onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label="Próxima página" />
      </span>
    </nav>
  );
}

// ── Abas acessíveis (setas ← → alternam) ─────────────────────────────────────

export function Tabs<T extends string>({ tabs, value, onChange, label }: {
  tabs: { key: T; label: string; count?: number | null }[]; value: T; onChange: (k: T) => void; label: string;
}) {
  const onKey = (e: React.KeyboardEvent, idx: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const next = (idx + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length;
    onChange(tabs[next].key);
    (e.currentTarget.parentElement?.children[next] as HTMLElement | undefined)?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button
          key={t.key}
          role="tab"
          type="button"
          className="tab"
          aria-selected={value === t.key}
          tabIndex={value === t.key ? 0 : -1}
          onClick={() => onChange(t.key)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {t.label}
          {t.count != null && <span className="chip c-neutral nodot" style={{ marginLeft: 6 }}>{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { key: T; label: string }[]; value: T; onChange: (k: T) => void; label: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} type="button" aria-pressed={value === o.key} onClick={() => onChange(o.key)}>{o.label}</button>
      ))}
    </div>
  );
}

export function PageHead({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h2 className="page-title">{title}</h2>
        {subtitle && <div className="page-sub">{subtitle}</div>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}
