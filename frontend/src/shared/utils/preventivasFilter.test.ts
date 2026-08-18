import { describe, it, expect } from 'vitest';
import { filterPreventivas } from './preventivasFilter';
import type { Preventiva } from '../api/types';

function preventiva(overrides: Partial<Preventiva>): Preventiva {
  return {
    data_prev: '15/09/2026',
    dia_par: 'Ímpar',
    atrasada: false,
    plano: 'Plano X',
    tipo: 'Preventiva',
    oficina: 'Elétrica',
    equipamento: 'Chiller 01',
    setor: 'UTI',
    os_vinculada: '123',
    os_situacao: 'Aberta',
    recomendado: 'Fulano de Tal',
    cargo: 'Técnico',
    escala: 'Diurno | Fixo',
    score: 150,
    ...overrides,
  };
}

describe('filterPreventivas', () => {
  const itens: Preventiva[] = [
    preventiva({ recomendado: 'Ana Eletricista', data_prev: '05/09/2026', plano: 'Ronda Elétrica' }),
    preventiva({ recomendado: 'Bruno Silveira', data_prev: '20/09/2026', plano: 'Ronda Hidráulica', setor: 'Almoxarifado' }),
    preventiva({ recomendado: null, data_prev: '10/09/2026', plano: 'Sem candidato' }),
  ];

  it('sem filtros retorna tudo', () => {
    expect(filterPreventivas(itens, '', '', '', '')).toHaveLength(3);
  });

  it('filtra por responsável (case-insensitive, parcial)', () => {
    const r = filterPreventivas(itens, 'ana', '', '', '');
    expect(r).toHaveLength(1);
    expect(r[0].recomendado).toBe('Ana Eletricista');
  });

  it('filtro por responsável não quebra quando recomendado é null', () => {
    const r = filterPreventivas(itens, 'bruno', '', '', '');
    expect(r).toHaveLength(1);
  });

  it('filtra por intervalo de datas (dataIni/dataFim em ISO)', () => {
    const r = filterPreventivas(itens, '', '2026-09-06', '2026-09-15', '');
    expect(r).toHaveLength(1);
    expect(r[0].plano).toBe('Sem candidato');
  });

  it('busca livre encontra por setor', () => {
    const r = filterPreventivas(itens, '', '', '', 'almoxarifado');
    expect(r).toHaveLength(1);
    expect(r[0].plano).toBe('Ronda Hidráulica');
  });

  it('busca livre encontra por plano', () => {
    const r = filterPreventivas(itens, '', '', '', 'ronda elétrica');
    expect(r).toHaveLength(1);
  });

  it('combina múltiplos filtros com AND', () => {
    const r = filterPreventivas(itens, 'ana', '2026-09-01', '2026-09-30', 'elétrica');
    expect(r).toHaveLength(1);
    const rVazio = filterPreventivas(itens, 'ana', '', '', 'hidráulica');
    expect(rVazio).toHaveLength(0);
  });

  it('filtra por status OS específico', () => {
    const comStatus: Preventiva[] = [
      preventiva({ os_situacao: 'Aberta', plano: 'A' }),
      preventiva({ os_situacao: 'Em Andamento', plano: 'B' }),
      preventiva({ os_situacao: '—', plano: 'C' }),
    ];
    const r = filterPreventivas(comStatus, '', '', '', '', 'Aberta');
    expect(r).toHaveLength(1);
    expect(r[0].plano).toBe('A');
  });

  it('filtro "sem_os" pega apenas itens sem OS vinculada visível', () => {
    const comStatus: Preventiva[] = [
      preventiva({ os_situacao: 'Aberta', plano: 'A' }),
      preventiva({ os_situacao: '—', plano: 'C' }),
    ];
    const r = filterPreventivas(comStatus, '', '', '', '', 'sem_os');
    expect(r).toHaveLength(1);
    expect(r[0].plano).toBe('C');
  });

  it('filtra por recomendação com/sem candidato', () => {
    const comRec = filterPreventivas(itens, '', '', '', '', '', 'com');
    expect(comRec.every((i) => i.recomendado)).toBe(true);

    const semRec = filterPreventivas(itens, '', '', '', '', '', 'sem');
    expect(semRec).toHaveLength(1);
    expect(semRec[0].plano).toBe('Sem candidato');
  });
});
