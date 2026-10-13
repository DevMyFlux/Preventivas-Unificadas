import { eachDay, DIAS_SEMANA, weekday } from '../utils/dateUtils';

interface Props {
  dataIni: string;
  dataFim: string;
  hoje: string;
  selecionados: string[];
  onChange: (dias: string[]) => void;
  /** Dias com ocorrências no resultado (mostra um contador no tooltip). */
  contagem?: Record<string, number>;
}

/**
 * Seleção de dias específicos dentro do período carregado (ex.: 02, 05 e 09 — não necessariamente
 * contíguos). Sem nenhum dia selecionado = todos os dias do período.
 */
export default function DayPicker({ dataIni, dataFim, hoje, selecionados, onChange, contagem }: Props) {
  const dias = eachDay(dataIni, dataFim, 62);
  const set = new Set(selecionados);
  const alternar = (d: string) => {
    const novo = new Set(set);
    if (novo.has(d)) novo.delete(d); else novo.add(d);
    onChange(Array.from(novo).sort());
  };
  const truncado = dataIni <= dataFim && eachDay(dataIni, dataFim, 63).length > 62;

  return (
    <div>
      <div className="row" style={{ marginBottom: 6, justifyContent: 'space-between' }}>
        <span className="label">Dias do período {selecionados.length > 0 && `(${selecionados.length} selecionado${selecionados.length > 1 ? 's' : ''})`}</span>
        {selecionados.length > 0 && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange([])}>Limpar dias</button>
        )}
      </div>
      <div className="daypicker" role="group" aria-label="Selecionar dias específicos">
        {dias.map((d) => {
          const wd = weekday(d);
          const n = contagem?.[d];
          return (
            <button
              key={d}
              type="button"
              className={`day${d === hoje ? ' today' : ''}${wd === 0 || wd === 6 ? ' weekend' : ''}`}
              aria-pressed={set.has(d)}
              aria-label={`${d.slice(8)}/${d.slice(5, 7)}${d === hoje ? ' (hoje)' : ''}${n != null ? `, ${n} ocorrências` : ''}`}
              title={n != null ? `${n} ocorrência(s)` : undefined}
              onClick={() => alternar(d)}
            >
              <small>{DIAS_SEMANA[wd]}</small>
              <b>{d.slice(8)}</b>
            </button>
          );
        })}
      </div>
      {truncado && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Mostrando os primeiros 62 dias do período.</div>}
    </div>
  );
}
