import { describe, it, expect } from 'vitest';
import {
  addDays, eachDay, firstOfMonth, formatBR, lastOfMonth, todayISO, toISODate, validateDateRange, weekday,
} from './dateUtils';

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

  it('rejeita períodos maiores que 366 dias (mesmo limite do backend)', () => {
    expect(validateDateRange('2025-01-01', '2026-06-01')).toMatch(/366/);
    expect(validateDateRange('2026-01-01', '2026-12-31')).toBeNull();
  });
});

describe('todayISO / fuso local', () => {
  it('retorna data no formato YYYY-MM-DD', () => {
    expect(todayISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('usa o dia LOCAL, não o UTC (às 22h de Brasília o dia ainda é o mesmo)', () => {
    // 2026-10-13 22:30 no horário local do ambiente de teste — independe do fuso da máquina
    const tardeDaNoite = new Date(2026, 9, 13, 22, 30);
    expect(todayISO(tardeDaNoite)).toBe('2026-10-13');
    expect(toISODate(new Date(2026, 0, 1, 0, 5))).toBe('2026-01-01');
    expect(toISODate(new Date(2026, 11, 31, 23, 59))).toBe('2026-12-31');
  });
});

describe('aritmética de datas', () => {
  it('soma dias atravessando mês e ano', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
  });

  it('lista os dias do intervalo (inclusive nas pontas) com limite', () => {
    expect(eachDay('2026-10-30', '2026-11-02')).toEqual(['2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02']);
    expect(eachDay('2026-01-01', '2026-12-31', 10)).toHaveLength(10);
    expect(eachDay('2026-10-05', '2026-10-01')).toEqual([]);
  });

  it('primeiro e último dia do mês', () => {
    expect(firstOfMonth('2026-10-17')).toBe('2026-10-01');
    expect(lastOfMonth('2026-02-10')).toBe('2026-02-28');
    expect(lastOfMonth('2026-10-01')).toBe('2026-10-31');
  });

  it('dia da semana e formatação BR', () => {
    expect(weekday('2026-10-13')).toBe(2); // terça
    expect(formatBR('2026-10-13')).toBe('13/10/2026');
    expect(formatBR(null)).toBe('—');
  });
});
