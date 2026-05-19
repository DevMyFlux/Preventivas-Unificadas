export function calcBarWidths<T extends { qtd: number }>(items: T[]): (T & { pct: number })[] {
  if (items.length === 0) return [];
  const max = Math.max(...items.map((i) => i.qtd));
  if (max === 0) return items.map((i) => ({ ...i, pct: 0 }));
  return items.map((i) => ({ ...i, pct: Math.round((i.qtd / max) * 100) }));
}
