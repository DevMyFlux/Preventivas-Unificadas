"""
Testes de core/neovero_client.py.

Contexto do fix: a coluna "OS Vinculada"/"Status OS" da aba Preventivas mostrava a
última OS conhecida de um item mesmo quando a ocorrência é uma projeção futura sem
nenhuma OS real ainda — o Neovero não cria a ordem de serviço com antecedência.
Isso confundia usuários (parecia ser a OS daquela data específica). Decisão: só
expor a OS vinculada quando ela está de fato Aberta ou Em Andamento.
"""
from core.neovero_client import os_vinculada_visivel


def test_os_fechada_fica_oculta():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 3}) == ("—", "—")


def test_os_cancelada_fica_oculta():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 4}) == ("—", "—")


def test_os_aberta_e_exibida():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 1}) == ("202508123", "Aberta")


def test_os_em_andamento_e_exibida():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 2}) == ("202508123", "Em Andamento")


def test_sem_os_nenhuma_fica_oculta():
    assert os_vinculada_visivel({}) == ("—", "—")
    assert os_vinculada_visivel(None) == ("—", "—")


def test_situacao_desconhecida_fica_oculta():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 99}) == ("—", "—")


# ── V2: configuração por ambiente e tratamento de falhas ──────────────────────

import pytest
import requests

from core import neovero_client as nc


class _Resp:
    def __init__(self, status=200, corpo=None):
        self.status_code = status
        self._corpo = corpo if corpo is not None else {}

    def json(self):
        return self._corpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=False)
def sem_cache_de_token():
    nc._token_cache.update({"token": None, "expires": 0.0})
    yield
    nc._token_cache.update({"token": None, "expires": 0.0})


def test_sem_credenciais_no_ambiente_o_token_falha_com_mensagem_clara(sem_cache_de_token, monkeypatch):
    monkeypatch.delenv("NEOVERO_USERNAME", raising=False)
    monkeypatch.delenv("NEOVERO_PASSWORD", raising=False)
    with pytest.raises(nc.NeoveroConfigError) as e:
        nc.obter_token()
    assert "NEOVERO_USERNAME" in str(e.value)


def test_token_usa_credenciais_do_ambiente_sem_escapar_manualmente(sem_cache_de_token, monkeypatch):
    monkeypatch.setenv("NEOVERO_USERNAME", "svc@exemplo.com")
    monkeypatch.setenv("NEOVERO_PASSWORD", "p@ss&w=rd%")
    capturado = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        capturado.update(url=url, data=data, headers=headers)
        return _Resp(200, {"access_token": "tok"})

    monkeypatch.setattr(nc.requests, "post", fake_post)
    assert nc.obter_token() == "tok"
    assert capturado["data"] == {"username": "svc@exemplo.com", "password": "p@ss&w=rd%"}   # o requests codifica
    assert nc.obter_token() == "tok"                                                         # segunda vez: cache


def test_falha_de_rede_na_autenticacao_vira_indisponivel_sem_vazar_a_senha(sem_cache_de_token, monkeypatch):
    monkeypatch.setenv("NEOVERO_USERNAME", "svc")
    monkeypatch.setenv("NEOVERO_PASSWORD", "segredo-123")
    monkeypatch.setattr(nc.requests, "post", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("x")))
    with pytest.raises(nc.NeoveroIndisponivelError) as e:
        nc.obter_token()
    assert "segredo-123" not in str(e.value)


def test_requisicao_5xx_esgota_tentativas_e_levanta_indisponivel(monkeypatch):
    chamadas = []
    monkeypatch.setattr(nc.requests, "request", lambda *a, **k: chamadas.append(1) or _Resp(503))
    with pytest.raises(nc.NeoveroIndisponivelError):
        nc._requisitar("GET", "/api/x", {})
    assert len(chamadas) == 2


def test_401_renova_o_token_e_repete_uma_vez(sem_cache_de_token, monkeypatch):
    monkeypatch.setenv("NEOVERO_USERNAME", "svc")
    monkeypatch.setenv("NEOVERO_PASSWORD", "x")
    tokens = iter(["novo-token"])
    monkeypatch.setattr(nc.requests, "post", lambda *a, **k: _Resp(200, {"access_token": next(tokens)}))
    respostas = iter([_Resp(401), _Resp(200, {"ok": True})])
    vistos = []

    def fake_request(metodo, url, headers=None, json=None, timeout=None):
        vistos.append(headers.get("authorization"))
        return next(respostas)

    monkeypatch.setattr(nc.requests, "request", fake_request)
    nc._token_cache.update({"token": "velho", "expires": 9e12})
    r = nc._requisitar("GET", "/api/x", {"authorization": "Bearer velho"})
    assert r.status_code == 200 and vistos == ["Bearer velho", "Bearer novo-token"]


def test_paginar_nao_devolve_resultado_parcial_quando_uma_pagina_falha(monkeypatch):
    respostas = iter([_Resp(200, {"records": [{"i": n} for n in range(100)]}), _Resp(500), _Resp(500)])
    monkeypatch.setattr(nc.requests, "request", lambda *a, **k: next(respostas))
    with pytest.raises(nc.NeoveroIndisponivelError):
        nc.paginar({}, {"limit": 100}, "/api/ordensservico/query")


def test_paginar_percorre_todas_as_paginas(monkeypatch):
    paginas = iter([_Resp(200, {"records": list(range(100))}), _Resp(200, {"records": list(range(100, 130))})])
    monkeypatch.setattr(nc.requests, "request", lambda *a, **k: next(paginas))
    assert nc.paginar({}, {"limit": 100}, "/x") == list(range(130))


def test_buscar_itens_de_plano_inexistente_devolve_vazio_mas_erro_de_servidor_propaga(monkeypatch):
    monkeypatch.setattr(nc.requests, "request", lambda *a, **k: _Resp(404))
    assert nc.buscar_itens_plano({}, 1) == []
    monkeypatch.setattr(nc.requests, "request", lambda *a, **k: _Resp(502))
    with pytest.raises(nc.NeoveroIndisponivelError):
        nc.buscar_itens_plano({}, 1)


def test_paginar_busca_as_paginas_restantes_em_paralelo_usando_totalcount(monkeypatch):
    import threading
    visto = {"threads": set(), "offsets": []}

    def fake_request(metodo, url, headers=None, json=None, timeout=None):
        off = json["offset"]
        visto["offsets"].append(off)
        visto["threads"].add(threading.get_ident())
        qtd = min(100, 250 - off)
        return _Resp(200, {"totalCount": 250, "records": [{"id": off + i} for i in range(qtd)]})

    monkeypatch.setattr(nc.requests, "request", fake_request)
    regs = nc.paginar({}, {"limit": 100}, "/x")
    assert [r["id"] for r in regs] == list(range(250))
    assert sorted(visto["offsets"]) == [0, 100, 200]


def test_paginar_descarta_registros_duplicados_entre_paginas(monkeypatch):
    def fake_request(metodo, url, headers=None, json=None, timeout=None):
        off = json["offset"]
        # a página 2 repete o último registro da 1ª (inclusão concorrente deslocou a janela)
        base = 0 if off == 0 else 99
        return _Resp(200, {"totalCount": 150, "records": [{"id": base + i} for i in range(100 if off == 0 else 51)]})

    monkeypatch.setattr(nc.requests, "request", fake_request)
    ids = [r["id"] for r in nc.paginar({}, {"limit": 100}, "/x")]
    assert len(ids) == len(set(ids)) == 150
