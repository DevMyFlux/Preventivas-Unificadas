"""
Regras nominais da HMB (5.4 rondas diárias, 5.5 oficina de ar comprimido e vácuo):
tabela turno × tipo de dia (do DIA DE EXECUÇÃO), validação de nomes e ambiguidades.
"""
from datetime import date

from core.regras.atribuicao import ContextoOcorrencia, aplicar_regras, paridade_do_dia, resolver_regras
from core.regras.nomes import resolver_alias
from tests.fakes import colaboradores_df
from units.brasilandia.regras import OFICINA_AR_COMPRIMIDO_VACUO, REGRAS as REGRAS_ATIVAS, RONDA_DIARIA

# A tabela das rondas está DESATIVADA no produto (rondas diárias são automáticas no Neovero); o mecanismo e a tabela
# continuam testados aqui, com a regra incluída explicitamente.
REGRAS = [RONDA_DIARIA, OFICINA_AR_COMPRIMIDO_VACUO]

# Quadro da HMB em out/2026 (nomes/cargos/regimes reais da escala)
QUADRO = [
    {"funcionario": "Iranildo Silva dos Santos", "cargo": "Eletricista", "regime": "Ímpar"},
    {"funcionario": "Michael de Campos Eguez", "cargo": "Eletricista", "regime": "Par"},
    {"funcionario": "Michael Kelvin de Abreu Moraes", "cargo": "Aux. Manutenção Elétrica", "regime": "Par"},
    {"funcionario": "Diego Reimberg", "cargo": "Eletricista", "turno": "Noturno", "regime": "Ímpar"},
    {"funcionario": "Diego Ferreira da Cunha", "cargo": "Eletricista", "turno": "Noturno", "regime": "Par"},
    {"funcionario": "Douglas Rodrigues", "cargo": "Técnico de Climatização", "regime": "Ímpar"},
    {"funcionario": "Douglas dos Santos Vieira", "cargo": "Aux. Manutenção / Climatização", "regime": "Ímpar"},
    {"funcionario": "Gustavo Rafael Pereira Vargas", "cargo": "Aux. Manutenção / Climatização", "regime": "Par"},
    {"funcionario": "Israel Pereira Bomfim", "cargo": "Técnico de Climatização", "regime": "Ímpar"},
]


def _ctx(descricao, dia, *, oficina="ELÉTRICA/QGBT", tipo_id=8, periodicidade=1, unidade="D", turno=None):
    from core.planejamento import detectar_turno
    return ContextoOcorrencia(descricao, oficina, tipo_id, periodicidade, unidade, dia, turno or detectar_turno(descricao))


def _resolvidas(confirmacoes=None):
    return resolver_regras(REGRAS, colaboradores_df(QUADRO), confirmacoes)


# ── paridade do dia de execução ───────────────────────────────────────────────

def test_paridade_usa_o_dia_de_execucao_inclusive_na_virada_de_mes():
    assert paridade_do_dia(date(2026, 10, 13)) == "Ímpar"
    assert paridade_do_dia(date(2026, 10, 14)) == "Par"
    assert paridade_do_dia(date(2026, 10, 31)) == "Ímpar"
    assert paridade_do_dia(date(2026, 11, 1)) == "Ímpar"   # 31 -> 1: ambos ímpares
    assert paridade_do_dia(date(2026, 11, 30)) == "Par"
    assert paridade_do_dia(date(2026, 12, 1)) == "Ímpar"
    assert paridade_do_dia(date(2026, 2, 28)) == "Par"


# ── ronda diária ──────────────────────────────────────────────────────────────

def test_ronda_diurna_impar_e_iranildo():
    ap = aplicar_regras(_resolvidas(), _ctx("PM - DIÁRIO - RONDA – CHILLERS", date(2026, 10, 13)))
    assert ap.status == "aplicada" and ap.nomes == {"Iranildo Silva dos Santos"}


def test_ronda_diurna_par_michael_e_ambigua_e_nao_escolhe_ninguem():
    ap = aplicar_regras(_resolvidas(), _ctx("PM - DIÁRIO - RONDA – CHILLERS", date(2026, 10, 14)))
    assert ap.status == "pendente"
    assert ap.nomes == frozenset()
    assert "Michael" in ap.mensagem
    assert {p.alias for p in ap.pendencias} == {"Michael"}
    assert set(ap.pendencias[0].candidatos) == {"Michael de Campos Eguez", "Michael Kelvin de Abreu Moraes"}


def test_ronda_noturna_diego_h_nao_bate_com_ninguem_e_fica_pendente():
    for dia in (date(2026, 10, 13), date(2026, 10, 14)):
        ap = aplicar_regras(_resolvidas(), _ctx("PM - DIÁRIO - RONDA – CHILLERS – NOTURNO", dia))
        assert ap.status == "pendente"
        assert ap.pendencias[0].status == "nao_encontrado"
        assert set(ap.pendencias[0].candidatos) == {"Diego Reimberg", "Diego Ferreira da Cunha"}


def test_confirmacao_humana_resolve_a_ambiguidade():
    conf = {"michael": "Michael de Campos Eguez", "diego h": "Diego Reimberg"}
    res = _resolvidas(conf)
    par = aplicar_regras(res, _ctx("PM - DIÁRIO - RONDA – CHILLERS", date(2026, 10, 14)))
    assert par.status == "aplicada" and par.nomes == {"Michael de Campos Eguez"}
    noite = aplicar_regras(res, _ctx("PM - DIÁRIO - RONDA – CHILLERS – NOTURNO", date(2026, 10, 13)))
    assert noite.status == "aplicada" and noite.nomes == {"Diego Reimberg"}


