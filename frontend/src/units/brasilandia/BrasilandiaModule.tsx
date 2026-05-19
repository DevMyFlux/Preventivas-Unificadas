import { useState } from 'react';
import { buildUnitClient } from '../../shared/api/client';
import PlanosPanel from '../../shared/components/PlanosPanel';
import PreventivasPanel from '../../shared/components/PreventivasPanel';
import ColaboradoresPanel from '../../shared/components/ColaboradoresPanel';
import ColaboradorModal from '../../shared/components/ColaboradorModal';

const apiClient = buildUnitClient('/api/brasilandia');

const TABS = [
  { key: 'planos',        label: 'Planos' },
  { key: 'preventivas',   label: 'Preventivas' },
  { key: 'colaboradores', label: 'Colaboradores' },
] as const;

type TabKey = typeof TABS[number]['key'];

interface BrasilandiaModuleProps {
  dataIni: string;
  dataFim: string;
}

export default function BrasilandiaModule({ dataIni, dataFim }: BrasilandiaModuleProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('planos');
  const [counts, setCounts] = useState<Record<TabKey, number>>({ planos: 0, preventivas: 0, colaboradores: 0 });
  const [selectedColaborador, setSelectedColaborador] = useState<string | null>(null);

  const setCount = (key: TabKey) => (n: number) => setCounts((c) => ({ ...c, [key]: n }));

  return (
    <div>
      {/* Inner tab bar */}
      <div className="inner-tab-bar">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            className={`inner-tab${activeTab === key ? ' active' : ''}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
            <span className="badge b-blue" style={{ minWidth: 22, textAlign: 'center' }}>
              {counts[key]}
            </span>
          </button>
        ))}
      </div>

      <main style={{ maxWidth: 1500, margin: '0 auto', padding: 22 }}>
        <div style={{ display: activeTab === 'planos' ? 'block' : 'none' }}>
          <PlanosPanel apiClient={apiClient} onCountChange={setCount('planos')} autoLoad />
        </div>
        <div style={{ display: activeTab === 'preventivas' ? 'block' : 'none' }}>
          <PreventivasPanel
            apiClient={apiClient}
            dataIni={dataIni}
            dataFim={dataFim}
            onCountChange={setCount('preventivas')}
          />
        </div>
        <div style={{ display: activeTab === 'colaboradores' ? 'block' : 'none' }}>
          <ColaboradoresPanel
            apiClient={apiClient}
            onCountChange={setCount('colaboradores')}
            onSelectColaborador={setSelectedColaborador}
            autoLoad
          />
        </div>
      </main>

      <ColaboradorModal
        apiClient={apiClient}
        nome={selectedColaborador}
        onClose={() => setSelectedColaborador(null)}
      />
    </div>
  );
}
