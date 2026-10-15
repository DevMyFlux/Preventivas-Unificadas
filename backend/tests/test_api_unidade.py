"""
API das unidades (blueprint único) com um Neovero falso: listagem/filtros/paginação de
preventivas, consistência listagem × totais × exportação, revisão de responsáveis, regras
nominais e tratamento de falhas do Neovero.
"""
import io
import shutil
import time
from pathlib import Path

import pytest
import requests
from openpyxl import load_workbook

from core import cache
from core.neovero_client import NeoveroConfigError, NeoveroIndisponivelError
from tests.conftest import fazer_login
from tests.fakes import colaboradores_df, item_plano, os_neovero, plano_neovero

DATA_HMB = Path(__file__).resolve().parent.parent / "data" / "hmb"
P = "/api/brasilandia"

QUADRO_HMB = [
    {"funcionario": "Iranildo Silva dos Santos", "cargo": "Eletricista", "regime": "Ímpar"},
    {"funcionario": "Michael de Campos Eguez", "cargo": "Eletricista", "regime": "Par"},
    {"funcionario": "Michael Kelvin de Abreu Moraes", "cargo": "Aux. Manutenção Elétrica", "regime": "Par"},
    {"funcionario": "Diego Reimberg", "cargo": "Eletricista", "turno": "Noturno", "regime": "Ímpar"},
    {"funcionario": "Clima Um", "cargo": "Técnico de Climatização"},
    {"funcionario": "William de Souza Lobo", "cargo": "Supervisor de Manutenção", "turno": "Administrativo"},
    {"funcionario": "Caio Cezar Santos Pereira", "cargo": "Eletricista", "status": "Desligado",
     "data_desligamento": "2026-09-18"},
]


class NeoveroFalso:
    def __init__(self):
        self.os_periodo, self.os_abertas, self.planos, self.itens = [], [], [], {}
        self.excecao = None
        self.consultas = []

    def paginar(self, headers, payload, endpoint):
        self.consultas.append((endpoint, payload))
        if self.excecao:
            raise self.excecao
        if endpoint == "/api/planosmanutencao/query":
            return list(self.planos)
        filtros = {f["property"]: f["value"] for f in payload["filterGroups"][0]["filters"]}
        return list(self.os_abertas if "situacao" in filtros else self.os_periodo)


@pytest.fixture()
def neovero(monkeypatch, tmp_path):
    from core import unit_blueprint as ub
    from units.brasilandia import colaboradores as hmb, config as cfg_hmb
    # overlay/planilhas da HMB copiados para um diretório temporário (testes nunca tocam os dados do repositório)
    destino = tmp_path / "hmb"
    shutil.copytree(DATA_HMB, destino)
    monkeypatch.setattr(cfg_hmb, "DATA_DIR", str(destino))
    monkeypatch.setattr(hmb, "DATA_DIR", str(destino))
    fake = NeoveroFalso()
    monkeypatch.setattr(ub, "get_headers", lambda: {})
    monkeypatch.setattr(ub, "paginar", fake.paginar)
    monkeypatch.setattr(ub, "buscar_itens_varios_planos", lambda h, p: fake.itens)
    hmb.invalidar_cache()
    hmb._colab_cache["df"] = colaboradores_df(QUADRO_HMB)
    hmb._colab_cache["ts"] = time.time()
    monkeypatch.setattr("core.preventivas.hoje_local", lambda: __import__("datetime").date(2026, 10, 14))
    yield fake
    hmb.invalidar_cache()


@pytest.fixture()
def dev(app, criar_usuarios):
    """Administrador: Regras e Atribuição são exclusivas dele."""
    c = app.test_client()
    fazer_login(c, "dev", criar_usuarios)
    return c


@pytest.fixture()
def ana(app, criar_usuarios):
    c = app.test_client()
    fazer_login(c, "ana.hmb", criar_usuarios)
    return c


def _massa(fake):
    fake.os_periodo = [
        os_neovero(1, "2026-10-10", situacao=3, responsavel="CLIMA UM", responsavel_id=2, equip_id=1),
        os_neovero(2, "2026-10-10", situacao=1, responsavel="CLIMA UM", responsavel_id=2, equip_id=2),
        os_neovero(3, "2026-10-12", situacao=2, responsavel="CLIMA UM", responsavel_id=2, equip_id=3),
        os_neovero(4, "2026-10-14", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31, equip_id=4,
                   plano="PM - MENSAL - QUADROS ELÉTRICOS", oficina="ELÉTRICA/QGBT"),
        os_neovero(5, "2026-10-14", situacao=3, responsavel="CLIMA UM", responsavel_id=2, equip_id=5),
    ]
    fake.os_abertas = [o for o in fake.os_periodo if o["situacao"] in (1, 2)] + [
        os_neovero(9, "2026-09-20", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31, equip_id=9)]
    fake.planos = [plano_neovero(7, "PM - ANUAL - X", periodicidade=1, unidade="A")]
    fake.itens = {7: [item_plano(70, "2026-10-20", equip_id=77)]}


