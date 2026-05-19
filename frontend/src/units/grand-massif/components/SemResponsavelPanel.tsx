import type { OSItem, OSResponse } from '../api/types';

interface SemResponsavelPanelProps {
  osData: OSResponse | null;
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '…' : text;
}

export default function SemResponsavelPanel({ osData }: SemResponsavelPanelProps) {
  const items: OSItem[] = osData ? osData.itens.filter((item) => !item.responsavel) : [];
  const count = items.length;

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>Sem Responsável</span>
        <span className="badge b-danger">{count}</span>
      </div>

      <div className="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>Nº OS</th>
              <th>Abertura</th>
              <th>Tipo</th>
              <th>Setor</th>
              <th>Prioridade</th>
              <th>Reclamação</th>
            </tr>
          </thead>
          <tbody>
            {!osData || count === 0 ? (
              <tr>
                <td colSpan={6} className="empty">
                  {!osData
                    ? 'Carregue os dados na aba OS Abertas para visualizar.'
                    : 'Nenhuma OS sem responsável encontrada.'}
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.numero} className="row-danger">
                  <td>{item.numero}</td>
                  <td>{item.abertura}</td>
                  <td>{item.tipo}</td>
                  <td>{item.setor}</td>
                  <td>{item.prioridade}</td>
                  <td title={item.reclamacao}>{truncate(item.reclamacao, 80)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
