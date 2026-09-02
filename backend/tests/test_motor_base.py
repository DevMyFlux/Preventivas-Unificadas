"""Testes do motor de recomendação compartilhado (core/motor_base.py)."""
from datetime import date

import pandas as pd
import pytest

from core.motor_base import (
    _cargo_compativel,
    _tier_cargo,
    calcular_score,
    classificar_categoria,
    classificar_complexidade,
    extrair_andar,
    indicar_responsavel,
    is_critico,
    COMPLEXIDADE_ALTA,
    COMPLEXIDADE_BAIXA,
    COMPLEXIDADE_MEDIA,
)


def test_classificar_categoria_eletrica():
    assert classificar_categoria("Manutenção quadro elétrico", "Bloco A", "") == "Elétrica"


def test_classificar_categoria_refrigeracao():
    assert classificar_categoria("Limpeza do chiller", "", "Ar condicionado split") == "Refrigeração"


def test_classificar_categoria_hidraulico():
    assert classificar_categoria("Troca de hidrômetro", "", "") == "Hidráulico"


def test_classificar_categoria_geral_default():
    assert classificar_categoria("Serviço qualquer sem palavra-chave", "Almoxarifado", "") == "Geral"


def test_is_critico_uti():
    assert is_critico("UTI Adulto") is True
    assert is_critico("Recepção") is False


def test_score_indisponivel_e_sempre_minimo():
    score = calcular_score(
        cargo="Eletricista", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=5, exp_ativo=5, carga_at=0, disponivel=False,
    )
    assert score == -999


def test_score_cargo_compativel_maior_que_incompativel():
    score_compativel = calcular_score(
        cargo="Eletricista", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    score_incompativel = calcular_score(
        cargo="Encanador", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    assert score_compativel > score_incompativel


def test_score_habilidade_compativel_aumenta_score():
    base = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    com_habilidade = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
        habilidades=["aux_eletrica"],
    )
    assert com_habilidade > base


def test_score_habilidade_categoria_diferente_nao_conta():
    base = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    com_habilidade_errada = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
        habilidades=["aux_hidraulica"],
    )
    assert com_habilidade_errada == base


def test_score_turno_correto_soma_pontos():
    diurno_no_turno = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Geral", turno_collab="Diurno", hora_os=10,
        setor="", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    diurno_fora_do_turno = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Geral", turno_collab="Noturno", hora_os=10,
        setor="", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    assert diurno_no_turno > diurno_fora_do_turno


def test_score_carga_penaliza():
    sem_carga = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Geral", turno_collab="Diurno", hora_os=10,
        setor="", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    com_carga = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Geral", turno_collab="Diurno", hora_os=10,
        setor="", exp_tipo=0, exp_ativo=0, carga_at=3, disponivel=True,
    )
    assert com_carga < sem_carga


