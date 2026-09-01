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


# ── HMB (formato calendário "ESCALA DE FOLGA", a partir de setembro/2026) ──────
# Mesmo provedor/formato novo da HETRIN (Nome/Iniciais/Função/Conselho/Horário +
# dias 1-30 + Observações, separadores DIURNO/NOTURNO) — sem coluna Plantão/regime
# própria, então regime vem sempre "Fixo" aqui (a disponibilidade real é decidida
# pelo calendário dia a dia, não por paridade).

@pytestmark_hmb
def test_hmb_exclui_vagas_e_contratacoes_pendentes(colab_hmb):
    nomes_norm = [n.lower() for n in colab_hmb["funcionario"]]
    assert not any("em processo de contratacao" in n or "em processo de contratação" in n for n in nomes_norm)
    assert not any("cobertura pendente" in n for n in nomes_norm)


@pytestmark_hmb
def test_hmb_turno_via_separador_diurno_noturno(colab_hmb):
    iranildo = colab_hmb[colab_hmb["funcionario"] == "Iranildo Silva dos Santos"]
    assert not iranildo.empty
    assert iranildo.iloc[0]["turno"] == "Diurno"
    assert iranildo.iloc[0]["regime"] == "Fixo"  # formato calendário não extrai par/ímpar de texto livre

    osmar = colab_hmb[colab_hmb["funcionario"] == "Osmar Silva"]
    assert not osmar.empty
    assert osmar.iloc[0]["turno"] == "Noturno"


@pytestmark_hmb
def test_hmb_disponibilidade_dia_real_bate_com_planilha(colab_hmb):
    iranildo = colab_hmb[colab_hmb["funcionario"] == "Iranildo Silva dos Santos"].iloc[0]
    assert br.esta_disponivel(iranildo, date(2026, 9, 1)) is True   # D na planilha
    assert br.esta_disponivel(iranildo, date(2026, 9, 2)) is False  # F na planilha


@pytestmark_hmb
def test_hmb_dia_fora_do_mes_e_seguro_por_padrao(colab_hmb):
    """O arquivo só cobre os dias 1-30 (setembro não tem dia 31). Preferir
    'indisponível' a adivinhar presença é o padrão seguro."""
    qualquer = colab_hmb.iloc[0]
    assert br.esta_disponivel(qualquer, date(2026, 8, 31)) is False


@pytestmark_hmb
def test_hmb_condicionado_no_texto_livre_bloqueia_via_overlay(colab_hmb):
    """Diferente da HETRIN rico/12x36 (que tem coluna Status própria), este formato
    não tem — o bloqueio de quem tem "condicionado" na Observação da planilha
    precisa vir do overlay (core/colaboradores_overlay.py), não do parser."""
    bloqueados = colab_hmb[colab_hmb["bloqueado"]]
    assert len(bloqueados) >= 1
    for _, row in bloqueados.iterrows():
        assert row["aviso"] is not None
        assert br.esta_disponivel(row, date(2026, 9, 2)) is False


# ── Isolamento entre unidades ────────────────────────────────────────────────

@pytestmark_hetrin
@pytestmark_hmb
def test_nomes_nao_se_repetem_entre_hetrin_e_hmb(colab_hetrin, colab_hmb):
    nomes_hetrin = set(colab_hetrin["funcionario"])
    nomes_hmb = set(colab_hmb["funcionario"])
    assert nomes_hetrin.isdisjoint(nomes_hmb)


# ── Seleção de arquivo não pode depender de mtime ────────────────────────────
# Bug real de produção: escolher entre a planilha antiga e a nova por data de
# modificação do arquivo funcionava local, mas quebrava depois do deploy — um
# checkout via git/Docker grava a mesma mtime (ou uma ordem arbitrária) pros
# arquivos copiados juntos, então "o mais recente por mtime" parava de significar
# "o mais recente de verdade" assim que o app ia pro Railway. A escolha precisa
# ser baseada no conteúdo do arquivo (formato rico), nunca em metadado do
# sistema de arquivos.

_TEM_DOIS_ARQUIVOS_HETRIN = os.path.exists(gm.DATA_DIR) and sum(
    1 for f in os.listdir(gm.DATA_DIR) if f.lower().endswith(".xlsx") and "escala" in f.lower()
) >= 2
_TEM_DOIS_ARQUIVOS_HMB = os.path.exists(br.DATA_DIR) and sum(
    1 for f in os.listdir(br.DATA_DIR) if f.lower().endswith(".xlsx") and "escala" in f.lower()
) >= 2


