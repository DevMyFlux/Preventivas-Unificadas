/** Datas no fuso LOCAL do navegador (Brasil). `toISOString()` usaria UTC e viraria o dia às 21h. */

export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function todayISO(now: Date = new Date()): string {
  return toISODate(now);
}

export function parseISO(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function addDays(iso: string, n: number): string {
  const d = parseISO(iso);
  d.setDate(d.getDate() + n);
  return toISODate(d);
}

export function validateDateRange(dataIni: string, dataFim: string): string | null {
  if (!dataIni || !dataFim) return null;
  if (dataFim < dataIni) return 'Data final não pode ser anterior à data inicial';
  if (Math.round((parseISO(dataFim).getTime() - parseISO(dataIni).getTime()) / 86_400_000) > 366) {
    return 'O período máximo é de 366 dias';
  }
  return null;
}

/** Todos os dias de [ini, fim] (limitado, para o seletor de dias). */
export function eachDay(ini: string, fim: string, limite = 62): string[] {
  const dias: string[] = [];
  let atual = ini;
  while (atual <= fim && dias.length < limite) {
    dias.push(atual);
    atual = addDays(atual, 1);
  }
  return dias;
}

export const DIAS_SEMANA = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];

export function weekday(iso: string): number {
  return parseISO(iso).getDay();
}

export function formatBR(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

/** Timestamp UTC da API ("...Z") → "dd/mm/aaaa hh:mm" no horário local. */
export function formatDateTimeBR(ts: string | null | undefined): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

export function firstOfMonth(iso: string): string {
  return `${iso.slice(0, 8)}01`;
}

export function lastOfMonth(iso: string): string {
  const d = parseISO(iso);
  return toISODate(new Date(d.getFullYear(), d.getMonth() + 1, 0));
}