def _get(c, **q):
    q = {"data_ini": "2026-10-01", "data_fim": "2026-10-31", **q}
    return c.get(f"{P}/preventivas", query_string=q)


# ── listagem / filtros / paginação / totais ───────────────────────────────────

def test_preventivas_exige_periodo_valido(ana, neovero):
    assert ana.get(f"{P}/preventivas").status_code == 400
    assert _get(ana, data_ini="2026-13-45").status_code == 400
    assert _get(ana, data_ini="2026-10-20", data_fim="2026-10-01").status_code == 400
    assert _get(ana, data_ini="2024-01-01", data_fim="2026-10-01").status_code == 400   # > 366 dias


def test_listagem_traz_reais_e_projecoes_com_status_e_atraso(ana, neovero):
    _massa(neovero)
    d = _get(ana).get_json()
    por_os = {i["os_vinculada"]: i for i in d["itens"] if i["origem"] == "OS"}
    assert por_os["1"]["status"] == "Concluída" and por_os["2"]["atrasada"] is True and por_os["3"]["status"] == "Em andamento"
    assert por_os["4"]["responsavel_status"] == "Gestão" and por_os["4"]["recomendado"] != "William de Souza Lobo"
    assert any(i["origem"] == "Plano" and i["status"] == "Aguardando geração" for i in d["itens"])
    assert d["periodo"]["hoje"] == "2026-10-14"
    assert d["totais"]["total"] == d["total"] == len(d["itens"])


def test_os_em_nome_do_gestor_aparece_para_revisao_com_executante_do_quadro(ana, neovero):
    _massa(neovero)
    d = _get(ana, revisao="1").get_json()
    nums = {i["os_vinculada"]: i for i in d["itens"]}
    assert "4" in nums and nums["4"]["responsavel_status"] == "Gestão"
    assert nums["4"]["recomendado"] in ("Iranildo Silva dos Santos", "Michael de Campos Eguez",
                                        "Michael Kelvin de Abreu Moraes", "Diego Reimberg", None)
    assert nums["4"]["recomendado"] != "William de Souza Lobo"
    # a OS 9 (de setembro, ainda aberta, em nome do gestor) entra por 'incluir_atrasadas'
    assert "9" in nums and nums["9"]["atrasada"] is True


def test_incluir_atrasadas_pode_ser_desligado(ana, neovero):
    _massa(neovero)
    com = {i["os_vinculada"] for i in _get(ana, data_ini="2026-10-14", data_fim="2026-10-14").get_json()["itens"]}
    sem = {i["os_vinculada"] for i in _get(ana, data_ini="2026-10-14", data_fim="2026-10-14", incluir_atrasadas="0").get_json()["itens"]}
    assert "9" in com and "9" not in sem


def test_filtros_por_dia_status_e_atraso_na_api(ana, neovero):
    _massa(neovero)
    assert {i["os_vinculada"] for i in _get(ana, dias="2026-10-10").get_json()["itens"]} >= {"1", "2"}
    d = _get(ana, dias="2026-10-10,2026-10-14", status="Concluída").get_json()
    assert {i["os_vinculada"] for i in d["itens"]} == {"1", "5"}
    atrasadas = _get(ana, atrasada="1").get_json()
    assert atrasadas["em_atraso"] == atrasadas["total"] == len(atrasadas["itens"]) >= 3
    assert all(i["atrasada"] for i in atrasadas["itens"])
    d = _get(ana, f_ini="2026-10-12", f_fim="2026-10-14", origem="OS", incluir_atrasadas="0").get_json()
    assert {i["os_vinculada"] for i in d["itens"]} == {"3", "4", "5"}