def test_confirmacao_de_pessoa_fora_do_quadro_ativo_e_rejeitada():
    res = _resolvidas({"michael": "Fulano Que Saiu"})
    ap = aplicar_regras(res, _ctx("PM - DIÁRIO - RONDA – CHILLERS", date(2026, 10, 14)))
    assert ap.status == "pendente"


def test_turno_noturno_truncado_pelo_neovero_e_reconhecido():
    # o Neovero corta o nome do plano: "...ILUMINAÇÃO 23H NOTURN"
    res = _resolvidas({"diego h": "Diego Reimberg"})
    ap = aplicar_regras(res, _ctx("PM - DIÁRIO - RONDA – LIGAR AR COND. E ILUMINAÇÃO 23H NOTURN", date(2026, 10, 13)))
    assert ap.status == "aplicada" and ap.nomes == {"Diego Reimberg"}


def test_ronda_que_nao_e_diaria_nao_recebe_a_regra():
    ap = aplicar_regras(_resolvidas(), _ctx("PM - MENSAL – RONDA – ILUMINAÇÃO", date(2026, 10, 13), tipo_id=2,
                                            periodicidade=1, unidade="M"))
    assert ap.status == "sem_regra"


def test_ronda_identificada_pelo_tipo_8_mesmo_sem_a_palavra_ronda_no_nome():
    # "PM - DIÁRIO - MEDIÇÃO HIDROMETRO" é tipo RONDA (id 8) no Neovero
    ap = aplicar_regras(_resolvidas(), _ctx("PM - DIÁRIO - MEDIÇÃO HIDROMETRO", date(2026, 10, 13), tipo_id=8))
    assert ap.status == "aplicada" and ap.nomes == {"Iranildo Silva dos Santos"}


# ── oficina de ar comprimido e vácuo ──────────────────────────────────────────

AC = dict(oficina="AR COMPRIMIDO E VÁCUO", tipo_id=2, periodicidade=1, unidade="D")


def test_oficina_ac_vacuo_dia_impar_e_israel():
    ap = aplicar_regras(_resolvidas(), _ctx("PM - DIÁRIA - AR COMPRIMIDO", date(2026, 10, 13), **AC))
    assert ap.status == "aplicada" and ap.nomes == {"Israel Pereira Bomfim"}


def test_oficina_ac_vacuo_dia_par_tem_dois_responsaveis_sem_sobrescrever():
    ap = aplicar_regras(_resolvidas(), _ctx("PM - DIÁRIA - VÁCUO", date(2026, 10, 14), **AC))
    assert ap.status == "aplicada"
    assert ap.nomes == {"Douglas Rodrigues", "Gustavo Rafael Pereira Vargas"}


def test_divergencia_de_escala_da_regra_gera_alerta():
    """Douglas Rodrigues consta na regra para dias PARES, mas a escala dele é ÍMPAR."""
    ap = aplicar_regras(_resolvidas(), _ctx("PM - DIÁRIA - VÁCUO", date(2026, 10, 14), **AC))
    assert any("Douglas Rodrigues" in a and "Ímpar" in a for a in ap.alertas)


def test_oficina_ac_vacuo_noturno_nao_especificado_preserva_comportamento_existente():
    ap = aplicar_regras(_resolvidas(), _ctx("PM - DIÁRIA - VÁCUO - NOTURNO", date(2026, 10, 14), **AC))
    assert ap.status == "sem_regra"


def test_outra_oficina_nao_recebe_a_regra_de_ac_vacuo():
    ap = aplicar_regras(_resolvidas(), _ctx("PM - MENSAL - SPLIT", date(2026, 10, 14), oficina="CLIMATIZAÇÃO",
                                            tipo_id=2, periodicidade=1, unidade="M"))
    assert ap.status == "sem_regra"


# ── resolução de nomes ────────────────────────────────────────────────────────

def test_apelidos_inequivocos_resolvem_sozinhos():
    nomes = [r["funcionario"] for r in QUADRO]
    for alias, esperado in (("Iranildo", "Iranildo Silva dos Santos"), ("Israel", "Israel Pereira Bomfim"),
                            ("Douglas Rodrigues", "Douglas Rodrigues"),
                            ("Gustavo Rafael", "Gustavo Rafael Pereira Vargas")):
        r = resolver_alias(alias, nomes)
        assert r.status == "ok" and r.escolhido == esperado and r.origem == "unico"


def test_desligado_nao_entra_no_quadro_de_resolucao():
    quadro = [dict(r) for r in QUADRO] + [{"funcionario": "Israel Antigo Silva", "cargo": "Eletricista", "status": "Desligado"}]
    res = resolver_regras(REGRAS, colaboradores_df(quadro))
    linha = res["oficina_ar_comprimido_vacuo"].linhas[("Diurno", "Ímpar")]
    assert linha.status == "ok" and linha.nomes == ["Israel Pereira Bomfim"]


def test_rondas_diarias_nao_fazem_mais_parte_das_regras_ativas_da_hmb():
    assert [r.id for r in REGRAS_ATIVAS] == ["oficina_ar_comprimido_vacuo"]
    ap = aplicar_regras(resolver_regras(REGRAS_ATIVAS, colaboradores_df(QUADRO)),
                        _ctx("PM - DIÁRIO - RONDA – CHILLERS", date(2026, 10, 13)))
    assert ap.status == "sem_regra"          # nenhuma pendência de "Michael"/"Diego H"
