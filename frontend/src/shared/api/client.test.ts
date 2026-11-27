import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auditQuery } from './adminClient';
import { buildUnitClient, preventivasQuery } from './client';
import { buildQuery, setCsrfToken } from './http';

describe('preventivasQuery — monta os parâmetros enviados ao backend', () => {
  it('período obrigatório e atrasadas incluídas por padrão', () => {
    const q = preventivasQuery({ dataIni: '2026-10-01', dataFim: '2026-10-31' });
    expect(q).toMatchObject({ data_ini: '2026-10-01', data_fim: '2026-10-31', incluir_atrasadas: '1' });
    expect(buildQuery(q)).toBe('?data_ini=2026-10-01&data_fim=2026-10-31&incluir_atrasadas=1');
  });

  it('dias selecionados (não contíguos) viram lista CSV', () => {
    const qs = buildQuery(preventivasQuery({ dataIni: '2026-10-01', dataFim: '2026-10-31', dias: ['2026-10-02', '2026-10-05', '2026-10-09'] }));
    expect(new URLSearchParams(qs).get('dias')).toBe('2026-10-02,2026-10-05,2026-10-09');
  });

  it('combina dia, status, turno, atraso, responsável e paginação', () => {
    const qs = new URLSearchParams(buildQuery(preventivasQuery({
      dataIni: '2026-10-01', dataFim: '2026-10-31', status: ['Pendente', 'Em andamento'], atrasada: true, turno: 'Noturno',
      paridade: 'Par', responsavel: '  Iranildo ', busca: ' ronda ', revisao: true, semCandidato: true, fIni: '2026-10-05',
      fFim: '2026-10-09', origem: 'OS', oficina: 'ELÉTRICA', page: 3, pageSize: 50, incluirAtrasadas: false,
    })));
    expect(Object.fromEntries(qs)).toEqual({
      data_ini: '2026-10-01', data_fim: '2026-10-31', incluir_atrasadas: '0', f_ini: '2026-10-05', f_fim: '2026-10-09',
      status: 'Pendente,Em andamento', atrasada: '1', turno: 'Noturno', paridade: 'Par', responsavel: 'Iranildo',
      busca: 'ronda', revisao: '1', sem_candidato: '1', origem: 'OS', oficina: 'ELÉTRICA', page: '3', page_size: '50',
    });
  });

  it('filtros vazios não geram parâmetros (e atrasada=false não é enviado)', () => {
    const qs = new URLSearchParams(buildQuery(preventivasQuery({
      dataIni: '2026-10-01', dataFim: '2026-10-01', dias: [], status: [], atrasada: false, turno: '', busca: '  ',
    })));
    expect([...qs.keys()].sort()).toEqual(['data_fim', 'data_ini', 'incluir_atrasadas']);
  });

  it('refresh só vai quando pedido', () => {
    expect(preventivasQuery({ dataIni: 'a', dataFim: 'b', refresh: true }).refresh).toBe('1');
    expect(preventivasQuery({ dataIni: 'a', dataFim: 'b' }).refresh).toBeUndefined();
  });
});

describe('auditQuery', () => {
  it('mapeia filtros da área administrativa', () => {
    const qs = new URLSearchParams(buildQuery(auditQuery({ dataIni: '2026-10-01', dataFim: '2026-10-13', username: ' ana ', unit: 'HMB', result: 'denied', page: 2, pageSize: 50 })));
    expect(Object.fromEntries(qs)).toEqual({ data_ini: '2026-10-01', data_fim: '2026-10-13', username: 'ana', unit: 'HMB', result: 'denied', page: '2', page_size: '50' });
  });
});

describe('cliente de unidade — usa só o prefixo do usuário e codifica nomes', () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);
    setCsrfToken('t');
  });
  afterEach(() => vi.unstubAllGlobals());

  it('codifica nome com acento/barra no caminho', async () => {
    const c = buildUnitClient('/api/brasilandia');
    await c.atualizarStatusColaborador('João da Silva/Jr', 'Desligado');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/brasilandia/colaborador/Jo%C3%A3o%20da%20Silva%2FJr/status');
    expect(fetchMock.mock.calls[0][1].method).toBe('PATCH');
  });

  it('nunca envia a unidade como parâmetro — só o prefixo da rota', async () => {
    const c = buildUnitClient('/api/grandmassif');
    await c.fetchPreventivas({ dataIni: '2026-10-01', dataFim: '2026-10-02' });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url.startsWith('/api/grandmassif/preventivas?')).toBe(true);
    expect(url).not.toMatch(/unit|unidade|empresa/i);
  });

  it('vínculo (admissão/desligamento) envia datas ISO ou null', async () => {
    const c = buildUnitClient('/api/brasilandia');
    await c.atualizarVinculoColaborador('Fulano', { data_desligamento: '2026-09-18', data_admissao: null });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ data_desligamento: '2026-09-18', data_admissao: null });
  });

  it('exportar preventivas usa GET com os mesmos filtros (sem paginação) — consistente com a listagem', async () => {
    fetchMock.mockResolvedValue(new Response(new Blob(['x']), { status: 200 }));
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:1', revokeObjectURL: () => {} });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await buildUnitClient('/api/brasilandia').exportarPreventivas({ dataIni: '2026-10-01', dataFim: '2026-10-31', status: ['Concluída'], page: 4, pageSize: 50 });
    const [url, init] = fetchMock.mock.calls[0];
    const qs = new URLSearchParams(String(url).split('?')[1]);
    expect(init.method).toBe('GET');
    expect(qs.get('status')).toBe('Concluída');
    expect(qs.has('page')).toBe(false);
    expect(qs.has('page_size')).toBe(false);
  });
});
