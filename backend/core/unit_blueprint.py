"""
Fábrica do blueprint de uma unidade (HETRIN, HMB…).

As duas unidades tinham ~700 e ~460 linhas de rotas quase idênticas; qualquer correção
precisava ser feita (e testada) duas vezes. Aqui fica UMA implementação parametrizada pelo
que realmente difere entre as unidades: configuração (`cfg`), carregador de colaboradores,
função de disponibilidade/recomendação (`indicar_responsavel`), regras nominais e a escala
nomeada soft (HETRIN). O escopo de acesso por unidade é imposto ANTES de chegar aqui, pela
guarda global (core.auth.http); este módulo nunca lê a unidade de nenhum parâmetro do cliente
— `cfg.EMPRESA_ID` vem da configuração do blueprint.
"""
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from functools import wraps

import requests
from flask import Blueprint, g, jsonify, request, send_file

from core import cache as _cache
from core.db import agora_utc
from core import colaboradores_overlay, preventivas as prev
from core import atribuicoes, os_historico
from core.exporters import gerar_excel_planos, gerar_excel_preventivas
from core.motor_base import HABILIDADES, HABILIDADES_POR_ID
from core.neovero_client import (
    NeoveroConfigError, NeoveroIndisponivelError, buscar_itens_varios_planos, filtros_planos, get_headers, paginar,
)
from core.regras import atribuicao as regras_mod
from core.regras import resolucoes as regras_db
from core.regras.nomes import normalizar_nome

log = logging.getLogger("myflux.unit")

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_DIAS_PERIODO = 366
CACHE_TTL_INFO = 300


class RequisicaoInvalida(Exception):
    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.mensagem, self.campo = mensagem, campo


def _parse_data(valor: str | None, campo: str) -> date | None:
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise RequisicaoInvalida(f"{campo} inválida — use o formato AAAA-MM-DD.", campo)


def _periodo(obrigatorio: bool = False) -> tuple[date | None, date | None]:
    d_ini, d_fim = _parse_data(request.args.get("data_ini"), "data_ini"), _parse_data(request.args.get("data_fim"), "data_fim")
    if obrigatorio and (not d_ini or not d_fim):
        raise RequisicaoInvalida("Informe data_ini e data_fim.", "data_ini")
    if d_ini and d_fim:
        if d_fim < d_ini:
            raise RequisicaoInvalida("data_fim não pode ser anterior a data_ini.", "data_fim")
        if (d_fim - d_ini).days > MAX_DIAS_PERIODO:
            raise RequisicaoInvalida(f"Período máximo de {MAX_DIAS_PERIODO} dias.", "data_fim")
    return d_ini, d_fim


def _bool_arg(nome: str, padrao: bool | None = None) -> bool | None:
    v = request.args.get(nome)
    if v is None or v == "":
        return padrao
    return v.strip().lower() in ("1", "true", "sim", "yes")


def tratar_erros(fn):
    """Erros previsíveis viram respostas claras; nada de stack trace/mensagem interna ao cliente."""
    @wraps(fn)
    def _w(*a, **kw):
        try:
            return fn(*a, **kw)
        except RequisicaoInvalida as e:
            return jsonify({"erro": e.mensagem, "campo": e.campo, "codigo": "requisicao_invalida"}), 400
        except NeoveroConfigError as e:
            log.error("Neovero não configurado: %s", e)
            return jsonify({"erro": str(e), "codigo": "neovero_nao_configurado"}), 503
        except (NeoveroIndisponivelError, requests.RequestException) as e:
            log.error("Neovero indisponível: %s", e)
            return jsonify({"erro": "Neovero indisponível no momento. Tente novamente em instantes.",
                            "codigo": "neovero_indisponivel"}), 502
        except Exception:
            log.exception("Erro não tratado em %s", request.path)
            return jsonify({"erro": "Erro interno ao processar a requisição.", "codigo": "erro_interno"}), 500
    return _w


