"""
Isolamento por unidade e proteção das rotas: o backend decide pelo prefixo da rota ↔ unidade do
cadastro do usuário; nada vindo do cliente (query, corpo, header, URL alterada) escolhe a unidade.
"""
import time

import pytest

from tests.conftest import fazer_login
from tests.fakes import colaboradores_df

ROTAS_UNIDADE_GET = ["/colaboradores", "/planos", "/habilidades", "/regras", "/revisao",
                     "/preventivas?data_ini=2026-10-14&data_fim=2026-10-14", "/atribuicoes?data_ini=2026-10-14&data_fim=2026-10-14"]
PREFIXO = {"HMB": "/api/brasilandia", "HETRIN": "/api/grandmassif"}


@pytest.fixture()
def neovero_falso(monkeypatch):
    """Substitui toda a E/S do Neovero e pré-carrega o cadastro de colaboradores de cada unidade.
    Guarda o payload de cada consulta para provar de qual empresa ela veio."""
    from core import unit_blueprint as ub
    from units.brasilandia import colaboradores as hmb
    from units.grand_massif import colaboradores as gm

    consultas = []

    def paginar_falso(headers, payload, endpoint):
        consultas.append((endpoint, payload))
        return []

    monkeypatch.setattr(ub, "get_headers", lambda: {})
    monkeypatch.setattr(ub, "paginar", paginar_falso)
    monkeypatch.setattr(ub, "buscar_itens_varios_planos", lambda h, p: {})
    for mod, nome in ((hmb, "Eletricista HMB"), (gm, "Eletricista HETRIN")):
        mod._colab_cache["df"] = colaboradores_df([{"funcionario": nome, "cargo": "Eletricista"}])
        mod._colab_cache["ts"] = time.time()
    yield consultas
    for mod in (hmb, gm):
        mod.invalidar_cache()


def _empresas(consultas):
    ids = set()
    for _, payload in consultas:
        for grupo in payload.get("filterGroups", []):
            for f in grupo["filters"]:
                if f["property"] in ("empresa.id", "empresaId"):
                    ids.update(f["value"] if isinstance(f["value"], list) else [f["value"]])
    return ids


# ── default-deny ──────────────────────────────────────────────────────────────

def test_toda_rota_api_exige_login_exceto_login_e_health(app, client):
    publicas = {"/api/auth/login", "/api/health"}
    verificadas = 0
    for regra in app.url_map.iter_rules():
        if not regra.rule.startswith("/api/") or regra.rule in publicas:
            continue
        caminho = regra.rule
        for var in ("<path:nome_colab>", "<nome_colab>"):
            caminho = caminho.replace(var, "Fulano")
        caminho = caminho.replace("<habilidade_id>", "x").replace("<int:user_id>", "1")
        for metodo in sorted(regra.methods - {"HEAD", "OPTIONS"}):
            r = client.open(caminho, method=metodo, json={} if metodo != "GET" else None)
            assert r.status_code == 401, f"{metodo} {caminho} respondeu {r.status_code} sem login"
            verificadas += 1
    assert verificadas > 25


def test_rotas_publicas_sao_somente_login_e_health(client):
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/auth/login", json={}).status_code == 401  # alcançável, mas credenciais inválidas


# ── usuário comum só vê a própria unidade ─────────────────────────────────────

@pytest.mark.parametrize("unidade,outra", [("HMB", "HETRIN"), ("HETRIN", "HMB")])
def test_usuario_nao_acessa_nenhuma_rota_da_outra_unidade(client, criar_usuarios, neovero_falso, unidade, outra):
    usuario = "ana.hmb" if unidade == "HMB" else "beto.hetrin"
    fazer_login(client, usuario, criar_usuarios)
    for rota in ROTAS_UNIDADE_GET:
        propria = client.get(PREFIXO[unidade] + rota).status_code
        # Regras e Atribuição são só do administrador: usuário comum recebe 403 até na própria unidade
        assert propria == (403 if rota.split("?")[0] in ("/regras", "/atribuicoes") else 200), f"{rota} na própria unidade: {propria}"
        r = client.get(PREFIXO[outra] + rota)
        assert r.status_code == 403, f"{rota} da outra unidade respondeu {r.status_code}"
    # nenhuma consulta ao Neovero foi feita em nome da outra empresa
    empresa_propria = 2 if unidade == "HMB" else 3
    assert _empresas(neovero_falso) <= {empresa_propria}


