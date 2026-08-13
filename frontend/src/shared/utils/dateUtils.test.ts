import { describe, it, expect } from 'vitest';
import { validateDateRange, todayISO } from './dateUtils';

describe('validateDateRange', () => {
  it('aceita intervalo válido', () => {
    expect(validateDateRange('2026-09-01', '2026-09-30')).toBeNull();
  });

  it('rejeita data final anterior à inicial', () => {
    expect(validateDateRange('2026-09-30', '2026-09-01')).toMatch(/anterior/i);
  });

  it('aceita datas iguais', () => {
    expect(validateDateRange('2026-09-01', '2026-09-01')).toBeNull();
  });

  it('não valida quando algum campo está vazio', () => {
    expect(validateDateRange('', '2026-09-01')).toBeNull();
    expect(validateDateRange('2026-09-01', '')).toBeNull();
  });
});

describe('todayISO', () => {
  it('retorna data no formato YYYY-MM-DD', () => {
    expect(todayISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
