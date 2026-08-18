import type { Preventiva } from '../api/types';

export type FiltroStatusOS = '' | 'Aberta' | 'Em Andamento' | 'sem_os';
export type FiltroRecomendacao = '' | 'com' | 'sem';

export function filterPreventivas(
  items: Preventiva[],
  responsavel: string,
  dataIni: string,
  dataFim: string,
  search: string,
  statusOS: FiltroStatusOS = '',
  recomendacao: FiltroRecomendacao = '',
): Preventiva[] {
  const respTerm = responsavel.trim().toLowerCase();
  const searchTerm = search.trim().toLowerCase();

  return items.filter((item) => {
    if (respTerm) {
      const rec = (item.recomendado ?? '').toLowerCase();
      if (!rec.includes(respTerm)) return false;
    }

    const datePrev = parseDateToISO(item.data_prev);
    if (dataIni && datePrev < dataIni) return false;
    if (dataFim && datePrev > dataFim) return false;

    if (statusOS) {
      const semOS = item.os_situacao === '—';
      if (statusOS === 'sem_os') {
        if (!semOS) return false;
      } else if (item.os_situacao !== statusOS) {
        return false;
      }
    }

    if (recomendacao === 'com' && !item.recomendado) return false;
    if (recomendacao === 'sem' && item.recomendado) return false;

    if (searchTerm) {
      const haystack = [item.plano, item.tipo, item.oficina, item.equipamento, item.setor, item.os_vinculada]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(searchTerm)) return false;
    }

    return true;
  });
}

function parseDateToISO(dateStr: string): string {
  if (!dateStr) return '';
  const parts = dateStr.split('/');
  if (parts.length === 3 && parts[0].length === 2) {
    return `${parts[2]}-${parts[1]}-${parts[0]}`;
  }
  return dateStr;
}