def test_paginacao_da_api_e_totais_do_periodo_independentes_do_filtro(ana, neovero):
    _massa(neovero)
    tudo = _get(ana, page_size=500).get_json()
    n = tudo["total"]
    p1 = _get(ana, page_size=2, page=1).get_json()
    p2 = _get(ana, page_size=2, page=2).get_json()
    assert p1["total"] == p2["total"] == n and len(p1["itens"]) == 2
    assert not {i["id"] for i in p1["itens"]} & {i["id"] for i in p2["itens"]}
    filtrado = _get(ana, status="Concluída").get_json()
    assert filtrado["totais"]["total"] == 2
    assert filtrado["totais_periodo"]["total"] == n   # contexto: o que existe no período sem o filtro


def test_exportacao_e_consistente_com_a_listagem_filtrada(ana, neovero):
    _massa(neovero)
    filtros = {"status": "Pendente,Em andamento", "atrasada": "1"}
    lista = _get(ana, page_size=500, **filtros).get_json()
    r = ana.get(f"{P}/exportar_preventivas", query_string={"data_ini": "2026-10-01", "data_fim": "2026-10-31", **filtros})
    assert r.status_code == 200 and "spreadsheetml" in r.mimetype
    linhas = list(load_workbook(io.BytesIO(r.data)).active.iter_rows(min_row=3, values_only=True))
    linhas = [l for l in linhas if any(l)]
    assert len(linhas) == lista["total"]
    assert {str(l[10]) for l in linhas} == {i["os_vinculada"] for i in lista["itens"]}
    assert all(l[3] in ("Pendente", "Em andamento") and l[4] == "Sim" for l in linhas)


def test_exportacao_ignora_linhas_enviadas_pelo_cliente(ana, neovero):
    _massa(neovero)
    r = ana.post(f"{P}/exportar_preventivas?data_ini=2026-10-14&data_fim=2026-10-14&incluir_atrasadas=0",
                 json={"itens": [{"plano": "LINHA FORJADA PELO CLIENTE"}]})
    assert r.status_code == 200
    celulas = " ".join(str(c) for row in load_workbook(io.BytesIO(r.data)).active.iter_rows(values_only=True) for c in row)
    assert "FORJADA" not in celulas


def test_dados_geracao_nao_mutam_o_cache_da_base(ana, neovero):
    """A carga/histórico em cache não pode acumular a cada geração (bug antigo: o dict em cache era mutado)."""
    _massa(neovero)
    _get(ana)
    base = next(v for k, v in cache._store.items() if k.startswith("hmb_base_"))["val"]
    antes = dict(base["carga"])
    cache.delete_prefix("hmb_prev_")
    _get(ana)
    assert dict(base["carga"]) == antes


# ── falhas do Neovero ─────────────────────────────────────────────────────────

def test_neovero_sem_configuracao_responde_503_claro_sem_vazar_detalhes(ana, neovero):
    neovero.excecao = NeoveroConfigError("Integração Neovero não configurada: defina NEOVERO_USERNAME e NEOVERO_PASSWORD")
    r = _get(ana)
    assert r.status_code == 503 and r.get_json()["codigo"] == "neovero_nao_configurado"


@pytest.mark.parametrize("exc", [NeoveroIndisponivelError("Neovero indisponível (Timeout) em /x"),
                                 requests.ConnectionError("conexao recusada http://interno:8080")])
def test_neovero_fora_do_ar_responde_502_sem_corromper_nada(ana, neovero, exc):
    neovero.excecao = exc
    r = _get(ana)
    assert r.status_code == 502 and r.get_json()["codigo"] == "neovero_indisponivel"
    assert "interno" not in r.get_data(as_text=True)
    assert not [k for k in cache._store if k.startswith("hmb_prev_")]   # nada de resultado parcial em cache
    neovero.excecao = None
    _massa(neovero)
    assert _get(ana).status_code == 200                                    # recupera na tentativa seguinte


def test_erro_inesperado_responde_500_generico_sem_stack_trace(ana, neovero, monkeypatch):
    from core import unit_blueprint as ub
    monkeypatch.setattr(ub, "paginar", lambda *a, **k: (_ for _ in ()).throw(ValueError("segredo-interno-123")))
    r = _get(ana)
    assert r.status_code == 500 and "segredo-interno-123" not in r.get_data(as_text=True)


# ── revisão de responsáveis ───────────────────────────────────────────────────