def _colaboradores_df():
    return pd.DataFrame([
        {"funcionario": "Ana Eletricista", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Bruno Encanador", "cargo": "Encanador", "turno": "Diurno", "regime": "Fixo"},
    ])


def test_indicar_responsavel_escolhe_cargo_compativel():
    principal, apoio, scores = indicar_responsavel(
        colaboradores=_colaboradores_df(),
        hist_tipo={}, hist_ativo={}, carga={},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal is not None
    assert principal["nome"] == "Ana Eletricista"


def test_indicar_responsavel_sem_colaboradores_retorna_none():
    principal, apoio, scores = indicar_responsavel(
        colaboradores=pd.DataFrame(), hist_tipo={}, hist_ativo={}, carga={},
        tipo="X", setor="Y", ativo="Z", data_ref=date(2026, 9, 10),
    )
    assert principal is None and apoio is None and scores == {}


def test_indicar_responsavel_respeita_disponibilidade():
    def indisponivel(row, data):
        return False

    principal, apoio, scores = indicar_responsavel(
        colaboradores=_colaboradores_df(),
        hist_tipo={}, hist_ativo={}, carga={},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), esta_disponivel_fn=indisponivel,
    )
    assert principal is None


# ── Bug corrigido: carga acumulada não pode excluir gente disponível ────────
# Antes do fix, `disponiveis` filtrava por `score > -999`, o mesmo sentinel que
# calcular_score usa para "indisponível". Como a penalidade de carga não tem teto,
# depois de várias dezenas de atribuições numa geração de preventivas de um mês
# inteiro, o score de alguém DISPONÍVEL também cruzava -999 e era excluído por
# engano — confirmado com dados reais: 1440 de 2232 preventivas de Hetrin/Set-2026
# ficavam sem recomendação por esse motivo, mesmo com os 17 colaboradores aptos.

def test_indicar_responsavel_nao_exclui_disponivel_com_carga_alta():
    carga_alta = {"Ana Eletricista": 100, "Bruno Encanador": 100}  # 100*25=2500 > qualquer score possível
    principal, apoio, scores = indicar_responsavel(
        colaboradores=_colaboradores_df(),
        hist_tipo={}, hist_ativo={}, carga=carga_alta,
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal is not None
    assert scores["Ana Eletricista"]["score"] < -999  # o score real ainda é bem negativo...
    assert principal["nome"] == "Ana Eletricista"      # ...mas ainda é escolhida, por ser a melhor disponível


def test_indicar_responsavel_prefere_menor_carga_em_empate_de_score():
    colab = pd.DataFrame([
        {"funcionario": "Ana", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Bia", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, apoio, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Ana": 3, "Bia": 1},  # mesmo score técnico, Bia tem menos carga
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal["nome"] == "Bia"


def test_indicar_responsavel_score_maior_vence_mesmo_com_mais_carga_moderada():
    """Uma pequena diferença de carga não deve derrubar quem tem vantagem técnica clara."""
    colab = pd.DataFrame([
        {"funcionario": "Especialista", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Generalista", "cargo": "Auxiliar de Manutenção", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Especialista": 1, "Generalista": 0},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal["nome"] == "Especialista"


def test_carga_dinamica_redistribui_ao_longo_de_varias_os():
    """Simula o efeito cascata da seção 10 do pedido: sem redistribuir carga, a
    mesma pessoa venceria as N atribuições seguidas. Incrementando carga a cada
    escolha (como as rotas fazem), a recomendação deve variar."""
    colab = pd.DataFrame([
        {"funcionario": "Ana", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Bruno", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Carla", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    carga = {}
    escolhidos = []
    for _ in range(6):
        principal, _, _ = indicar_responsavel(
            colaboradores=colab, hist_tipo={}, hist_ativo={}, carga=carga,
            tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
            data_ref=date(2026, 9, 10), hora_ref=10,
        )
        escolhidos.append(principal["nome"])
        carga[principal["nome"]] = carga.get(principal["nome"], 0) + 1

    # com 3 pessoas tecnicamente empatadas e 6 OS, cada uma deve aparecer pelo
    # menos uma vez — não pode ser sempre a mesma (efeito cascata)
    assert len(set(escolhidos)) == 3


# ── Cargo abreviado (planilha nova da HMB usa "Aux." em vez de "Auxiliar de") ────

@pytest.mark.parametrize("cargo", [
    "Auxiliar de Manutenção",
    "Auxiliar de Manutenção/Climatização",
    "Aux. Manutenção",
    "Aux. Manutenção / Climatização",
    "Aux Manutenção",
])
def test_cargo_auxiliar_reconhece_forma_abreviada(cargo):
    assert _cargo_compativel(cargo.lower(), "Hidráulico") is True


# ── Bug corrigido: balanceamento não pode fazer cargo incompatível ganhar de ────
# ── cargo compatível, mesmo com muita carga acumulada no compatível ─────────────
# Confirmado com dado real (Hetrin, categoria Inspeção): depois de várias dezenas
# de atribuições numa geração de preventivas, técnicos/eletricistas disponíveis
# empatavam em score com uma gestora administrativa (cargo incompatível, mas nunca
# escalada antes = carga sempre 0) — e o desempate por menor carga escolhia a
# gestora. Isso viola a regra: "balanceamento nunca deve fazer um funcionário
# tecnicamente inadequado ganhar de um funcionário tecnicamente qualificado".

def test_balanceamento_nao_supera_incompatibilidade_de_cargo():
    colab = pd.DataFrame([
        {"funcionario": "Eletricista Sobrecarregado", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Gestora Nunca Escalada", "cargo": "Gestora Local / Engenheira", "turno": "Administrativo", "regime": "Fixo"},
    ])
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Eletricista Sobrecarregado": 10, "Gestora Nunca Escalada": 0},  # -250 de penalidade no eletricista
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    # mesmo com o eletricista deeply penalizado por carga e a gestora em carga zero,
    # o eletricista (tecnicamente apto) tem que vencer
    assert principal["nome"] == "Eletricista Sobrecarregado"
    assert scores["Gestora Nunca Escalada"]["funcao_compativel"] is False
    assert scores["Eletricista Sobrecarregado"]["funcao_compativel"] is True


def test_ninguem_compativel_ainda_assim_recomenda_alguem():
    """Sem candidato compatível nenhum, o motor deve preferir indicar o melhor
    disponível a devolver 'sem candidato' — só não pode preferir o incompatível
    quando existe opção melhor (coberto pelo teste acima)."""
    colab = pd.DataFrame([
        {"funcionario": "Gestora", "cargo": "Gestora Local / Engenheira", "turno": "Administrativo", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal is not None
    assert principal["nome"] == "Gestora"


# ── exigir_turno — bug real reportado na HETRIN ──────────────────────────────────
# Plano "COLETA DIÁRIA MEDIDOR - NOTURNO - N2" (02/09/2026) recomendou Salem Abreu
# da Silva Junior, eletricista só diurno — porque preventivas futuras (sem OS real,
# sem dataHoraAbertura) sempre usavam hora_ref=8 (diurno) e o turno nunca passava de
# bônus de score, então a penalidade de carga acumulada podia fazer o turno errado
# "ganhar" de um turno certo que ainda estava escalado pra aquele dia. exigir_turno
# transforma o bônus num filtro, só quando o próprio nome do plano já é explícito
# sobre o turno — nunca pro hora_ref=8 padrão "chutado" (ver docstring da função).

def test_exigir_turno_impede_diurno_de_vencer_carga_baixa_em_plano_noturno():
    colab = pd.DataFrame([
        {"funcionario": "Salem (diurno)", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Lúcio (noturno, sobrecarregado)", "cargo": "Eletricista", "turno": "Noturno", "regime": "Fixo"},
    ])
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Salem (diurno)": 0, "Lúcio (noturno, sobrecarregado)": 5},  # -125 de penalidade no noturno
        tipo="Coleta diária medidor", setor="Área externa", ativo="Medidor de energia",
        data_ref=date(2026, 9, 2), hora_ref=20, exigir_turno=True,
    )
    # mesmo o noturno estando bem mais penalizado por carga, o turno certo tem que vencer
    assert principal["nome"] == "Lúcio (noturno, sobrecarregado)"
    assert scores["Salem (diurno)"]["turno_compativel"] is False
    assert scores["Lúcio (noturno, sobrecarregado)"]["turno_compativel"] is True


def test_exigir_turno_falso_preserva_comportamento_antigo_so_bonus():
    """Sem exigir_turno (planos sem turno explícito no nome — a maioria), a mesma
    situação de carga ainda pode virar pro diurno — comportamento pré-existente,
    não regride pra planos onde o turno é só um palpite (hora_ref=8 padrão)."""
    colab = pd.DataFrame([
        {"funcionario": "Diurno fresco", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Noturno sobrecarregado", "cargo": "Eletricista", "turno": "Noturno", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Diurno fresco": 0, "Noturno sobrecarregado": 5},
        tipo="Manutenção geral", setor="Área externa", ativo="Equipamento qualquer",
        data_ref=date(2026, 9, 2), hora_ref=8, exigir_turno=False,
    )
    assert principal["nome"] == "Diurno fresco"


def test_exigir_turno_sem_ninguem_do_turno_certo_ainda_recomenda_alguem():
    """exigir_turno não pode virar 'sem candidato' quando ninguém do turno certo
    está disponível — mesma filosofia do gate de cargo: prefere indicar alguém a
    nada, só não deixa o turno errado vencer quando existe opção certa."""
    colab = pd.DataFrame([
        {"funcionario": "Único diurno disponível", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="Coleta diária medidor", setor="Área externa", ativo="Medidor de energia",
        data_ref=date(2026, 9, 2), hora_ref=20, exigir_turno=True,
    )
    assert principal is not None
    assert principal["nome"] == "Único diurno disponível"
    assert scores["Único diurno disponível"]["turno_compativel"] is False


# ── classificar_categoria: tipo_os prioriza sobre setor/ativo ───────────────────
# Bug real confirmado por investigação (Hetrin, set/2026): William Miranda de Moraes
# (Técnico de Climatização, Noturno) foi recomendado numa ronda ELÉTRICA de
# Iluminação/Tomadas (plano "PM - RONDA ILUMINAÇÃO/TOMADAS - DIA - D1") porque o
# SETOR da ocorrência ("BLOCO 4 1º ANDAR - CASA DE MÁQUINAS CLIMATIZAÇÃO") continha a
# palavra "climatização", que batia em _KW_REFRIG antes de "iluminação"/"tomada"
# (_KW_ELETRICA) serem sequer considerados — a versão antiga concatenava
# tipo_os+setor+ativo num único texto sem dar prioridade a de onde veio a keyword.

def test_classificar_categoria_prioriza_tipo_os_sobre_setor():
    categoria = classificar_categoria(
        "PM - RONDA ILUMINAÇÃO/TOMADAS - DIA - D1",
        "BLOCO 4 1º ANDAR - CASA DE MÁQUINAS CLIMATIZAÇÃO",
        "",
    )
    assert categoria == "Elétrica"


def test_classificar_categoria_cai_pro_setor_so_se_tipo_os_nao_bater_nada():
    """Sem sinal nenhum no tipo_os, setor/ativo continuam servindo de sinal — não é
    que o setor deixou de importar, só que ele vira sinal secundário."""
    categoria = classificar_categoria("Serviço qualquer sem palavra-chave", "", "Ar condicionado split")
    assert categoria == "Refrigeração"


def test_bug_william_miranda_nao_fica_mais_compativel_por_engano():
    categoria = classificar_categoria(
        "PM - RONDA ILUMINAÇÃO/TOMADAS - DIA - D1",
        "BLOCO 4 1º ANDAR - CASA DE MÁQUINAS CLIMATIZAÇÃO",
        "",
    )
    assert _cargo_compativel("técnico de climatização", categoria) is False
    assert _cargo_compativel("eletricista", categoria) is True


# ── classificar_categoria: keywords novas (regras do email HETRIN) ──────────────

@pytest.mark.parametrize("tipo_os, categoria_esperada", [
    ("PM - RONDA SEMANAL - QUADROS DE DISTRIBUIÇÃO", "Elétrica"),
    ("PM - RONDA SEMANAL - QUADROS HVAC", "Elétrica"),
    ("PM - RONDA DIÁRIA - SISTEMA DE AR COMPRIMIDO - ÍMPAR", "Refrigeração"),
    ("PM MENSAL - SISTEMA TERMOSSOLAR - HETRIN - DIURNO", "Refrigeração"),
])
def test_classificar_categoria_novas_keywords_email(tipo_os, categoria_esperada):
    assert classificar_categoria(tipo_os, "", "") == categoria_esperada


def test_quadros_hvac_nao_aceita_mais_tecnico_climatizacao():
    """Bug confirmado por investigação: sem a keyword, 'QUADROS HVAC' caía em
    'Inspeção' genérica e aceitava Técnico de Climatização como apto — mesmo sendo um
    plano elétrico (EXCLUSIVAMENTE Eletricistas, pelo pedido da supervisão)."""
    categoria = classificar_categoria("PM - RONDA SEMANAL - QUADROS HVAC", "", "")
    assert _cargo_compativel("técnico de climatização", categoria) is False
    assert _cargo_compativel("eletricista", categoria) is True


def test_limpeza_nobreak_nao_vira_alta_so_por_causa_do_equipamento():
    """'Limpeza' é baixa complexidade por definição, mesmo perto de um nobreak —
    checado antes das keywords de equipamento (ver classificar_complexidade)."""
    assert classificar_complexidade("PM - LIMPEZA GERAL - SALA DOS NOBREAKS", "", "") == COMPLEXIDADE_BAIXA


# ── Bug real confirmado: oficina "CCO" colidia com keyword elétrica ─────────────
# A oficina real "CENTRO DE COMANDO DA OPERAÇÃO - CCO" (usada nos 6 planos de coleta
# diária de medidor/hidrômetro da HETRIN) continha "cco"/"comando", que eram keywords
# de _KW_ELETRICA — como routes.py concatena tipo+descricao+oficina antes de chamar
# indicar_responsavel, isso forçava 'Elétrica' pra TODAS as coletas e excluía por
# engano os auxiliares de climatização/manutenção geral (ex: Isabel Alves Dias) que a
# escala nomeada da supervisão exige pra essas coletas.

def test_coleta_medidor_com_oficina_cco_nao_vira_eletrica():
    tipo_classif = "Preventiva COLETA DIÁRIA MEDIDOR - NOTURNO - N2 CENTRO DE COMANDO DA OPERAÇÃO - CCO"
    categoria = classificar_categoria(tipo_classif, "", "")
    assert categoria != "Elétrica"
    assert _cargo_compativel("aux. manutenção / climatização", categoria) is True


def test_coleta_hidrometro_nao_vira_hidraulico_exclusivo():
    """'coleta' tem prioridade sobre 'hidrômetro' (_KW_HIDRO) — bug real confirmado
    por validação com dado real: classificar como 'Hidráulico' excluía Aux. Eletricista
    (cargo real de Jussara/Eduonete, nomeadas pela supervisão pra essa coleta) do
    cargo compatível, e 28/28 ocorrências de setembro/2026 foram pra outra pessoa."""
    tipo_classif = "Preventiva COLETA DIÁRIA HIDRÔMETRO -DIURNO - D1 CENTRO DE COMANDO DA OPERAÇÃO - CCO"
    categoria = classificar_categoria(tipo_classif, "", "")
    assert categoria == "Inspeção"
    assert _cargo_compativel("aux. eletricista", categoria) is True


# ── classificar_complexidade ─────────────────────────────────────────────────────

@pytest.mark.parametrize("tipo_os, esperado", [
    ("PM - LIMPEZA GERAL - SALA DOS NOBREAKS", COMPLEXIDADE_BAIXA),
    ("COLETA DIÁRIA MEDIDOR - DIURNO - D1", COMPLEXIDADE_BAIXA),
    ("COLETA DIÁRIA HIDRÔMETRO -DIURNO - D1", COMPLEXIDADE_BAIXA),
    ("PM - RONDA SEMANAL - INSPEÇÃO NOBREAKS", COMPLEXIDADE_ALTA),
    ("PM - RONDA SEMANAL - QUADROS DE DISTRIBUIÇÃO", COMPLEXIDADE_ALTA),
    ("PM RONDA PERIÓDICA - FANCOILS HIDRÔNICOS", COMPLEXIDADE_ALTA),
    ("PM MENSAL - SPLIT - HETRIN", COMPLEXIDADE_ALTA),
    ("PM - RONDA ILUMINAÇÃO/TOMADAS - DIA - D1", COMPLEXIDADE_MEDIA),
])
def test_classificar_complexidade_casos_reais(tipo_os, esperado):
    assert classificar_complexidade(tipo_os, "", "") == esperado


# ── _tier_cargo ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cargo, tier_esperado", [
    ("Eletricista", "tecnico"),
    ("Técnico de Climatização", "tecnico"),
    ("Aux. Eletricista", "auxiliar"),
    ("Aux. Manutenção / Climatização", "auxiliar"),
    ("Auxiliar Administrativo", "outro"),
    ("Gerente de Equipe/Engenheira", "outro"),
])
def test_tier_cargo(cargo, tier_esperado):
    assert _tier_cargo(cargo.lower()) == tier_esperado


def test_score_complexidade_favorece_auxiliar_em_tarefa_baixa():
    colab = pd.DataFrame([
        {"funcionario": "Auxiliar", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Tecnico", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="COLETA DIÁRIA MEDIDOR - DIURNO - D1", setor="", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal["nome"] == "Auxiliar"
    assert scores["Auxiliar"]["complexidade"] == COMPLEXIDADE_BAIXA


def test_score_complexidade_favorece_tecnico_em_tarefa_alta():
    colab = pd.DataFrame([
        {"funcionario": "Auxiliar", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Tecnico", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="PM - RONDA SEMANAL - QUADROS DE DISTRIBUIÇÃO", setor="", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal["nome"] == "Tecnico"
    assert scores["Tecnico"]["complexidade"] == COMPLEXIDADE_ALTA


# ── Gate de complexidade: carga acumulada não pode inverter o tier certo ────────
# Bug real confirmado por validação com dado real (HMB, setembro/2026 inteiro): com
# complexidade sendo SÓ bônus de score (sem gate), a penalidade de carga_alta
# acumulada (sem teto) podia superar o bônus pontual ao longo do mês — 311
# ocorrências de Alta complexidade acabaram indo pra um auxiliar (o oposto do
# pedido), só porque o técnico "certo" já tinha acumulado muita carga_alta. Mesmo
# raciocínio do teste 'test_balanceamento_nao_supera_incompatibilidade_de_cargo',
# agora pra hierarquia técnico/auxiliar.

def test_gate_complexidade_tecnico_vence_mesmo_com_muita_carga_alta():
    colab = pd.DataFrame([
        {"funcionario": "Tecnico Sobrecarregado", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Auxiliar Nunca Escalado", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Tecnico Sobrecarregado": 20, "Auxiliar Nunca Escalado": 0},
        carga_alta={"Tecnico Sobrecarregado": 20, "Auxiliar Nunca Escalado": 0},
        tipo="PM - RONDA SEMANAL - QUADROS DE DISTRIBUIÇÃO", setor="", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    # mesmo com o técnico deeply penalizado por carga/carga_alta, ele tem que vencer
    # numa tarefa de Alta complexidade — o auxiliar não pode "ganhar" só por ter
    # carga zero
    assert principal["nome"] == "Tecnico Sobrecarregado"
    assert scores["Tecnico Sobrecarregado"]["tier_adequado"] is True
    assert scores["Auxiliar Nunca Escalado"]["tier_adequado"] is False


def test_gate_complexidade_auxiliar_vence_mesmo_com_muita_carga():
    colab = pd.DataFrame([
        {"funcionario": "Auxiliar Sobrecarregado", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Tecnico Nunca Escalado", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Auxiliar Sobrecarregado": 20, "Tecnico Nunca Escalado": 0},
        tipo="COLETA DIÁRIA MEDIDOR - DIURNO - D1", setor="", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal["nome"] == "Auxiliar Sobrecarregado"


def test_gate_complexidade_media_nao_restringe_tier():
    """Complexidade Média (default) não tem tier preferencial — o gate não deve
    restringir nada, deixando o critério normal (score/carga) decidir."""
    colab = pd.DataFrame([
        {"funcionario": "Auxiliar", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Tecnico", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Auxiliar": 0, "Tecnico": 5},
        tipo="PM - RONDA ILUMINAÇÃO/TOMADAS - DIA - D1", setor="", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=8,
    )
    assert scores["Auxiliar"]["complexidade"] == COMPLEXIDADE_MEDIA
    assert scores["Auxiliar"]["tier_adequado"] is True
    assert scores["Tecnico"]["tier_adequado"] is True
    # com Média, o desempate é só carga — o auxiliar (carga menor) vence
    assert principal["nome"] == "Auxiliar"


def test_gate_complexidade_nao_esvazia_pool_sem_tier_certo():
    """Sem ninguém do tier adequado disponível, prefere indicar o melhor disponível
    a devolver 'sem candidato' — mesma filosofia soft dos outros gates."""
    colab = pd.DataFrame([
        {"funcionario": "Único Auxiliar Disponível", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="PM - RONDA SEMANAL - QUADROS DE DISTRIBUIÇÃO", setor="", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal is not None
    assert principal["nome"] == "Único Auxiliar Disponível"


# ── extrair_andar ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("setor, esperado", [
    ("BLOCO 4 1º ANDAR - ENFERMARIA CIRÚRGICA 213", "1º ANDAR"),
    ("BLOCO B 4º ANDA - CONFORTO", "4º ANDAR"),  # erro de digitação real (sem o R)
    ("BLOCO A 1SS - GERADORES", "1º SUBSOLO"),
    ("BLOCO B TÉRREO - EMERGÊNCIA", "TÉRREO"),
    ("BLOCO 6 1º ANDAR - CME - LAJE TÉCNICA", "1º ANDAR"),  # andar numerado tem prioridade
    ("BLOCO B COBERTURA - CASA DE MAQUINA ELEVADORES 01", "COBERTURA"),
    ("ÁREA EXTERNA - CENTRAL DE RESÍDUOS - RESÍDUOS QUÍMICOS", None),
    ("", None),
    (None, None),
])
def test_extrair_andar(setor, esperado):
    assert extrair_andar(setor) == esperado


def test_andar_repetido_favorece_colaborador_ja_alocado_no_mesmo_andar():
    colab = pd.DataFrame([
        {"funcionario": "Ana", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Bia", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    andares = {"Ana": {"1º ANDAR"}}
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="PM - RONDA ILUMINAÇÃO/TOMADAS", setor="BLOCO 4 1º ANDAR - ENFERMARIA", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10, andares_colaborador=andares,
    )
    assert principal["nome"] == "Ana"
    assert scores["Ana"]["mesmo_andar"] is True
    assert scores["Bia"]["mesmo_andar"] is False


def test_andar_nunca_quebra_cargo_ou_turno():
    """O bônus de andar só decide entre quem já passou pelos gates de cargo/turno —
    nunca faz alguém tecnicamente inadequado (ou do turno errado) vencer."""
    colab = pd.DataFrame([
        {"funcionario": "Eletricista certo", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Encanador no mesmo andar", "cargo": "Encanador", "turno": "Diurno", "regime": "Fixo"},
    ])
    andares = {"Encanador no mesmo andar": {"1º ANDAR"}}
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="PM - RONDA ILUMINAÇÃO/TOMADAS", setor="BLOCO 4 1º ANDAR - ENFERMARIA", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10, andares_colaborador=andares,
    )
    assert principal["nome"] == "Eletricista certo"


# ── carga_alta: balanceamento de tarefas de alta complexidade ───────────────────

def test_carga_alta_penaliza_quem_ja_acumulou_muitas_tarefas_complexas():
    colab = pd.DataFrame([
        {"funcionario": "Sobrecarregado de Alta", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Fresco", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    carga_alta = {"Sobrecarregado de Alta": 10, "Fresco": 0}
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="PM - RONDA SEMANAL - QUADROS DE DISTRIBUIÇÃO", setor="", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10, carga_alta=carga_alta,
    )
    assert principal["nome"] == "Fresco"


def test_carga_alta_nao_penaliza_tarefa_baixa():
    """carga_alta só entra em jogo quando a tarefa ATUAL é Alta complexidade — não
    penaliza quem já fez tarefas complexas antes, se a tarefa de agora é simples."""
    colab = pd.DataFrame([
        {"funcionario": "Historico de Alta", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Sem historico", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    carga_alta = {"Historico de Alta": 10, "Sem historico": 0}
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="COLETA DIÁRIA MEDIDOR - DIURNO - D1", setor="", ativo="",
        data_ref=date(2026, 9, 10), hora_ref=10, carga_alta=carga_alta,
    )
    # mesmo score pros dois (mesma carga_alta não se aplica, mesma carga=0) -> empate,
    # que aqui só pode ser resolvido pela ordem de iteração; o importante é que os
    # dois têm o MESMO score (não houve penalidade indevida)
    assert scores["Historico de Alta"]["score"] == scores["Sem historico"]["score"]


# ── nomes_permitidos: escala nomeada obrigatória (coleta HETRIN) ────────────────

def test_nomes_permitidos_restringe_quando_ha_gente_no_conjunto():
    colab = pd.DataFrame([
        {"funcionario": "Isabel Alves Dias", "cargo": "Aux. Manutenção / Climatização", "turno": "Noturno", "regime": "Fixo"},
        {"funcionario": "Outro Auxiliar", "cargo": "Aux. Manutenção", "turno": "Noturno", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="COLETA DIÁRIA MEDIDOR - NOTURNO - N2", setor="", ativo="",
        data_ref=date(2026, 9, 2), hora_ref=20,
        nomes_permitidos={"Isabel Alves Dias"},
    )
    assert principal["nome"] == "Isabel Alves Dias"


def test_nomes_permitidos_nao_esvazia_pool_quando_ninguem_do_conjunto_disponivel():
    """Mesma filosofia soft dos outros gates: se ninguém do conjunto nomeado está
    disponível, prefere indicar o melhor disponível a devolver 'sem candidato'."""
    colab = pd.DataFrame([
        {"funcionario": "Único disponível", "cargo": "Aux. Manutenção", "turno": "Noturno", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="COLETA DIÁRIA MEDIDOR - NOTURNO - N2", setor="", ativo="",
        data_ref=date(2026, 9, 2), hora_ref=20,
        nomes_permitidos={"Alguém que não está escalado hoje"},
    )
    assert principal is not None
    assert principal["nome"] == "Único disponível"


def test_nomes_permitidos_none_nao_restringe_nada():
    """None (default) é o comportamento pré-existente — sem restrição nenhuma."""
    colab = pd.DataFrame([
        {"funcionario": "Ana", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10, nomes_permitidos=None,
    )
    assert principal["nome"] == "Ana"
