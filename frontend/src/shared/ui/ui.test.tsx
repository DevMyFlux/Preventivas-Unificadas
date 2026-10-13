import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import DayPicker from './DayPicker';
import Modal from './Modal';
import { Alert, Button, Chip, EmptyState, KpiCard, Pagination, Tabs } from './ui';

describe('DayPicker', () => {
  function Wrapper({ onChange }: { onChange?: (d: string[]) => void }) {
    const [sel, setSel] = useState<string[]>([]);
    return <DayPicker dataIni="2026-10-12" dataFim="2026-10-16" hoje="2026-10-14" selecionados={sel}
      onChange={(d) => { setSel(d); onChange?.(d); }} contagem={{ '2026-10-14': 7 }} />;
  }

  it('mostra todos os dias do período e marca o de hoje', () => {
    render(<Wrapper />);
    const botoes = screen.getAllByRole('button').filter((b) => b.hasAttribute('aria-pressed'));
    expect(botoes).toHaveLength(5);
    expect(screen.getByRole('button', { name: /14\/10 \(hoje\), 7 ocorrências/ })).toBeInTheDocument();
  });

  it('permite escolher dias NÃO contíguos e devolve a lista ordenada', async () => {
    const aoMudar = vi.fn();
    render(<Wrapper onChange={aoMudar} />);
    await userEvent.click(screen.getByRole('button', { name: /^16\/10/ }));
    await userEvent.click(screen.getByRole('button', { name: /^12\/10/ }));
    expect(aoMudar).toHaveBeenLastCalledWith(['2026-10-12', '2026-10-16']);
    expect(screen.getByText(/2 selecionados/)).toBeInTheDocument();
  });

  it('desmarca ao clicar de novo e "Limpar dias" zera a seleção', async () => {
    const aoMudar = vi.fn();
    render(<Wrapper onChange={aoMudar} />);
    const dia = screen.getByRole('button', { name: /^13\/10/ });
    await userEvent.click(dia);
    expect(dia).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(dia);
    expect(dia).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(screen.getByRole('button', { name: /^15\/10/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Limpar dias' }));
    expect(aoMudar).toHaveBeenLastCalledWith([]);
  });
});

describe('Pagination', () => {
  it('descreve o intervalo e desabilita os extremos', () => {
    const { rerender } = render(<Pagination page={1} pageSize={100} total={250} onPage={() => {}} />);
    expect(screen.getByText(/1–100 de 250/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Página anterior' })).toBeDisabled();
    expect(screen.getByText('Página 1 de 3')).toBeInTheDocument();
    rerender(<Pagination page={3} pageSize={100} total={250} onPage={() => {}} />);
    expect(screen.getByText(/201–250 de 250/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Próxima página' })).toBeDisabled();
  });

  it('navega e notifica a mudança de página e de tamanho', async () => {
    const onPage = vi.fn();
    const onSize = vi.fn();
    render(<Pagination page={2} pageSize={50} total={500} onPage={onPage} onPageSize={onSize} />);
    await userEvent.click(screen.getByRole('button', { name: 'Próxima página' }));
    expect(onPage).toHaveBeenCalledWith(3);
    await userEvent.click(screen.getByRole('button', { name: 'Página anterior' }));
    expect(onPage).toHaveBeenCalledWith(1);
    await userEvent.selectOptions(screen.getByRole('combobox'), '200');
    expect(onSize).toHaveBeenCalledWith(200);
  });

  it('sem registros mostra mensagem clara', () => {
    render(<Pagination page={1} pageSize={50} total={0} onPage={() => {}} />);
    expect(screen.getByText('Nenhum registro')).toBeInTheDocument();
  });
});

describe('KpiCard', () => {
  it('é um botão pressionável quando clicável e mostra o valor formatado', async () => {
    const onClick = vi.fn();
    render(<KpiCard label="Em atraso" value={1234} tone="danger" onClick={onClick} pressed />);
    const b = screen.getByRole('button', { name: /Em atraso/ });
    expect(b).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByText('1.234')).toBeInTheDocument();
    await userEvent.click(b);
    expect(onClick).toHaveBeenCalled();
  });

  it('sem onClick não vira botão; carregando mostra esqueleto (sem número falso)', () => {
    render(<KpiCard label="Total" value={null} loading />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByText('0')).toBeNull();
  });
});

describe('Tabs', () => {
  const tabs = [{ key: 'a' as const, label: 'A' }, { key: 'b' as const, label: 'B', count: 3 }, { key: 'c' as const, label: 'C' }];

  it('expõe papéis ARIA e troca com as setas do teclado', async () => {
    const onChange = vi.fn();
    render(<Tabs tabs={tabs} value="a" onChange={onChange} label="Seções" />);
    expect(screen.getByRole('tablist', { name: 'Seções' })).toBeInTheDocument();
    const [a] = screen.getAllByRole('tab');
    expect(a).toHaveAttribute('aria-selected', 'true');
    a.focus();
    await userEvent.keyboard('{ArrowLeft}');
    expect(onChange).toHaveBeenLastCalledWith('c');   // da primeira aba, ← volta circular para a última
    a.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('b');
    expect(within(screen.getByRole('tab', { name: /B/ })).getByText('3')).toBeInTheDocument();
  });
});

describe('componentes simples', () => {
  it('Button em loading fica desabilitado e anuncia ocupado', () => {
    render(<Button loading>Salvar</Button>);
    const b = screen.getByRole('button', { name: /Salvar/ });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute('aria-busy', 'true');
  });

  it('Alert de erro usa role=alert; informativo usa status', () => {
    const { rerender } = render(<Alert tone="danger">Falhou</Alert>);
    expect(screen.getByRole('alert')).toHaveTextContent('Falhou');
    rerender(<Alert tone="info">Dica</Alert>);
    expect(screen.getByRole('status')).toHaveTextContent('Dica');
  });

  it('Chip e EmptyState renderizam o texto (a cor nunca é o único sinal)', () => {
    render(<><Chip tone="danger">Atrasada</Chip><EmptyState title="Nada aqui">Ajuste os filtros</EmptyState></>);
    expect(screen.getByText('Atrasada')).toBeInTheDocument();
    expect(screen.getByText('Nada aqui')).toBeInTheDocument();
  });
});

describe('Modal (acessibilidade)', () => {
  it('é um diálogo nomeado, fecha com Esc e devolve o foco ao botão que o abriu', async () => {
    function Teste() {
      const [aberto, setAberto] = useState(false);
      return <><button onClick={() => setAberto(true)}>Abrir</button>{aberto && <Modal title="Detalhes" onClose={() => setAberto(false)}><input aria-label="campo" /></Modal>}</>;
    }
    render(<Teste />);
    const abrir = screen.getByRole('button', { name: 'Abrir' });
    await userEvent.click(abrir);
    expect(screen.getByRole('dialog', { name: 'Detalhes' })).toBeInTheDocument();
    expect(screen.getByLabelText('campo')).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(abrir).toHaveFocus();
  });

  it('mantém o foco preso dentro do diálogo (Tab circular)', async () => {
    render(<Modal title="T" onClose={() => {}}><input aria-label="um" /><input aria-label="dois" /></Modal>);
    const fechar = screen.getByRole('button', { name: 'Fechar' });
    const dois = screen.getByLabelText('dois');
    dois.focus();
    await userEvent.tab();
    expect(fechar).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(dois).toHaveFocus();
  });
});
