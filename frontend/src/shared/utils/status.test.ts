import { describe, expect, it } from 'vitest';
import { calcBarWidths } from './barChart';
import { HINT_RESPONSAVEL, STATUS_EXECUCAO, toneDaProposta, toneDoResponsavel, toneDoStatus } from './status';

describe('status de execução', () => {
  it('cobre os sete status do backend, cada um com dica explicativa', () => {
    expect(STATUS_EXECUCAO.map((s) => s.status)).toEqual([
      'Pendente', 'Em andamento', 'Parada', 'Concluída', 'Aguardando geração', 'Sem OS – verificar', 'Cancelada']);
    expect(STATUS_EXECUCAO.every((s) => s.hint.length > 5)).toBe(true);
  });

  it('cores semânticas: concluída verde, pendente âmbar, em andamento azul', () => {
    expect(toneDoStatus('Concluída')).toBe('success');
    expect(toneDoStatus('Pendente')).toBe('warning');
    expect(toneDoStatus('Em andamento')).toBe('info');
    expect(toneDoStatus('Sem OS – verificar')).toBe('purple');   // não é atraso: cor diferente da vermelha
    expect(toneDoStatus('qualquer coisa')).toBe('neutral');
  });

  it('responsável: gestão/genérico pedem atenção, desligado/bloqueado são críticos', () => {
    expect(toneDoResponsavel('Atribuída')).toBe('success');
    expect(toneDoResponsavel('Gestão')).toBe('warning');
    expect(toneDoResponsavel('Genérico')).toBe('warning');
    expect(toneDoResponsavel('Desligado')).toBe('danger');
    expect(toneDoResponsavel('Bloqueado')).toBe('danger');
    expect(toneDoResponsavel('Sem responsável')).toBe('purple');
  });

  it('propostas: aplicada verde, falha vermelha, conflito âmbar', () => {
    expect(toneDaProposta('aplicada')).toBe('success');
    expect(toneDaProposta('falha')).toBe('danger');
    expect(toneDaProposta('conflito')).toBe('warning');
    expect(toneDaProposta('simulada')).toBe('info');
  });
});

describe('calcBarWidths', () => {
  it('normaliza pelo maior valor e trata listas vazias/zeradas', () => {
    expect(calcBarWidths([{ qtd: 10 }, { qtd: 5 }, { qtd: 0 }]).map((x) => x.pct)).toEqual([100, 50, 0]);
    expect(calcBarWidths([])).toEqual([]);
    expect(calcBarWidths([{ qtd: 0 }]).map((x) => x.pct)).toEqual([0]);
  });
});

describe('responsável de equipe do Neovero (rondas diárias da HMB)', () => {
  it('é tratado como correto (verde) e tem dica explicativa', () => {
    expect(toneDoResponsavel('Equipe do Neovero')).toBe('success');
    expect(HINT_RESPONSAVEL['Equipe do Neovero']).toMatch(/automaticamente/);
  });
});
