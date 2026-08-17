"""
Testes do novo formato de escala (HETRIN rico/12x36 e HMB rico/por-grupo), contra os
dados reais das planilhas — não só casos sintéticos. Cobre especificamente:
- extração correta dos campos novos (cargo, turno, bloqueio/aviso);
- exclusão de linhas que não são colaboradores reais (vaga, legenda, em contratação);
- a colisão do código "T" entre o formato antigo (T=trabalhando) e o novo da HETRIN
  (T=Transição-não-escalar), que usam dicionários separados de propósito;
- isolamento entre unidades (nenhum nome se repete entre as duas planilhas).
"""
import os
from datetime import date

import pandas as pd
import pytest

from units.brasilandia import colaboradores as br
from units.grand_massif import colaboradores as gm

HETRIN_DISPONIVEL = os.path.exists(gm.DATA_DIR) and any(
    "hetrin" in f.lower() for f in os.listdir(gm.DATA_DIR)
) if os.path.exists(gm.DATA_DIR) else False
HMB_DISPONIVEL = os.path.exists(br.DATA_DIR) and any(
    "hmb" in f.lower() for f in os.listdir(br.DATA_DIR)
) if os.path.exists(br.DATA_DIR) else False

pytestmark_hetrin = pytest.mark.skipif(not HETRIN_DISPONIVEL, reason="planilha real da Hetrin não presente neste ambiente")
pytestmark_hmb = pytest.mark.skipif(not HMB_DISPONIVEL, reason="planilha real da HMB não presente neste ambiente")


@pytest.fixture
def colab_hetrin():
    gm.invalidar_cache()
    df = gm.carregar_colaboradores()
    assert df is not None, "parser não conseguiu ler a planilha real da Hetrin"
    return df


@pytest.fixture
def colab_hmb():
    br.invalidar_cache()
    df = br.carregar_colaboradores()
    assert df is not None, "parser não conseguiu ler a planilha real da HMB"
    return df


# ── HETRIN (formato rico/12x36) ──────────────────────────────────────────────

@pytestmark_hetrin
def test_hetrin_carrega_apenas_colaboradores_reais(colab_hetrin):
    nomes = colab_hetrin["funcionario"].tolist()
    # linhas de legenda/nota nunca podem aparecer como "colaborador"
    for lixo in ("P", "F", "T", "N", "V", "C", "RES", "ADM"):
        assert lixo not in nomes
    assert not any("legenda" in n.lower() or "atenção" in n.lower() or "nota" in n.lower() for n in nomes)
    # vaga em aberto não é colaborador
    assert not any(n.upper().startswith("VAGA") for n in nomes)


@pytestmark_hetrin
def test_hetrin_condicionado_bloqueia_com_aviso(colab_hetrin):
    condicionados = colab_hetrin[colab_hetrin["bloqueado"]]
    assert len(condicionados) >= 1
    for _, row in condicionados.iterrows():
        assert row["aviso"] is not None
        assert "Condicionado" in row["aviso"]


@pytestmark_hetrin
def test_hetrin_esta_disponivel_respeita_bloqueio(colab_hetrin):
    bloqueados = colab_hetrin[colab_hetrin["bloqueado"]]
    assert len(bloqueados) >= 1
    for _, row in bloqueados.iterrows():
        # mesmo que o código do dia diga presença, bloqueado nunca está disponível
        assert gm.esta_disponivel(row, date(2026, 8, 20)) is False


@pytestmark_hetrin
def test_hetrin_turno_normalizado_para_igualdade_exata(colab_hetrin):
    """calcular_score() compara turno com == 'diurno'/'noturno' — 'Diurno alternado'
    cru quebraria isso silenciosamente."""
    turnos = set(colab_hetrin["turno"].str.lower().unique())
    assert turnos <= {"diurno", "noturno", "administrativo", "reserva", ""}


@pytestmark_hetrin
def test_hetrin_codigo_t_nao_conta_como_presenca_no_formato_novo():
    """O 'T' do formato rico (Transição-não-escalar) é o OPOSTO do 'T' do formato
    calendário antigo (trabalhando, em STATUS_PRESENTES). Confirma que o parser novo
    usa seu próprio dicionário, não STATUS_PRESENTES."""
    assert gm._CODIGOS_FORMATO_RICO["T"] is False
    assert "T" in gm.STATUS_PRESENTES  # o antigo continua tratando T como presença


# ── HMB (formato rico/por-grupo) ─────────────────────────────────────────────

@pytestmark_hmb
def test_hmb_exclui_vagas_e_contratacoes_pendentes(colab_hmb):
    nomes_norm = [n.lower() for n in colab_hmb["funcionario"]]
    assert not any("em processo de contratacao" in n or "em processo de contratação" in n for n in nomes_norm)
    assert not any("cobertura pendente" in n for n in nomes_norm)


@pytestmark_hmb
def test_hmb_paridade_extraida_do_texto_livre(colab_hmb):
    iranildo = colab_hmb[colab_hmb["funcionario"] == "Iranildo Silva dos Santos"]
    assert not iranildo.empty
    assert iranildo.iloc[0]["regime"] == "Par"
    assert iranildo.iloc[0]["turno"] == "Diurno"


@pytestmark_hmb
def test_hmb_disponibilidade_dia_real_bate_com_planilha(colab_hmb):
    iranildo = colab_hmb[colab_hmb["funcionario"] == "Iranildo Silva dos Santos"].iloc[0]
    assert br.esta_disponivel(iranildo, date(2026, 8, 16)) is True   # par, P na planilha
    assert br.esta_disponivel(iranildo, date(2026, 8, 17)) is False  # ímpar, ausente


@pytestmark_hmb
def test_hmb_dia_fora_da_quinzena_e_seguro_por_padrao(colab_hmb):
    """O arquivo só cobre 16-31/08 — dias 1-15 não têm dado nenhum. Preferir
    'indisponível' a adivinhar presença é o padrão seguro."""
    qualquer = colab_hmb.iloc[0]
    assert br.esta_disponivel(qualquer, date(2026, 8, 5)) is False


# ── Isolamento entre unidades ────────────────────────────────────────────────

@pytestmark_hetrin
@pytestmark_hmb
def test_nomes_nao_se_repetem_entre_hetrin_e_hmb(colab_hetrin, colab_hmb):
    nomes_hetrin = set(colab_hetrin["funcionario"])
    nomes_hmb = set(colab_hmb["funcionario"])
    assert nomes_hetrin.isdisjoint(nomes_hmb)
