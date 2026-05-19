import type { OSItem } from '../api/types';

export function filterOS(
  items: OSItem[],
  situacao: string,
  responsavel: string,
  search: string,
): OSItem[] {
  const term = search.trim().toLowerCase();

  return items.filter((item) => {
    if (situacao === 'Aberta' && item.sit_label !== 'Aberta') return false;
    if (situacao === 'Em Andamento' && item.sit_label !== 'Em Andamento') return false;
    if (situacao === 'Fechada' && item.sit_label !== 'Fechada') return false;

    if (responsavel === 'Com Responsável' && !item.responsavel) return false;
    if (responsavel === 'Sem Responsável' && item.responsavel) return false;

    if (term) {
      const haystack = [item.numero, item.tipo, item.setor, item.responsavel ?? '', item.reclamacao]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(term)) return false;
    }

    return true;
  });
}