def test_escrita_na_outra_unidade_tambem_e_barrada(client, criar_usuarios, neovero_falso):
    fazer_login(client, "ana.hmb", criar_usuarios)
    base = "/api/grandmassif/colaborador/Eletricista%20HETRIN"
    assert client.patch(base + "/status", json={"status": "Desligado"}).status_code == 403
    assert client.patch(base + "/bloqueio", json={"bloqueado": True}).status_code == 403
    assert client.patch(base + "/vinculo", json={"data_desligamento": "2026-10-20"}).status_code == 403
    assert client.post(base + "/habilidades", json={"habilidade_id": "tec_eletrica"}).status_code == 403
    assert client.post("/api/grandmassif/limpar_cache").status_code == 403
    assert client.post("/api/grandmassif/atribuicoes/decisao", json={"ids": [1], "acao": "aprovar"}).status_code == 403
    assert client.put("/api/grandmassif/regras/resolucoes", json={"alias": "x", "funcionario": "y"}).status_code == 403


@pytest.mark.parametrize("adulteracao", [
    {"params": {"unit": "HETRIN"}},
    {"params": {"unidade": "grandmassif", "empresa_id": "3", "empresaId": "3"}},
    {"headers": {"X-Unit": "HETRIN", "X-Empresa-Id": "3"}},
])
def test_parametros_e_headers_do_cliente_nao_mudam_a_unidade(client, criar_usuarios, neovero_falso, adulteracao):
    fazer_login(client, "ana.hmb", criar_usuarios)
    params = {"data_ini": "2026-10-14", "data_fim": "2026-10-14", **adulteracao.get("params", {})}
    r = client.get("/api/brasilandia/preventivas", query_string=params, headers=adulteracao.get("headers"))
    assert r.status_code == 200
    assert _empresas(neovero_falso) == {2}   # sempre a empresa da HMB


@pytest.mark.parametrize("caminho", [
    "/api//grandmassif/colaboradores",
    "/api/brasilandia/../grandmassif/colaboradores",
    "/api/%67randmassif/colaboradores",
    "/api/GRANDMASSIF/colaboradores",
    "/api/grandmassif/colaboradores/",
    "/api/grandmassif%2Fcolaboradores",
])
def test_truques_de_url_nao_furam_o_isolamento(client, criar_usuarios, neovero_falso, caminho):
    fazer_login(client, "ana.hmb", criar_usuarios)
    r = client.get(caminho, follow_redirects=True)
    assert r.status_code in (403, 404), f"{caminho} -> {r.status_code}"
    assert "Eletricista HETRIN" not in r.get_data(as_text=True)


def test_dev_acessa_todas_as_unidades(client, criar_usuarios, neovero_falso):
    fazer_login(client, "dev", criar_usuarios)
    for u in ("HMB", "HETRIN"):
        for rota in ROTAS_UNIDADE_GET:
            assert client.get(PREFIXO[u] + rota).status_code == 200


def test_unidade_do_usuario_vem_do_cadastro_nao_do_login(client, criar_usuarios):
    r = client.post("/api/auth/login", json={"username": "ana.hmb", "password": criar_usuarios, "unit": "HETRIN",
                                             "role": "dev"})
    assert r.status_code == 200
    u = r.get_json()["user"]
    assert u["unit"] == "HMB" and u["is_dev"] is False


