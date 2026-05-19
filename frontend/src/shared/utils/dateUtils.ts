export function validateDateRange(dataIni: string, dataFim: string): string | null {
  if (dataIni && dataFim && dataFim < dataIni) {
    return 'Data final não pode ser anterior à data inicial';
  }
  return null;
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
