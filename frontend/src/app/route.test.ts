import { describe, expect, it } from 'vitest';
import { hashDa, parseRota } from './route';

describe('roteamento por hash', () => {
  it('interpreta rotas de unidade e de administração', () => {
    expect(parseRota('#/u/HMB/colaboradores', 'HETRIN')).toEqual({ tipo: 'unidade', unidade: 'HMB', pagina: 'colaboradores' });
    expect(parseRota('#/admin/auditoria', 'HETRIN')).toEqual({ tipo: 'admin', pagina: 'auditoria' });
  });

  it('rota vazia ou inválida cai na unidade padrão do usuário', () => {
    expect(parseRota('', 'HETRIN')).toEqual({ tipo: 'unidade', unidade: 'HETRIN', pagina: 'preventivas' });
    expect(parseRota('#/lixo/qualquer', 'HMB')).toEqual({ tipo: 'unidade', unidade: 'HMB', pagina: 'preventivas' });
    expect(parseRota('#/admin/inexistente', 'HMB')).toEqual({ tipo: 'unidade', unidade: 'HMB', pagina: 'preventivas' });
    expect(parseRota('#/u/HMB/pagina-falsa', 'HETRIN')).toEqual({ tipo: 'unidade', unidade: 'HMB', pagina: 'preventivas' });
  });

  it('ida e volta (hash → rota → hash) é estável', () => {
    for (const h of ['#/u/HMB/regras', '#/u/HETRIN/atribuicoes', '#/admin/relatorios']) {
      expect(hashDa(parseRota(h, 'HMB'))).toBe(h);
    }
  });
});
