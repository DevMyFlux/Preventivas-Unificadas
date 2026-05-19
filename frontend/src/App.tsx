import { useState, useEffect } from 'react';
import { validateDateRange, todayISO } from './shared/utils/dateUtils';
import GrandMassifModule from './units/grand-massif/GrandMassifModule';
import BrasilandiaModule from './units/brasilandia/BrasilandiaModule';

type UnitKey = 'grandmassif' | 'brasilandia';

const UNITS: { key: UnitKey; label: string; dotColor: string }[] = [
  { key: 'grandmassif', label: 'Grand Massif Trindade',   dotColor: 'var(--unit-gm-accent)' },
  { key: 'brasilandia', label: 'Grand Massif Brasilandia', dotColor: 'var(--unit-br-accent)' },
];

function useClock(): string {
  const fmt = () => new Date().toLocaleTimeString('pt-BR');
  const [time, setTime] = useState(fmt);
  useEffect(() => {
    const id = setInterval(() => setTime(fmt()), 1000);
    return () => clearInterval(id);
  }, []);
  return time;
}

export default function App() {
  const clock = useClock();
  const today = todayISO();

  const [activeUnit, setActiveUnit] = useState<UnitKey>('grandmassif');

  const [deInput, setDeInput]   = useState(today);
  const [ateInput, setAteInput] = useState(today);
  const [dateRange, setDateRange] = useState({ dataIni: today, dataFim: today });
  const [dateError, setDateError] = useState<string | null>(null);

  function handleApply() {
    const err = validateDateRange(deInput, ateInput);
    setDateError(err);
    if (!err) setDateRange({ dataIni: deInput, dataFim: ateInput });
  }

  function handleToday() {
    const t = todayISO();
    setDeInput(t);
    setAteInput(t);
    setDateError(null);
    setDateRange({ dataIni: t, dataFim: t });
  }

  return (
    <div>
      {/* Global header */}
      <header className="app-header">
        <div className="app-header-brand">
          <div className="app-header-title">MyFlux Preventivas</div>
          <div className="app-header-subtitle">Sistema Unificado de Manutenção Hospitalar</div>
        </div>

        {/* Unit selector */}
        <div className="unit-selector">
          {UNITS.map(({ key, label, dotColor }) => (
            <button
              key={key}
              className={`unit-tab${activeUnit === key ? ' active' : ''}`}
              onClick={() => setActiveUnit(key)}
              aria-pressed={activeUnit === key}
            >
              <span className="unit-dot" style={{ background: dotColor }} />
              {label}
            </button>
          ))}
        </div>

        <div className="app-header-clock">{clock}</div>
      </header>

      {/* Date-range filter bar */}
      <div className="date-filter-bar">
        <label style={{ fontSize: '0.84rem', fontWeight: 600 }}>De</label>
        <input
          type="date"
          value={deInput}
          onChange={(e) => setDeInput(e.target.value)}
          aria-label="Data inicial"
        />
        <label style={{ fontSize: '0.84rem', fontWeight: 600 }}>Até</label>
        <input
          type="date"
          value={ateInput}
          onChange={(e) => setAteInput(e.target.value)}
          aria-label="Data final"
        />
        <button className="btn-primary" onClick={handleApply}>Aplicar</button>
        <button className="btn-neutral" onClick={handleToday}>Hoje</button>
        {(dateRange.dataIni || dateRange.dataFim) && (
          <span style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>
            {dateRange.dataIni || '—'} → {dateRange.dataFim || '—'}
          </span>
        )}
        {dateError && (
          <span role="alert" style={{ fontSize: '0.82rem', color: 'var(--color-danger)', fontWeight: 600 }}>
            {dateError}
          </span>
        )}
      </div>

      {/* Unit modules — always mounted to preserve their state */}
      <div style={{ display: activeUnit === 'grandmassif' ? 'block' : 'none' }}>
        <GrandMassifModule dataIni={dateRange.dataIni} dataFim={dateRange.dataFim} />
      </div>
      <div style={{ display: activeUnit === 'brasilandia' ? 'block' : 'none' }}>
        <BrasilandiaModule dataIni={dateRange.dataIni} dataFim={dateRange.dataFim} />
      </div>
    </div>
  );
}