def test_mudar_o_vinculo_do_usuario_derruba_as_sessoes_abertas(client, app, criar_usuarios, neovero_falso):
    ana = app.test_client()
    fazer_login(ana, "ana.hmb", criar_usuarios)
    assert ana.get("/api/brasilandia/colaboradores").status_code == 200
    dev = client
    fazer_login(dev, "dev", criar_usuarios)
    from core.auth.servico import obter_usuario_por_username
    uid = obter_usuario_por_username("ana.hmb").id
    assert dev.patch(f"/api/admin/users/{uid}", json={"unit": "HETRIN"}).status_code == 200
    assert ana.get("/api/brasilandia/colaboradores").status_code == 401   # sessão antiga encerrada
    novo = app.test_client()
    fazer_login(novo, "ana.hmb", criar_usuarios)
    assert novo.get("/api/brasilandia/colaboradores").status_code == 403
    assert novo.get("/api/grandmassif/colaboradores").status_code == 200


def test_usuario_desativado_perde_o_acesso_imediatamente(client, app, criar_usuarios, neovero_falso):
    ana = app.test_client()
    fazer_login(ana, "ana.hmb", criar_usuarios)
    assert ana.get("/api/brasilandia/colaboradores").status_code == 200
    fazer_login(client, "dev", criar_usuarios)
    from core.auth.servico import obter_usuario_por_username
    uid = obter_usuario_por_username("ana.hmb").id
    assert client.post(f"/api/admin/users/{uid}/active", json={"active": False}).status_code == 200
    assert ana.get("/api/brasilandia/colaboradores").status_code == 401
    assert app.test_client().post("/api/auth/login", json={"username": "ana.hmb", "password": criar_usuarios}).status_code == 401


def test_exportacao_e_cache_respeitam_o_escopo_da_unidade(client, criar_usuarios, neovero_falso):
    """O cache de uma unidade nunca é servido a outra: chaves têm prefixo de unidade e as rotas são barradas."""
    dev = client
    fazer_login(dev, "dev", criar_usuarios)
    assert dev.get("/api/grandmassif/preventivas?data_ini=2026-10-14&data_fim=2026-10-14").status_code == 200
    from core import cache
    chaves = [k for k in cache._store]
    assert chaves and all(k.startswith(("hetrin_", "hmb_")) for k in chaves)
    ana = client.application.test_client()
    fazer_login(ana, "ana.hmb", criar_usuarios)
    assert ana.get("/api/grandmassif/exportar_preventivas?data_ini=2026-10-14&data_fim=2026-10-14").status_code == 403
    assert ana.post("/api/grandmassif/exportar_planos", json={"itens": [{"id": 1}]}).status_code == 403


@pytest.mark.parametrize("usuario,prefixo", [("ana.hmb", "/api/brasilandia"), ("beto.hetrin", "/api/grandmassif")])
def test_regras_e_atribuicao_so_para_o_administrador_mesmo_na_propria_unidade(client, criar_usuarios, neovero_falso, usuario, prefixo):
    fazer_login(client, usuario, criar_usuarios)
    for metodo, rota, corpo in [("get", "/regras", None), ("put", "/regras/resolucoes", {"alias": "x", "funcionario": "y"}),
                                ("delete", "/regras/resolucoes", None), ("get", "/atribuicoes", None),
                                ("post", "/atribuicoes/propostas", {"os_ids": [1]}), ("post", "/atribuicoes/decisao", {"ids": [1], "acao": "aprovar"}),
                                ("post", "/atribuicoes/processar", {"ids": [1], "modo": "simular"}),
                                ("get", "/ATRIBUICOES", None), ("get", "/%72egras", None)]:
        r = getattr(client, metodo)(prefixo + rota, **({"json": corpo} if corpo is not None else {}))
        assert r.status_code == 403, f"{metodo.upper()} {rota} respondeu {r.status_code} para usuário comum"
    # o que o usuário comum PODE: as demais rotas da unidade
    assert client.get(prefixo + "/preventivas", query_string={"data_ini": "2026-10-14", "data_fim": "2026-10-14"}).status_code == 200


def test_administrador_continua_acessando_regras_e_atribuicao(app, criar_usuarios, neovero_falso):
    dev = app.test_client()
    fazer_login(dev, "dev", criar_usuarios)
    assert dev.get("/api/brasilandia/regras").status_code == 200
    assert dev.get("/api/grandmassif/atribuicoes").status_code != 403          # passou pela guarda (400 = faltam datas)
    assert dev.get("/api/grandmassif/regras").status_code == 200