@pytest.mark.skipif(not _TEM_DOIS_ARQUIVOS_HETRIN, reason="precisa da planilha antiga e da nova lado a lado")
def test_hetrin_escolhe_formato_rico_mesmo_com_mtime_do_antigo_mais_novo():
    caminhos = [
        os.path.join(gm.DATA_DIR, f) for f in os.listdir(gm.DATA_DIR)
        if f.lower().endswith(".xlsx") and "escala" in f.lower()
    ]
    antigo = max(caminhos, key=lambda f: os.path.getmtime(f) if "hetrin" not in f.lower() else -1)
    mtimes_originais = {f: os.stat(f) for f in caminhos}
    # força o antigo a ter a mtime mais recente de todas — simula o cenário real
    agora = max(os.path.getmtime(f) for f in caminhos) + 3600
    os.utime(antigo, (agora, agora))
    try:
        gm.invalidar_cache()
        df = gm.carregar_colaboradores()
        assert "bloqueado" in df.columns  # só o parser novo produz essa coluna
    finally:
        st = mtimes_originais[antigo]
        os.utime(antigo, (st.st_atime, st.st_mtime))
        gm.invalidar_cache()


# ── HETRIN (formato calendário "ESCALA DE FOLGA", a partir de setembro/2026) ────
# Provedor novo (Energia Verde Norte) — sem coluna Equipe/Status, só Nome/Iniciais/
# Função/Conselho/Horário + dias 1-30 + Observações, com separadores DIURNO/NOTURNO
# na primeira coluna. Achado ao migrar a planilha real: linhas "POSIÇÃO NÃO COBERTA"
# (vaga em aberto, sem pessoa real) não tinham nenhuma proteção nesse parser —
# entravam como um "colaborador" fantasma, igual ao bug de legenda vazando que já
# tínhamos corrigido nos outros formatos.

def _df_calendario_escala_de_folga():
    linhas = [
        ["Nome", "Iniciais", "Função", "Conselho", "Horário"] + list(range(1, 31)) + ["Observações"],
        ["DIURNO"] + [None] * 35,
        ["Fulano de Tal", "FT", "Eletricista", "", "07:00–19:00"] + (["D", "F"] * 15) + [""],
        ["POSIÇÃO NÃO COBERTA", "", "Técnico de Climatização", "", "Conforme"] + [""] * 30 + ["Vaga em aberto."],
        ["NOTURNO"] + [None] * 35,
        ["Vaga - Folguista Noturno", "", "Aux. Eletricista", "", "19:00–07:00"] + [""] * 30 + ["Vaga."],
        ["Ciclana da Silva", "CS", "Aux. Eletricista", "", "19:00–07:00"] + (["N", "F"] * 15) + [""],
    ]
    return pd.DataFrame(linhas)


def test_hetrin_calendario_exclui_posicao_nao_coberta():
    df_raw = _df_calendario_escala_de_folga()
    resultado = gm._parse_calendario_gm(df_raw)
    assert resultado is not None
    nomes = resultado["funcionario"].tolist()
    assert "Fulano de Tal" in nomes
    assert "Ciclana da Silva" in nomes
    assert not any("posi" in n.lower() and "coberta" in n.lower() for n in nomes)
    assert not any(n.lower().startswith("vaga") for n in nomes)
    assert len(resultado) == 2


def test_hetrin_calendario_turno_via_separador_diurno_noturno():
    df_raw = _df_calendario_escala_de_folga()
    resultado = gm._parse_calendario_gm(df_raw)
    fulano = resultado[resultado["funcionario"] == "Fulano de Tal"].iloc[0]
    ciclana = resultado[resultado["funcionario"] == "Ciclana da Silva"].iloc[0]
    assert fulano["turno"] == "Diurno"
    assert ciclana["turno"] == "Noturno"


@pytest.mark.skipif(not _TEM_DOIS_ARQUIVOS_HMB, reason="precisa da planilha antiga e da nova lado a lado")
def test_hmb_escolhe_formato_rico_mesmo_com_mtime_do_antigo_mais_novo():
    caminhos = [
        os.path.join(br.DATA_DIR, f) for f in os.listdir(br.DATA_DIR)
        if f.lower().endswith(".xlsx") and "escala" in f.lower()
    ]
    antigo = max(caminhos, key=lambda f: os.path.getmtime(f) if "escala_hmb" not in f.lower() else -1)
    mtimes_originais = {f: os.stat(f) for f in caminhos}
    agora = max(os.path.getmtime(f) for f in caminhos) + 3600
    os.utime(antigo, (agora, agora))
    try:
        br.invalidar_cache()
        df = br.carregar_colaboradores()
        assert "tipo_posto" in df.columns  # só o parser novo produz essa coluna
    finally:
        st = mtimes_originais[antigo]
        os.utime(antigo, (st.st_atime, st.st_mtime))
        br.invalidar_cache()