def test_revisao_lista_os_abertas_em_nome_de_gestao_desligado_ou_generico(ana, neovero):
    neovero.os_abertas = [
        os_neovero(21, "2026-10-14", responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31),
        os_neovero(22, "2026-10-14", responsavel="CAIO CEZAR SANTOS PEREIRA", responsavel_id=9, equip_id=11),
        os_neovero(23, "2026-10-14", responsavel="ELÉTRICA - DIURNO", responsavel_id=67, equip_id=12),
        os_neovero(24, "2026-10-14", responsavel="CLIMA UM", responsavel_id=2, equip_id=13),   # válido: não entra
        os_neovero(25, "2026-10-14", responsavel=None, equip_id=14),
    ]
    d = ana.get(f"{P}/revisao").get_json()
    por_os = {i["os_numero"]: i for i in d["itens"]}
    assert set(por_os) == {"21", "22", "23", "25"}
    assert por_os["21"]["responsavel_status"] == "Gestão"
    assert por_os["22"]["responsavel_status"] == "Desligado" and por_os["22"]["data_desligamento"] == "2026-09-18"
    assert por_os["23"]["responsavel_status"] == "Genérico" and por_os["25"]["responsavel_status"] == "Sem responsável"
    assert d["por_status"] == {"Gestão": 1, "Desligado": 1, "Genérico": 1, "Sem responsável": 1}
    # somente leitura: nenhuma chamada de escrita foi feita
    assert all(c[0].endswith("/query") for c in neovero.consultas)


# ── regras nominais (5.4 / 5.5) pela API ──────────────────────────────────────

def test_endpoint_de_regras_mostra_pendencias_e_nao_adivinha(dev, neovero):
    d = dev.get(f"{P}/regras").get_json()
    regras = {r["id"]: r for r in d["regras"]}
    ronda = {(l["turno"], l["paridade"]): l for l in regras["ronda_diaria"]["linhas"]}
    assert ronda[("Diurno", "Ímpar")]["status"] == "ok"            # Iranildo inequívoco
    assert ronda[("Diurno", "Par")]["status"] == "pendente"          # Michael: 2 pessoas
    assert ronda[("Diurno", "Par")]["responsaveis"][0]["status"] == "ambiguo"
    assert len(ronda[("Diurno", "Par")]["responsaveis"][0]["candidatos"]) == 2
    assert ronda[("Noturno", "Par")]["responsaveis"][0]["status"] == "nao_encontrado"


def test_confirmar_nome_da_regra_valida_alias_e_colaborador_e_vale_na_proxima_geracao(dev, neovero):
    neovero.os_periodo = [os_neovero(31, "2026-10-14", situacao=1, responsavel="ELÉTRICA - DIURNO", responsavel_id=67,
                                     plano="PM - DIÁRIO - RONDA – NOBREAK", oficina="ELÉTRICA/QGBT", tipo="RONDA",
                                     tipo_id=8, periodicidade=1, unidade_tempo="D")]
    antes = _get(dev, data_ini="2026-10-14", data_fim="2026-10-14").get_json()
    oc = antes["itens"][0]
    assert oc["recomendado"] is None and oc["regra"]["status"] == "pendente"
    assert antes["pendencias_regras"]

    assert dev.put(f"{P}/regras/resolucoes", json={"alias": "Fulano", "funcionario": "Michael de Campos Eguez"}).status_code == 400
    assert dev.put(f"{P}/regras/resolucoes", json={"alias": "Michael", "funcionario": "Caio Cezar Santos Pereira"}).status_code == 400
    # gestão não executa OS / nome que não combina com o apelido: rejeitados; pessoa certa do quadro: aceita
    assert dev.put(f"{P}/regras/resolucoes", json={"alias": "Michael", "funcionario": "William de Souza Lobo"}).status_code == 400
    assert dev.put(f"{P}/regras/resolucoes", json={"alias": "Michael", "funcionario": "Diego Reimberg"}).status_code == 400
    assert dev.put(f"{P}/regras/resolucoes", json={"alias": "Michael", "funcionario": "Michael de Campos Eguez"}).status_code == 200
    depois = _get(dev, data_ini="2026-10-14", data_fim="2026-10-14").get_json()["itens"][0]
    assert depois["recomendado"] == "Michael de Campos Eguez" and depois["regra"]["status"] == "aplicada"
    assert dev.delete(f"{P}/regras/resolucoes", query_string={"alias": "Michael"}).get_json()["removidas"] == 1
    again = _get(dev, data_ini="2026-10-14", data_fim="2026-10-14").get_json()["itens"][0]
    assert again["recomendado"] is None


# ── mutações de colaborador ───────────────────────────────────────────────────

