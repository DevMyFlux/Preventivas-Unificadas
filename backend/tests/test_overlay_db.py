"""Overlay de colaboradores no BANCO: semente única, durabilidade, isolamento por unidade e fallback."""
import json

from sqlalchemy import select

from core import colaboradores_overlay as ov
from core.db import sessao
from core.models import ColaboradorOverlay
from core.overlay_store import DbStore, JsonStore
from tests.conftest import fazer_login
from units.brasilandia import config as cfg_hmb

SEMENTE_HMB = cfg_hmb.DATA_DIR


def test_primeira_leitura_semeia_do_json_versionado_uma_unica_vez(app):
    store = DbStore("HMB", SEMENTE_HMB)
    dados = store.load()
    assert dados["RONALDO MANOEL DOS SANTOS"]["data_desligamento"] == "2026-09-08"
    assert dados["CAIO CEZAR SANTOS PEREIRA"]["data_desligamento"] == "2026-09-18"
    assert dados["LESLE VENINI IZIDORO DOS SANTOS"]["data_desligamento"] == "2026-09-26"
    with sessao() as s:
        linhas = s.scalars(select(ColaboradorOverlay).where(ColaboradorOverlay.unit == "HMB")).all()
        assert sum(1 for l in linhas if l.chave == "__seed__") == 1
    store.load()
    store.load()   # releituras não duplicam a semente
    with sessao() as s:
        assert len(s.scalars(select(ColaboradorOverlay).where(ColaboradorOverlay.unit == "HMB")).all()) == len(linhas)


def test_edicoes_persistem_no_banco_e_a_semente_nao_sobrescreve_depois(app):
    store = DbStore("HMB", SEMENTE_HMB)
    ov.set_data_desligamento(store, "Fulano de Tal", "2026-10-20", por="ana.hmb")
    ov.set_data_desligamento(store, "Ronaldo Manoel dos Santos", None, por="ana.hmb")   # remove a data da semente
    ov.adicionar_habilidade(store, "Fulano de Tal", "tec_eletrica", por="ana.hmb")
    novo = DbStore("HMB", SEMENTE_HMB)   # "outro worker": instância nova lendo o mesmo banco
    dados = novo.load()
    assert dados["FULANO DE TAL"]["data_desligamento"] == "2026-10-20"
    assert dados["FULANO DE TAL"]["habilidades"] == ["tec_eletrica"]
    assert "data_desligamento" not in dados["RONALDO MANOEL DOS SANTOS"]    # a semente NÃO ressuscita a data
    with sessao() as s:
        linha = s.scalar(select(ColaboradorOverlay).where(ColaboradorOverlay.chave == "FULANO DE TAL"))
        assert linha.updated_by == "ana.hmb"


def test_atualizacoes_de_colaboradores_diferentes_nao_se_sobrescrevem(app):
    a, b = DbStore("HMB", SEMENTE_HMB), DbStore("HMB", SEMENTE_HMB)
    ov.set_bloqueado(a, "Pessoa A", True, "motivo A")
    ov.set_bloqueado(b, "Pessoa B", True, "motivo B")      # "outro worker" gravando em seguida
    dados = a.load()
    assert dados["PESSOA A"]["aviso"] == "motivo A" and dados["PESSOA B"]["aviso"] == "motivo B"


def test_unidades_sao_isoladas_no_banco(app):
    hmb, hetrin = DbStore("HMB", None), DbStore("HETRIN", None)
    ov.set_status(hmb, "Mesmo Nome", "Desligado")
    assert "MESMO NOME" in hmb.load() and "MESMO NOME" not in hetrin.load()


def test_version_muda_a_cada_gravacao(app):
    store = DbStore("HMB", None)
    v0 = store.version()
    ov.set_status(store, "Alguem", "Desligado")
    v1 = store.version()
    assert v1 != v0
    assert JsonStore(SEMENTE_HMB).version() != "0"


def test_banco_indisponivel_nao_torna_desligados_elegiveis_usa_a_semente(app, monkeypatch):
    import core.overlay_store as mod

    monkeypatch.setattr(mod, "sessao", lambda: (_ for _ in ()).throw(RuntimeError("banco fora do ar")))
    dados = DbStore("HMB", SEMENTE_HMB).load()
    assert dados["CAIO CEZAR SANTOS PEREIRA"]["data_desligamento"] == "2026-09-18"
    assert DbStore("HMB", SEMENTE_HMB).version() == "indisponivel"


def test_json_store_continua_funcionando_para_pasta(tmp_path):
    ov.set_status(str(tmp_path), "Fulano", "Desligado")
    assert json.loads((tmp_path / "colaboradores_overlay.json").read_text(encoding="utf-8"))["FULANO"]["status"] == "Desligado"


def test_mutacao_pela_api_grava_no_banco_e_nao_no_arquivo(app, criar_usuarios, monkeypatch):
    """O PATCH de desligamento vai para o banco: sobrevive a reinício/deploy; o JSON do repositório fica intacto."""
    import time
    from tests.fakes import colaboradores_df
    from units.brasilandia import colaboradores as hmb
    caminho = f"{cfg_hmb.DATA_DIR}/colaboradores_overlay.json"
    with open(caminho, encoding="utf-8") as f:
        arquivo = json.load(f)
    hmb._colab_cache["df"] = colaboradores_df([{"funcionario": "Eletricista Teste", "cargo": "Eletricista"}])
    hmb._colab_cache["ts"] = time.time()
    c = app.test_client()
    fazer_login(c, "ana.hmb", criar_usuarios)
    r = c.patch("/api/brasilandia/colaborador/Eletricista%20Teste/vinculo", json={"data_desligamento": "2026-10-25"})
    assert r.status_code == 200
    assert cfg_hmb.OVERLAY.load()["ELETRICISTA TESTE"]["data_desligamento"] == "2026-10-25"
    with open(caminho, encoding="utf-8") as f:
        assert json.load(f) == arquivo   # arquivo versionado intocado
    hmb.invalidar_cache()