def criar_blueprint(*, nome, cfg, codigo_unidade, carregar_colaboradores, invalidar_colaboradores, indicar_responsavel,
                    regras=(), nomes_permitidos_fn=None, regra_cargo_fn=None,
                    plano_automatico_fn=None, nomes_equipe=frozenset()) -> Blueprint:
    bp = Blueprint(nome, __name__, url_prefix=f"/api/{cfg.PREFIXO_API}")
    prefixo_cache = f"{codigo_unidade.lower()}_"
    _travas: dict[str, threading.Lock] = defaultdict(threading.Lock)

    def com_trava(chave: str):
        """Uma única geração por chave de cache por vez: pedidos idênticos simultâneos (duplo clique,
        dois usuários, requisição repetida) esperam o primeiro em vez de repetir ~40 s de consultas."""
        return _travas[chave]

    def ck(chave: str) -> str:
        return prefixo_cache + chave

    def invalidar_tudo() -> None:
        invalidar_colaboradores()
        _cache.delete_prefix(prefixo_cache)

    # ── dados base ────────────────────────────────────────────────────────────
    def os_payload(d_ini=None, d_fim=None):
        filtros = [{"property": "empresa.id", "value": [cfg.EMPRESA_ID]}]
        if d_ini or d_fim:
            filtros.append({"property": "periodoAbertura", "value": {
                "rangeType": "CUSTOM",
                "customStart": d_ini.strftime("%Y-%m-%dT00:00:00") if d_ini else None,
                "customEnd": d_fim.strftime("%Y-%m-%dT23:59:59") if d_fim else None}})
        return {"limit": 100, "sort": [{"field": "dataHoraAbertura", "dir": "desc"}],
                "filterGroups": [{"combineOperator": "AND", "filters": filtros}]}

    def os_abertas_payload():
        return {"limit": 100, "sort": [{"field": "dataHoraAbertura", "dir": "desc"}],
                "filterGroups": [{"combineOperator": "AND", "filters": [
                    {"property": "empresa.id", "value": [cfg.EMPRESA_ID]},
                    {"property": "situacao", "value": [1, 2]}]}]}

    def carregar_abertas(headers, forcar=False):
        """OS Abertas/Em andamento de TODAS as datas (um pedido leve; cache curto)."""
        chave = ck("abertas")
        if not forcar:
            cached = _cache.get(chave)
            if cached is not None:
                return cached
        abertas = paginar(headers, os_abertas_payload(), "/api/ordensservico/query")
        _cache.set(chave, abertas)
        return abertas

    def carregar_base(headers, d_ini, d_fim, forcar=False):
        chave = ck(f"base_{d_ini}_{d_fim}")
        if not forcar:
            cached = _cache.get(chave)
            if cached:
                return cached
        abertas = carregar_abertas(headers, forcar)
        periodo = paginar(headers, os_payload(d_ini, d_fim), "/api/ordensservico/query")
        hist_tipo, hist_ativo, carga = defaultdict(int), defaultdict(int), defaultdict(int)
        for o in periodo:
            if o.get("situacao") != 3:
                continue
            nome_r = ((o.get("responsavel") or {}).get("nome") or "").strip()
            t = ((o.get("tipoManutencao") or {}).get("descricao") or "").strip()
            a = ((o.get("equipamento") or {}).get("nome") or "").strip()
            if nome_r:
                if t:
                    hist_tipo[(nome_r, t)] += 1
                if a:
                    hist_ativo[(nome_r, a)] += 1
        for o in abertas:
            nome_r = ((o.get("responsavel") or {}).get("nome") or "").strip()
            if nome_r:
                carga[nome_r] += 1
        base = {"hist_tipo": hist_tipo, "hist_ativo": hist_ativo, "carga": carga,
                "todas_periodo": periodo, "abertas_hoje": abertas,
                "fechadas_periodo": [o for o in periodo if o.get("situacao") == 3]}
        _cache.set(chave, base)
        return base

    def carregar_planos_e_itens(headers, forcar=False):
        """Planos ativos + itens: não dependem do período consultado, então ficam em cache
        (10 min) e são reaproveitados por qualquer intervalo de datas."""
        chave = ck("planos_itens")
        if not forcar:
            cached = _cache.get(chave)
            if cached:
                return cached
        planos = paginar(headers, {"limit": 100, "orderBy": [{"column": "descricao", "ascending": True}],
                                   "filterGroups": [{"combineOperator": "AND",
                                                     "filters": filtros_planos(cfg.EMPRESA_ID, cfg.OFICINA_ID, ativo=True)}]},
                         "/api/planosmanutencao/query")
        itens = buscar_itens_varios_planos(headers, planos)
        _cache.set(chave, (planos, itens))
        return planos, itens

    def roster():
        colab = carregar_colaboradores()
        if colab is None:
            raise RequisicaoInvalida("Planilha de colaboradores não encontrada.")
        return colab

    def ativos(colab):
        return colab[colab["status"] == "Ativo"]

    def resolvidas(colab):
        conf = regras_db.carregar_confirmacoes(codigo_unidade)
        return regras_mod.resolver_regras(list(regras), ativos(colab), conf)

    def gerar(d_ini, d_fim, incluir_atrasadas=True, forcar=False):
        # A chave inclui a versão do overlay (desligamentos/bloqueios) e das confirmações de regras no
        # BANCO: uma alteração feita em outro worker invalida o cache deste na próxima requisição.
        roster()   # carrega (e, na 1ª vez, semeia) o overlay ANTES de ler a versão — senão a chave mudaria logo após a 1ª geração
        versao = hash((cfg.OVERLAY.version(), regras_db.versao(codigo_unidade)))
        chave = ck(f"prev_{d_ini}_{d_fim}_{int(incluir_atrasadas)}_{versao}")
        if not forcar:
            cached = _cache.get(chave)
            if cached:
                return cached
        with com_trava(chave):
            if not forcar:
                cached = _cache.get(chave)   # outro pedido pode ter terminado enquanto esperávamos
                if cached:
                    return cached
            return _gerar_sem_trava(chave, d_ini, d_fim, incluir_atrasadas, forcar)

    def _gerar_sem_trava(chave, d_ini, d_fim, incluir_atrasadas, forcar):
        h = get_headers()
        colab = roster()
        # OS (período + abertas) e planos/itens são independentes: buscados ao mesmo tempo
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_base = pool.submit(carregar_base, h, d_ini, d_fim, forcar)
            f_planos = pool.submit(carregar_planos_e_itens, h, forcar)
            base, (planos, itens) = f_base.result(), f_planos.result()
        ctx = prev.ContextoGeracao(
            colab_ativos=ativos(colab), colab_todos=colab, indicar=indicar_responsavel,
            regras_resolvidas=resolvidas(colab), nomes_permitidos_fn=nomes_permitidos_fn, regra_cargo_fn=regra_cargo_fn,
            plano_automatico_fn=plano_automatico_fn, nomes_equipe=nomes_equipe,
            # cópias: o cache da base não pode ser mutado pela geração (acumularia a cada chamada)
            hist_tipo=dict(base["hist_tipo"]), hist_ativo=dict(base["hist_ativo"]), carga=dict(base["carga"]),
            hoje=prev.hoje_local())
        ocorrencias = prev.gerar_ocorrencias(ctx, planos, itens, base["todas_periodo"], base["abertas_hoje"],
                                             d_ini, d_fim, incluir_atrasadas)
        resultado = {"itens": ocorrencias, "gerado_em": agora_utc().isoformat() + "Z",
                     "pendencias_regras": pendencias_das_regras(ctx.regras_resolvidas),
                     "base": base}
        _cache.set(chave, resultado)
        _observar_responsaveis(ocorrencias)
        return resultado

    def _observar_responsaveis(ocorrencias):
        """Registra primeira leitura / transferência do responsável das OS reais. Falha aqui nunca derruba a geração."""
        try:
            os_historico.registrar_observacoes(codigo_unidade, [
                {"os_numero": o["os_vinculada"], "os_id": o.get("os_id"), "plano": o["plano"], "responsavel": o["responsavel_atual"]}
                for o in ocorrencias if o["origem"] == "OS"])
        except Exception:   # pragma: no cover - degradação segura
            log.exception("Falha ao registrar histórico de responsável (%s)", codigo_unidade)

    def pendencias_das_regras(res: dict) -> list[dict]:
        saida = []
        for r in res.values():
            for linha in r.linhas.values():
                for x in linha.pendencias:
                    saida.append({"regra": r.regra.titulo, "turno": linha.turno, "paridade": linha.paridade,
                                  "alias": x.alias, "status": x.status, "motivo": x.motivo,
                                  "candidatos": x.candidatos})
        return saida

    def filtros_da_requisicao() -> dict:
        a = request.args
        return {
            "dias": a.get("dias"), "data_ini": a.get("f_ini") or None, "data_fim": a.get("f_fim") or None,
            "status": a.get("status"), "atrasada": True if _bool_arg("atrasada") else None,
            "turno": a.get("turno") or None, "paridade": a.get("paridade") or None,
            "responsavel": a.get("responsavel"), "busca": a.get("busca"),
            "revisao": True if _bool_arg("revisao") else None,
            "sem_candidato": True if _bool_arg("sem_candidato") else None,
            "requer_intervencao": True if _bool_arg("requer_intervencao") else None,
            "origem": a.get("origem") or None, "oficina": a.get("oficina"),
        }

    # ── preventivas ───────────────────────────────────────────────────────────
    @bp.route("/preventivas")
    @tratar_erros
    def api_preventivas():
        d_ini, d_fim = _periodo(obrigatorio=True)
        r = gerar(d_ini, d_fim, _bool_arg("incluir_atrasadas", True), forcar=_bool_arg("refresh", False))
        todos = r["itens"]
        filtrados = prev.filtrar(todos, filtros_da_requisicao())
        pagina = request.args.get("page", 1, type=int)
        por_pagina = request.args.get("page_size", 100, type=int)
        tf = prev.totais(filtrados)
        return jsonify({
            "total": tf["total"], "com_recomendacao": tf["com_recomendacao"], "em_atraso": tf["atrasadas"],
            "pagina": max(1, pagina), "por_pagina": max(1, min(por_pagina, 500)),
            "itens": prev.paginar_lista(filtrados, pagina, por_pagina),
            "totais": tf, "totais_periodo": prev.totais(todos),
            "periodo": {"data_ini": d_ini.isoformat(), "data_fim": d_fim.isoformat(), "hoje": prev.hoje_local().isoformat()},
            "gerado_em": r["gerado_em"], "pendencias_regras": r["pendencias_regras"],
        })

    @bp.route("/exportar_preventivas", methods=["GET", "POST"])
    @tratar_erros
    def api_exportar_preventivas():
        # Exporta o que o SERVIDOR calculou (mesmos filtros da listagem) — não aceita linhas
        # enviadas pelo cliente: o arquivo é sempre consistente com tabela e totais.
        d_ini, d_fim = _periodo(obrigatorio=True)
        r = gerar(d_ini, d_fim, _bool_arg("incluir_atrasadas", True))
        filtrados = prev.filtrar(r["itens"], filtros_da_requisicao())
        g.audit_details = {"linhas": len(filtrados)}
        buf = gerar_excel_preventivas(filtrados, d_ini, d_fim, cfg.NOME)
        sufixo = f"{d_ini.strftime('%Y%m%d')}_{d_fim.strftime('%Y%m%d')}"
        return send_file(buf, as_attachment=True, download_name=f"{codigo_unidade.lower()}_preventivas_{sufixo}.xlsx",
                         mimetype=_XLSX)

    # ── revisão (5.1 / 5.2): OS abertas em nome de gestão, desligados, genéricos… ─
    @bp.route("/revisao")
    @tratar_erros
    def api_revisao():
        """Todas as OS abertas/em andamento (independente da data) cujo responsável NÃO é
        um executante válido, para revisão da supervisão. Nada é reatribuído aqui."""
        h = get_headers()
        colab = roster()
        abertas = carregar_abertas(h)
        ctx = prev.ContextoGeracao(colab_ativos=ativos(colab), colab_todos=colab, indicar=indicar_responsavel,
                                   regra_cargo_fn=regra_cargo_fn, plano_automatico_fn=plano_automatico_fn,
                                   nomes_equipe=nomes_equipe)
        itens = []
        fora_da_regra = []
        for o in abertas:
            oc = prev._ocorrencia_de_os(o, ctx.hoje)
            if not oc:
                continue
            st, cadastro = prev.classificar_responsavel_da_ocorrencia(oc, ctx)
            if st in prev.RESPONSAVEIS_VALIDOS:
                desvio = prev._desvio_de_cargo(oc, cadastro, ctx) if st == prev.RESP_ATRIBUIDA else None
                if desvio:   # executante válido, mas cargo fora do exigido pelo plano (só sinaliza)
                    fora_da_regra.append({
                        "os_numero": oc["os_vinculada"], "data_prev": oc["_dia"].strftime("%d/%m/%Y"), "plano": oc["plano"],
                        "status": oc["status"], "responsavel_atual": oc["responsavel_atual"], "desvio": desvio})
                continue
            desligamento = None
            if cadastro:
                linha = colab[colab["funcionario"] == cadastro].iloc[0]
                desligamento = linha.get("data_desligamento")
            itens.append({
                "os_numero": oc["os_vinculada"], "data_prev": oc["_dia"].strftime("%d/%m/%Y"), "plano": oc["plano"],
                "oficina": oc["oficina"], "situacao": oc["os_situacao"], "status": oc["status"], "atrasada": oc["atrasada"],
                "responsavel_atual": oc["responsavel_atual"], "responsavel_status": st,
                "responsavel_cadastro": cadastro, "data_desligamento": desligamento,
            })
        itens.sort(key=lambda x: (x["responsavel_status"], x["responsavel_atual"] or "", x["data_prev"]))
        try:
            planos_ativos, _ = carregar_planos_e_itens(h)
            planos_invalidos = prev.planos_com_responsavel_invalido(planos_ativos, abertas, ctx)
        except (NeoveroIndisponivelError, requests.RequestException):
            planos_invalidos = None   # a revisão das OS continua útil mesmo sem os planos
        por_status = defaultdict(int)
        por_responsavel = defaultdict(int)
        for it in itens:
            por_status[it["responsavel_status"]] += 1
            por_responsavel[(it["responsavel_status"], it["responsavel_atual"] or "—")] += 1
        return jsonify({
            "total": len(itens), "por_status": dict(por_status),
            "por_responsavel": [{"status": s, "responsavel": r, "ordens": n}
                                for (s, r), n in sorted(por_responsavel.items(), key=lambda x: -x[1])],
            "itens": itens,
            "cargo_fora_da_regra": fora_da_regra,
            "planos_responsavel_invalido": planos_invalidos,
            "nota": "Somente leitura: nenhuma OS é reatribuída automaticamente; o histórico é preservado.",
        })

    # ── histórico de responsável / transferências ─────────────────────────────
    @bp.route("/transferencias")
    @tratar_erros
    def api_transferencias():
        """Transferências de responsável OBSERVADAS pela aplicação (ver core/os_historico.py)."""
        so_transf = request.args.get("todas") not in ("1", "true")
        itens = os_historico.listar(codigo_unidade, os_numero=request.args.get("os"), so_transferencias=so_transf)
        return jsonify({
            "total": len(itens), "itens": itens,
            "nota": "Registra o que a aplicação observou entre leituras do Neovero; mudanças anteriores ao monitoramento "
                    "não são conhecidas. O motivo é anotado por uma pessoa.",
        })

    @bp.route("/transferencias/<int:registro_id>/motivo", methods=["PUT"])
    @tratar_erros
    def api_motivo_transferencia(registro_id: int):
        corpo = request.get_json(silent=True) or {}
        r = os_historico.anotar_motivo(codigo_unidade, registro_id, str(corpo.get("motivo", "")), g.user.username)
        if r is None:
            return jsonify({"erro": "Registro não encontrado nesta unidade."}), 404
        g.audit_details = {"registro": registro_id}
        return jsonify(r)

    # ── planos ────────────────────────────────────────────────────────────────
    @bp.route("/planos")
    @tratar_erros
    def api_planos():
        cached = _cache.get(ck("planos"))
        if cached:
            return jsonify(cached)
        h = get_headers()
        unidades = {"D": "Dias", "M": "Meses", "A": "Anos", "H": "Horas", "S": "Semanas"}
        todos = paginar(h, {"limit": 100, "orderBy": [{"column": "descricao", "ascending": True}],
                            "filterGroups": [{"combineOperator": "AND",
                                              "filters": filtros_planos(cfg.EMPRESA_ID, cfg.OFICINA_ID, ativo=None)}]},
                        "/api/planosmanutencao/query")
        itens = [{
            "id": p.get("id", ""), "descricao": p.get("descricao", ""),
            "tipo": ((p.get("tipoManutencao") or {}).get("descricao") or ""),
            "periodicidade": f"{p.get('periodicidade', '')} {unidades.get(p.get('periodicidadeTempoUnidade', ''), '')}".strip(),
            "oficina": ((p.get("oficina") or {}).get("descricao") or ""),
            "procedimento": ((p.get("procedimento") or {}).get("nome") or ""),
            "ativo": p.get("ativo", False),
        } for p in todos]
        payload = {"total": len(itens), "itens": itens}
        _cache.set(ck("planos"), payload)
        return jsonify(payload)

    @bp.route("/exportar_planos", methods=["POST"])
    @tratar_erros
    def api_exportar_planos():
        corpo = request.get_json(silent=True)
        planos = corpo.get("itens") if isinstance(corpo, dict) else corpo
        if not isinstance(planos, list) or not planos:
            raise RequisicaoInvalida("Nenhum dado para exportar.")
        if len(planos) > 5000:
            raise RequisicaoInvalida("Muitos registros para exportar de uma vez.")
        planos = [p for p in planos if isinstance(p, dict)]
        g.audit_details = {"linhas": len(planos)}
        buf = gerar_excel_planos(planos, cfg.NOME)
        return send_file(buf, as_attachment=True, download_name=f"{codigo_unidade.lower()}_planos_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                         mimetype=_XLSX)

    # ── colaboradores ─────────────────────────────────────────────────────────
    def serializar_colab(r) -> dict:
        return {
            "funcionario": r["funcionario"], "cargo": r["cargo"], "turno": r["turno"], "regime": r["regime"],
            "horario": r.get("horario", "") or "", "status": r.get("status", "Ativo"),
            "habilidades": list(r.get("habilidades", []) or []), "bloqueado": bool(r.get("bloqueado", False)),
            "aviso": r.get("aviso"), "data_admissao": r.get("data_admissao"),
            "data_desligamento": r.get("data_desligamento"),
            "fora_da_escala": bool(r.get("fora_da_escala", False)),
            "executa_os": prev.eleg.cargo_executa_os(str(r.get("cargo", ""))),
            "especialidade": prev.limites.especialidade_do_cargo(str(r.get("cargo", ""))),
            "limite_diario": prev.limites.limite_do_cargo(str(r.get("cargo", ""))),
        }

    def achar_colaborador(colab, nome_url: str):
        alvo = nome_url.strip().upper()
        linha = colab[colab["funcionario"].str.strip().str.upper() == alvo]
        if linha.empty:
            return None
        return linha.iloc[0]

    @bp.route("/colaboradores")
    @tratar_erros
    def api_colaboradores():
        colab = roster()
        itens = [serializar_colab(r) for _, r in colab.iterrows()]
        return jsonify({"total": len(itens), "itens": itens})

    @bp.route("/colaborador/<path:nome_colab>")
    @tratar_erros
    def api_colaborador(nome_colab):
        d_ini, d_fim = _periodo()
        if not d_ini and not d_fim:   # sem período: últimos 30 dias (nunca o histórico inteiro da empresa)
            d_fim = prev.hoje_local()
            d_ini = d_fim - timedelta(days=30)
        colab = roster()
        row = achar_colaborador(colab, nome_colab)
        if row is None:
            return jsonify({"erro": "Funcionário não encontrado."}), 404
        base = carregar_base(get_headers(), d_ini, d_fim)
        nome_real = row["funcionario"]
        ctx_nome = nome_real.upper()
        os_abertas = []
        from core.regras.nomes import nomes_batem
        for o in base["abertas_hoje"]:
            resp = (o.get("responsavel") or {}).get("nome", "")
            if resp and nomes_batem(resp, nome_real):
                os_abertas.append({
                    "numero": o.get("numero", ""),
                    "abertura": str(o.get("dataHoraAbertura", "") or "")[:16].replace("T", " "),
                    "tipo": ((o.get("tipoManutencao") or {}).get("descricao") or ""),
                    "setor": ((o.get("setor") or {}).get("nome") or ""),
                    "situacao": {1: "Aberta", 2: "Em Andamento"}.get(o.get("situacao"), "")})
        tipos = {t: c for (n, t), c in base["hist_tipo"].items() if nomes_batem(n, nome_real) or n.upper() == ctx_nome}
        ativos_ = {a: c for (n, a), c in base["hist_ativo"].items() if nomes_batem(n, nome_real) or n.upper() == ctx_nome}
        detalhe = serializar_colab(row)
        detalhe.update({
            "os_abertas": os_abertas, "total_abertas": len(os_abertas), "total_historico": sum(tipos.values()),
            "tipos_servico": [{"tipo": t, "qtd": q} for t, q in sorted(tipos.items(), key=lambda x: -x[1])[:10]],
            "equipamentos": [{"ativo": a, "qtd": q} for a, q in sorted(ativos_.items(), key=lambda x: -x[1])[:10]],
        })
        return jsonify(detalhe)

    @bp.route("/habilidades")
    def api_habilidades():
        return jsonify({"itens": HABILIDADES})

    def _checar_existe(nome_url: str):
        colab = roster()
        row = achar_colaborador(colab, nome_url)
        if row is None:
            raise RequisicaoInvalida("Funcionário não encontrado.", "nome")
        return row["funcionario"]

    @bp.route("/colaborador/<path:nome_colab>/status", methods=["PATCH"])
    @tratar_erros
    def api_colab_status(nome_colab):
        nome_real = _checar_existe(nome_colab)
        status = (request.get_json(silent=True) or {}).get("status")
        if status not in ("Ativo", "Desligado"):
            raise RequisicaoInvalida("status deve ser 'Ativo' ou 'Desligado'.", "status")
        colaboradores_overlay.set_status(cfg.OVERLAY, nome_real, status, por=g.user.username)
        invalidar_tudo()
        g.audit_details = {"colaborador": nome_real, "status": status}
        return jsonify({"funcionario": nome_real, "status": status})

    @bp.route("/colaborador/<path:nome_colab>/vinculo", methods=["PATCH"])
    @tratar_erros
    def api_colab_vinculo(nome_colab):
        """Data de admissão e/ou desligamento por DIA. Body: {"data_admissao": "AAAA-MM-DD"|null,
        "data_desligamento": "AAAA-MM-DD"|null}; campo ausente não é alterado, null remove a data.
        A partir da data de desligamento (inclusive) o colaborador deixa de ser elegível —
        o histórico de OS já atribuídas é preservado."""
        nome_real = _checar_existe(nome_colab)
        corpo = request.get_json(silent=True) or {}
        if "data_admissao" not in corpo and "data_desligamento" not in corpo:
            raise RequisicaoInvalida("Informe data_admissao e/ou data_desligamento.")
        try:
            if "data_admissao" in corpo:
                colaboradores_overlay.set_data_admissao(cfg.OVERLAY, nome_real, corpo.get("data_admissao"), por=g.user.username)
            if "data_desligamento" in corpo:
                colaboradores_overlay.set_data_desligamento(cfg.OVERLAY, nome_real, corpo.get("data_desligamento"), por=g.user.username)
        except ValueError as e:
            raise RequisicaoInvalida(f"Data inválida — use AAAA-MM-DD ({e}).")
        invalidar_tudo()
        g.audit_details = {"colaborador": nome_real, "data_admissao": corpo.get("data_admissao"),
                           "data_desligamento": corpo.get("data_desligamento")}
        return jsonify({"funcionario": nome_real,
                        "data_admissao": corpo.get("data_admissao") if "data_admissao" in corpo else None,
                        "data_desligamento": corpo.get("data_desligamento") if "data_desligamento" in corpo else None})

    @bp.route("/colaborador/<path:nome_colab>/bloqueio", methods=["PATCH"])
    @tratar_erros
    def api_colab_bloqueio(nome_colab):
        nome_real = _checar_existe(nome_colab)
        corpo = request.get_json(silent=True) or {}
        bloqueado = corpo.get("bloqueado")
        if not isinstance(bloqueado, bool):
            raise RequisicaoInvalida("bloqueado deve ser true ou false.", "bloqueado")
        aviso = corpo.get("aviso")
        if aviso is not None and (not isinstance(aviso, str) or len(aviso) > 500):
            raise RequisicaoInvalida("aviso inválido (texto de até 500 caracteres).", "aviso")
        colaboradores_overlay.set_bloqueado(cfg.OVERLAY, nome_real, bloqueado, aviso, por=g.user.username)
        invalidar_tudo()
        g.audit_details = {"colaborador": nome_real, "bloqueado": bloqueado}
        return jsonify({"funcionario": nome_real, "bloqueado": bloqueado, "aviso": aviso if bloqueado else None})

    @bp.route("/colaborador/<path:nome_colab>/habilidades", methods=["POST"])
    @tratar_erros
    def api_colab_add_hab(nome_colab):
        nome_real = _checar_existe(nome_colab)
        hid = (request.get_json(silent=True) or {}).get("habilidade_id")
        if hid not in HABILIDADES_POR_ID:
            raise RequisicaoInvalida(f"habilidade_id desconhecido: {hid!r}", "habilidade_id")
        habilidades = colaboradores_overlay.adicionar_habilidade(cfg.OVERLAY, nome_real, hid, por=g.user.username)
        invalidar_tudo()
        g.audit_details = {"colaborador": nome_real, "habilidade": hid, "operacao": "adicionar"}
        return jsonify({"funcionario": nome_real, "habilidades": habilidades})

    @bp.route("/colaborador/<path:nome_colab>/habilidades/<habilidade_id>", methods=["DELETE"])
    @tratar_erros
    def api_colab_rm_hab(nome_colab, habilidade_id):
        nome_real = _checar_existe(nome_colab)
        habilidades = colaboradores_overlay.remover_habilidade(cfg.OVERLAY, nome_real, habilidade_id, por=g.user.username)
        invalidar_tudo()
        g.audit_details = {"colaborador": nome_real, "habilidade": habilidade_id, "operacao": "remover"}
        return jsonify({"funcionario": nome_real, "habilidades": habilidades})

    @bp.route("/limpar_cache", methods=["POST"])
    @tratar_erros
    def api_limpar_cache():
        return jsonify({"removidas": _cache.delete_prefix(prefixo_cache)})

    # ── regras nominais (5.4 / 5.5) ───────────────────────────────────────────
    @bp.route("/regras")
    @tratar_erros
    def api_regras():
        colab = roster()
        res = resolvidas(colab)
        executantes = [r["funcionario"] for _, r in ativos(colab).iterrows()
                       if prev.eleg.cargo_executa_os(str(r.get("cargo", "")))]
        return jsonify({"regras": regras_mod.descrever(res), "quadro_ativo": sorted(executantes)})

    @bp.route("/regras/resolucoes", methods=["PUT"])
    @tratar_erros
    def api_regras_confirmar():
        corpo = request.get_json(silent=True) or {}
        alias, funcionario = str(corpo.get("alias", "")), str(corpo.get("funcionario", ""))
        colab = roster()
        validos = {a for r in regras for a in r.aliases()}
        if normalizar_nome(alias) not in validos:
            raise RequisicaoInvalida("Apelido não pertence a nenhuma regra desta unidade.", "alias")
        quadro = ativos(colab)
        if funcionario not in set(quadro["funcionario"]):
            raise RequisicaoInvalida("O colaborador informado não está ativo no quadro desta unidade.", "funcionario")
        linha = quadro[quadro["funcionario"] == funcionario].iloc[0]
        if not prev.eleg.cargo_executa_os(str(linha.get("cargo", ""))):
            raise RequisicaoInvalida("Este colaborador não executa ordens de serviço (cargo de gestão/administração).",
                                     "funcionario")
        alias_n, nome_n = normalizar_nome(alias).split(), normalizar_nome(funcionario).split()
        if not alias_n or not nome_n or not nome_n[0].startswith(alias_n[0]):
            raise RequisicaoInvalida("O primeiro nome do colaborador não corresponde ao apelido da regra.", "funcionario")
        regras_db.confirmar(codigo_unidade, alias, funcionario, g.user.username)
        _cache.delete_prefix(ck("prev_"))
        g.audit_details = {"alias": alias, "funcionario": funcionario}
        return jsonify({"ok": True})

    @bp.route("/regras/resolucoes", methods=["DELETE"])
    @tratar_erros
    def api_regras_remover():
        alias = request.args.get("alias", "")
        n = regras_db.remover(codigo_unidade, alias)
        _cache.delete_prefix(ck("prev_"))
        g.audit_details = {"alias": alias, "removidas": n}
        return jsonify({"removidas": n})

    # ── atribuição de executantes no Neovero (5.7) ────────────────────────────
    @bp.route("/atribuicoes")
    @tratar_erros
    def api_atribuicoes():
        d_ini, d_fim = _periodo(obrigatorio=True)
        r = gerar(d_ini, d_fim, True)
        base = r["base"]
        ids = atribuicoes.mapa_funcionarios_neovero(base["todas_periodo"] + base["abertas_hoje"])
        fila = atribuicoes.montar_fila(r["itens"], ids)
        from core.settings import settings
        return jsonify({
            "fila": fila,
            "propostas": atribuicoes.listar_propostas(codigo_unidade),
            "integracao": {
                "escrita_habilitada": settings.neovero_escrita_habilitada,
                "simulacao": settings.neovero_escrita_simulada,
                "aviso": ("A escrita no Neovero usa a API interna do cliente web (sem documentação oficial) e "
                          "não foi validada em ambiente de teste. Padrão: desligada; quando ligada, começa em simulação."),
            },
        })

    @bp.route("/atribuicoes/propostas", methods=["POST"])
    @tratar_erros
    def api_atribuicoes_criar():
        corpo = request.get_json(silent=True) or {}
        d_ini, d_fim = _parse_data(corpo.get("data_ini"), "data_ini"), _parse_data(corpo.get("data_fim"), "data_fim")
        if not d_ini or not d_fim:
            raise RequisicaoInvalida("Informe data_ini e data_fim.")
        os_ids = {int(x) for x in corpo.get("os_ids", []) if str(x).isdigit()}
        if not os_ids:
            raise RequisicaoInvalida("Informe os_ids.")
        r = gerar(d_ini, d_fim, True)
        base = r["base"]
        ids = atribuicoes.mapa_funcionarios_neovero(base["todas_periodo"] + base["abertas_hoje"])
        fila = [f for f in atribuicoes.montar_fila(r["itens"], ids) if int(f["os_id"]) in os_ids]
        originais = {int(o["id"]): o.get("responsavelId") for o in base["todas_periodo"] + base["abertas_hoje"]}
        res = atribuicoes.criar_propostas(codigo_unidade, fila, g.user.username, originais)
        g.audit_details = {"solicitadas": len(os_ids), "criadas": sum(1 for x in res if x.get("criada"))}
        return jsonify({"resultado": res})

    @bp.route("/atribuicoes/decisao", methods=["POST"])
    @tratar_erros
    def api_atribuicoes_decidir():
        corpo = request.get_json(silent=True) or {}
        ids = [int(x) for x in corpo.get("ids", []) if str(x).isdigit()]
        acao = corpo.get("acao")
        if not ids or acao not in ("aprovar", "rejeitar"):
            raise RequisicaoInvalida("Informe ids e acao ('aprovar' ou 'rejeitar').")
        n = atribuicoes.decidir(codigo_unidade, ids, acao == "aprovar", g.user.username)
        g.audit_details = {"acao": acao, "propostas": n}
        return jsonify({"atualizadas": n})

    @bp.route("/atribuicoes/processar", methods=["POST"])
    @tratar_erros
    def api_atribuicoes_processar():
        corpo = request.get_json(silent=True) or {}
        ids = [int(x) for x in corpo.get("ids", []) if str(x).isdigit()]
        modo = corpo.get("modo", "simular")
        if not ids or modo not in ("simular", "aplicar"):
            raise RequisicaoInvalida("Informe ids e modo ('simular' ou 'aplicar').")
        colab = roster()
        cargos = dict(zip(colab["funcionario"], colab["cargo"]))
        try:
            res = atribuicoes.processar(codigo_unidade, cfg.EMPRESA_ID, ids, g.user.username, get_headers(), cargos,
                                        modo=modo, user_obj=g.user)
        except atribuicoes.EscritaDesabilitada as e:
            return jsonify({"erro": str(e), "codigo": "escrita_desabilitada"}), 409
        _cache.delete_prefix(ck("prev_"))
        g.audit_details = {"modo": modo, "propostas": len(res)}
        return jsonify({"resultado": res})

    return bp