def test_mutacao_em_colaborador_inexistente_e_rejeitada_e_nao_cria_lixo_no_overlay(ana, neovero):
    from core import colaboradores_overlay as ov
    from units.brasilandia import config as cfg
    antes = ov.carregar(cfg.OVERLAY)
    assert ana.patch(f"{P}/colaborador/Digitado%20Errado/status", json={"status": "Desligado"}).status_code == 400
    assert ana.patch(f"{P}/colaborador/Digitado%20Errado/vinculo", json={"data_desligamento": "2026-10-20"}).status_code == 400
    assert ov.carregar(cfg.OVERLAY) == antes


def test_desligar_pela_api_invalida_cache_e_deixa_de_recomendar_a_partir_da_data(ana, neovero):
    neovero.os_periodo = [os_neovero(41, "2026-10-14", situacao=1, responsavel="WILLIAN DE SOUZA LOBO",
                                     responsavel_id=31, plano="PM - MENSAL - QUADROS ELÉTRICOS",
                                     oficina="ELÉTRICA/QGBT"),
                          os_neovero(42, "2026-10-16", situacao=1, responsavel="WILLIAN DE SOUZA LOBO",
                                     responsavel_id=31, equip_id=11, plano="PM - MENSAL - QUADROS ELÉTRICOS",
                                     oficina="ELÉTRICA/QGBT")]
    # só 1 eletricista ativo "forte": Iranildo (ímpar) e Diego; vamos desligar todos os eletricistas aptos
    d = _get(ana, data_ini="2026-10-14", data_fim="2026-10-16", incluir_atrasadas="0").get_json()
    antes = {i["os_vinculada"]: i["recomendado"] for i in d["itens"]}
    assert antes["41"] or antes["42"]
    nomes = {n for n in antes.values() if n}
    for n in nomes:
        r = ana.patch(f"{P}/colaborador/{n}/vinculo", json={"data_desligamento": "2026-10-15"})
        assert r.status_code == 200
    d2 = _get(ana, data_ini="2026-10-14", data_fim="2026-10-16", incluir_atrasadas="0").get_json()
    depois = {i["os_vinculada"]: i["recomendado"] for i in d2["itens"]}
    # no dia 14 ainda podem ser recomendados; a partir de 15 nenhum dos desligados aparece
    assert depois["42"] not in nomes


def test_colaboradores_lista_desligados_do_historico_com_data(ana, neovero):
    from units.brasilandia import colaboradores as hmb
    hmb.invalidar_cache()   # lê a planilha real (cópia) + overlay: traz os 3 desligados de set/2026
    d = ana.get(f"{P}/colaboradores").get_json()
    desligados = {i["funcionario"]: i for i in d["itens"] if i["status"] == "Desligado"}
    assert desligados["Ronaldo Manoel dos Santos"]["data_desligamento"] == "2026-09-08"
    assert desligados["Caio Cezar Santos Pereira"]["data_desligamento"] == "2026-09-18"
    assert desligados["Lesle Venini Izidoro dos Santos"]["data_desligamento"] == "2026-09-26"
    assert all(i["executa_os"] is not None for i in d["itens"])
    supervisor = next(i for i in d["itens"] if i["funcionario"] == "William de Souza Lobo")
    assert supervisor["executa_os"] is False


def test_alteracao_feita_em_outro_worker_invalida_o_cache_de_preventivas(ana, neovero):
    """O overlay vive no banco (compartilhado): se OUTRO processo grava um desligamento, este processo
    não pode continuar servindo recomendações em cache por até 5 minutos — a chave de cache inclui a
    versão do overlay, então a próxima requisição gera um resultado novo."""
    from core import cache
    from core import colaboradores_overlay as ov
    from units.brasilandia import config as cfg
    neovero.os_periodo = [os_neovero(61, "2026-10-20", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31,
                                     plano="PM - MENSAL - QUADROS ELÉTRICOS", oficina="ELÉTRICA/QGBT")]
    chaves = lambda: {k for k in cache._store if k.startswith("hmb_prev_")}   # noqa: E731
    _get(ana, data_ini="2026-10-20", data_fim="2026-10-20", incluir_atrasadas="0")
    _get(ana, data_ini="2026-10-20", data_fim="2026-10-20", incluir_atrasadas="0")
    assert len(chaves()) == 1                         # 2ª chamada reaproveitou o cache
    # "outro worker" grava direto no banco, sem passar por esta aplicação nem invalidar o cache local
    ov.set_data_desligamento(cfg.OVERLAY, "Qualquer Pessoa", "2026-10-19", por="outro-worker")
    _get(ana, data_ini="2026-10-20", data_fim="2026-10-20", incluir_atrasadas="0")
    assert len(chaves()) == 2                         # versão nova => resultado novo (o antigo expira sozinho)
