export function scoreClass(score: number): string {
  if (score >= 250) return 'score-high';
  if (score >= 150) return 'score-mid';
  return 'score-low';
}

export function statusBadgeClass(status: string): string {
  switch (status) {
    case 'Bate com atual':     return 'b-ok';
    case 'Sugestao diferente': return 'b-warn';
    case 'Sem resp. atual':    return 'b-blue';
    case 'Sem candidato':      return 'b-danger';
    default:                   return 'b-gray';
  }
}
