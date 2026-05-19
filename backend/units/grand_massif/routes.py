"""
Blueprint Flask — Grand Massif.
Rotas: /api/grandmassif/*
"""
import time
from collections import defaultdict
from datetime import datetime, date

from flask import Blueprint, jsonify, request, send_file

from core import cache as _cache_module
from core.neovero_client import (
    get_headers, paginar, buscar_itens_plano, filtros_planos, SIT_MAP, URL_BASE,
)
from core.exporters import gerar_excel_preventivas, gerar_excel_recomendacoes
from units.grand_massif import config as CFG
from units.grand_massif.colaboradores import carregar_colaboradores
from units.grand_massif.motor import indicar_responsavel, extrair_ativo

import requests as _requests

bp = Blueprint("grand_massif", __name__, url_prefix="/api/grandmassif")

_CACHE_PREFIX = "gm_"


def _ck(key: str) -> str:
    return _CACHE_PREFIX + key


def _parse_dates():
    d_ini = d_fim = None
    try:
        v = request.args.get("data_ini")
        if v:
            d_ini = datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        pass
    try:
        v = request.args.get("data_fim")
        if v:
            d_fim = datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        pass
    return d_ini, d_fim


def _filtrar_por_data(lista, d_ini=None, d_fim=None):
    if not d_ini and not d_fim:
        return lista
    out = []
    for o in lista:
        dt_str = str(o.get("dataHoraAbertura", "") or "")[:10]
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
            if d_ini and dt < d_ini:
                continue
            if d_fim and dt > d_fim:
                continue
            out.append(o)
        except Exception:
            out.append(o)
    return out


def _todas_os_payload():
    return {
        "limit": 100,
        "sort": [{"field": "dataHoraAbertura", "dir": "desc"}],
        "filterGroups": [{
            "combineOperator": "AND",
            "filters": [
                {"property": "empresa.id", "value": [CFG.EMPRESA_ID]},
                {"property": "periodoAbertura", "value": {"rangeType": "CUSTOM", "customStart": None, "customEnd": None}},
                {"property": "periodoFechamento", "value": {"rangeType": "CUSTOM", "customStart": None, "customEnd": None}},
            ],
        }],
    }


def _nomes_batem(nome_api: str, nome_planilha: str) -> bool:
    def normalizar(n):
        return [p.replace(".", "").lower() for p in n.strip().split() if len(p) > 1]
    partes_api = normalizar(nome_api)
    partes_planilha = normalizar(nome_planilha)
    if not partes_api or not partes_planilha:
        return False
    if partes_api[0] != partes_planilha[0]:
        return False
    partes_api_full = [p for p in partes_api if len(p) > 1]
    partes_planilha_full = [p for p in partes_planilha if len(p) > 1]
    matches = sum(1 for p in partes_planilha_full if any(
        p == q or p.startswith(q[:3]) or q.startswith(p[:3])
        for q in partes_api_full
    ))
    return matches >= max(2, len(partes_planilha_full) * 0.6)


def _carregar_dados_base(headers, d_ini=None, d_fim=None):
    cache_key = _ck(f"base_{d_ini}_{d_fim}")
    cached = _cache_module.get(cache_key)
    if cached:
        return cached

    colab = carregar_colaboradores()
    todas = paginar(headers, _todas_os_payload(), "/api/ordensservico/query")

    abertas_hoje = [o for o in todas if o.get("situacao") in (1, 2)]
    fechadas_todas = [o for o in todas if o.get("situacao") == 3]
    todas_periodo = _filtrar_por_data(todas, d_ini, d_fim)
    fechadas_periodo = _filtrar_por_data(fechadas_todas, d_ini, d_fim) if (d_ini or d_fim) else fechadas_todas

    hist_tipo = defaultdict(int)
    hist_ativo = defaultdict(int)
    carga = defaultdict(int)

    for o in fechadas_periodo:
        resp = o.get("responsavel") or {}
        nome = (resp.get("nome") or "").strip()
        t = ((o.get("tipoManutencao") or {}).get("descricao") or "").strip()
        a = ((o.get("equipamento") or {}).get("nome") or "").strip()
        if nome:
            if t:
                hist_tipo[(nome, t)] += 1
            if a:
                hist_ativo[(nome, a)] += 1

    for o in abertas_hoje:
        resp = o.get("responsavel") or {}
        nome = (resp.get("nome") or "").strip()
        if nome:
            carga[nome] += 1

    result = {
        "colab": colab,
        "hist_tipo": hist_tipo,
        "hist_ativo": hist_ativo,
        "carga": carga,
        "todas_periodo": todas_periodo,
        "abertas_hoje": abertas_hoje,
        "fechadas_periodo": fechadas_periodo,
    }
    _cache_module.set(cache_key, result)
    return result


def _enriquecer_os(o, headers):
    os_id = o.get("id")
    ck = _ck(f"os_{os_id}")
    cached = _cache_module.get(ck)
    if cached:
        return cached
    r = _requests.get(f"{URL_BASE}/api/ordensservico/{os_id}", headers=headers, timeout=60)
    det = r.json() if r.status_code == 200 else o
    _cache_module.set(ck, det)
    return det


def _montar_item_os(o, headers, colab, hist_tipo, hist_ativo, carga):
    det = _enriquecer_os(o, headers)
    tipo = ((det.get("tipoManutencao") or {}).get("descricao") or "").strip()
    setor = ((det.get("setor") or {}).get("nome") or "").strip()
    ativo = extrair_ativo(det)
    resp_atual = ((det.get("responsavel") or {}).get("nome") or "").strip()
    sit = SIT_MAP.get(o.get("situacao"), "")
    dt_str = str(det.get("dataHoraAbertura", "") or "")
    try:
        dt_os = datetime.fromisoformat(dt_str[:19].replace("T", " "))
        data_os = dt_os.date()
        hora_os = dt_os.hour
    except Exception:
        data_os = date.today()
        hora_os = 8

    recomend, cargo, escala, score = (None, None, None, -999)
    if colab is not None:
        principal, _, _ = indicar_responsavel(colab, hist_tipo, hist_ativo, carga, tipo, setor, ativo, data_os, hora_os)
        if principal:
            recomend = principal["nome"]
            cargo = principal["cargo"]
            escala = principal["escala"]
            score = principal["score"]

    if not recomend:
        status = "Sem candidato"
    elif resp_atual and _nomes_batem(resp_atual, recomend):
        status = "Bate com atual"
    elif resp_atual:
        status = "Sugestao diferente"
    else:
        status = "Sem resp. atual"

    return {
        "numero": o.get("numero", ""),
        "tipo": tipo,
        "setor": setor,
        "ativo": ativo,
        "situacao": sit,
        "prioridade": ((o.get("prioridade") or {}).get("descricao") or ""),
        "reclamacao": (o.get("reclamacao") or ""),
        "responsavel_atual": resp_atual or None,
        "recomendado": recomend,
        "cargo": cargo or "",
        "escala": escala or "",
        "score": score,
        "status": status,
        "data_os": data_os.strftime("%d/%m/%Y"),
        "hora_os": hora_os,
        "turno_os": "Diurno" if 7 <= hora_os < 19 else "Noturno",
        "dia_par": "Par" if data_os.day % 2 == 0 else "Ímpar",
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@bp.route("/os")
def api_os():
    try:
        d_ini, d_fim = _parse_dates()
        h = get_headers()
        base = _carregar_dados_base(h, d_ini, d_fim)
        todas = base["todas_periodo"]

        sit_filtro = request.args.get("situacao")
        if sit_filtro:
            try:
                sit_int = int(sit_filtro)
                todas = [o for o in todas if o.get("situacao") == sit_int]
            except Exception:
                pass

        itens = [{
            "numero": o.get("numero", ""),
            "abertura": str(o.get("dataHoraAbertura", "") or "")[:16].replace("T", " "),
            "tipo": ((o.get("tipoManutencao") or {}).get("descricao") or ""),
            "setor": ((o.get("setor") or {}).get("nome") or ""),
            "prioridade": ((o.get("prioridade") or {}).get("descricao") or ""),
            "situacao": o.get("situacao"),
            "sit_label": SIT_MAP.get(o.get("situacao"), ""),
            "responsavel": (o.get("responsavel") or {}).get("nome", "") or None,
            "reclamacao": o.get("reclamacao") or "",
        } for o in todas]

        return jsonify({
            "total": len(todas),
            "com_responsavel": sum(1 for o in todas if o.get("responsavel")),
            "sem_responsavel": sum(1 for o in todas if not o.get("responsavel")),
            "abertas": sum(1 for o in todas if o.get("situacao") == 1),
            "em_andamento": sum(1 for o in todas if o.get("situacao") == 2),
            "fechadas": sum(1 for o in todas if o.get("situacao") == 3),
            "pendencia": sum(1 for o in todas if o.get("situacao") == 2),
            "itens": itens,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/recomendacoes")
def api_recomendacoes():
    try:
        d_ini, d_fim = _parse_dates()
        h = get_headers()
        base = _carregar_dados_base(h, d_ini, d_fim)
        colab, hist_tipo, hist_ativo, carga = base["colab"], base["hist_tipo"], base["hist_ativo"], base["carga"]
        if colab is None:
            return jsonify({"erro": "Planilha de colaboradores não encontrada"}), 500

        todas = base["todas_periodo"]
        if not todas:
            return jsonify({"erro": "Nenhuma OS encontrada no período."}), 404

        resultados = [_montar_item_os(o, h, colab, hist_tipo, hist_ativo, carga) for o in todas]
        _cache_module.set(_ck("recomendacoes"), resultados)

        return jsonify({
            "total": len(resultados),
            "com_responsavel": sum(1 for r in resultados if r["responsavel_atual"]),
            "sem_responsavel": sum(1 for r in resultados if not r["responsavel_atual"]),
            "bate_atual": sum(1 for r in resultados if r["status"] == "Bate com atual"),
            "sugestao_diff": sum(1 for r in resultados if r["status"] == "Sugestao diferente"),
            "sem_candidato": sum(1 for r in resultados if r["status"] == "Sem candidato"),
            "itens": resultados,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/tasks_por_funcionario")
def api_tasks_por_funcionario():
    try:
        recomendacoes = _cache_module.get(_ck("recomendacoes"))
        if recomendacoes is None:
            return jsonify({"erro": "Calcule as recomendações primeiro"}), 400

        h = get_headers()
        d_ini, d_fim = _parse_dates()
        base = _carregar_dados_base(h, d_ini, d_fim)
        colab = base["colab"]
        if colab is None:
            return jsonify({"erro": "Planilha de colaboradores não encontrada"}), 500

        por_func = defaultdict(list)
        for r in recomendacoes:
            if r["recomendado"]:
                por_func[r["recomendado"]].append(r)

        resultado = []
        for _, row in colab.iterrows():
            nome = row["funcionario"]
            tasks = por_func.get(nome, [])
            resultado.append({
                "funcionario": nome,
                "cargo": row["cargo"],
                "turno": row["turno"],
                "regime": row["regime"],
                "total_tasks": len(tasks),
                "tasks": tasks,
            })
        resultado.sort(key=lambda x: -x["total_tasks"])
        return jsonify({"total": len(resultado), "itens": resultado})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/colaborador/<path:nome>")
def api_colaborador(nome):
    try:
        d_ini, d_fim = _parse_dates()
        h = get_headers()
        base = _carregar_dados_base(h, d_ini, d_fim)
        colab = base["colab"]
        if colab is None:
            return jsonify({"erro": "Planilha de colaboradores não encontrada"}), 500

        row = colab[colab["funcionario"].str.strip().str.upper() == nome.strip().upper()]
        if row.empty:
            primeiro = nome.strip().upper().split()[0]
            row = colab[colab["funcionario"].str.strip().str.upper().str.startswith(primeiro)]
        if row.empty:
            return jsonify({"erro": "Funcionário não encontrado"}), 404
        row = row.iloc[0]

        os_abertas = []
        for o in base["abertas_hoje"]:
            resp = (o.get("responsavel") or {}).get("nome", "")
            if resp and resp.upper() == nome.upper():
                os_abertas.append({
                    "numero": o.get("numero", ""),
                    "abertura": str(o.get("dataHoraAbertura", "") or "")[:16].replace("T", " "),
                    "tipo": ((o.get("tipoManutencao") or {}).get("descricao") or ""),
                    "setor": ((o.get("setor") or {}).get("nome") or ""),
                    "situacao": SIT_MAP.get(o.get("situacao"), ""),
                })

        hist_tipo = base["hist_tipo"]
        hist_ativo = base["hist_ativo"]
        tipos = {t: c for (n, t), c in hist_tipo.items() if n.upper() == nome.upper()}
        ativos = {a: c for (n, a), c in hist_ativo.items() if n.upper() == nome.upper()}

        return jsonify({
            "funcionario": nome,
            "cargo": row["cargo"],
            "turno": row["turno"],
            "regime": row["regime"],
            "horario": row.get("horario", ""),
            "os_abertas": os_abertas,
            "total_abertas": len(os_abertas),
            "total_historico": sum(tipos.values()),
            "tipos_servico": [{"tipo": t, "qtd": q} for t, q in sorted(tipos.items(), key=lambda x: -x[1])[:10]],
            "equipamentos": [{"ativo": a, "qtd": q} for a, q in sorted(ativos.items(), key=lambda x: -x[1])[:10]],
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/preventivas")
def api_preventivas():
    try:
        d_ini, d_fim = _parse_dates()
        if not d_ini or not d_fim:
            return jsonify({"erro": "Informe data_ini e data_fim."}), 400

        ck = _ck(f"prev_{d_ini}_{d_fim}")
        cached = _cache_module.get(ck)
        if cached:
            return jsonify({"total": len(cached), "com_recomendacao": sum(1 for p in cached if p["recomendado"]), "itens": cached})

        h = get_headers()
        base_ck = _ck(f"base_{d_ini}_{d_fim}")
        base = _cache_module.get(base_ck)
        if base:
            colab, hist_tipo, hist_ativo, carga = base["colab"], base["hist_tipo"], base["hist_ativo"], base["carga"]
        else:
            colab = carregar_colaboradores()
            hist_tipo = hist_ativo = carga = defaultdict(int)

        planos = paginar(h, {
            "limit": 100,
            "orderBy": [{"column": "descricao", "ascending": True}],
            "filterGroups": [{"combineOperator": "AND", "filters": filtros_planos(CFG.EMPRESA_ID, CFG.OFICINA_ID)}],
        }, "/api/planosmanutencao/query")

        preventivas = []
        for idx, p in enumerate(planos, 1):
            itens = buscar_itens_plano(h, p["id"])
            tipo = ((p.get("tipoManutencao") or {}).get("descricao") or "").strip()
            oficina = ((p.get("oficina") or {}).get("descricao") or "").strip()
            tipo_classif = f"{tipo} {p.get('descricao', '')} {oficina}".strip()

            for item in itens:
                dt_str = str(item.get("dataProximaPreventiva") or "")[:10]
                if not dt_str:
                    continue
                try:
                    dt_prev = datetime.strptime(dt_str, "%Y-%m-%d").date()
                except Exception:
                    continue
                if not (d_ini <= dt_prev <= d_fim):
                    continue

                equip = item.get("equipamento") or {}
                setor = (item.get("setor") or equip.get("setorAtual") or {}).get("nome", "") or ""
                os_v = item.get("ordemServico") or {}
                equip_nome = (equip.get("nome") or "").strip()

                recomend, cargo, escala, score = (None, None, None, -999)
                if colab is not None:
                    principal, _, _ = indicar_responsavel(colab, hist_tipo, hist_ativo, carga, tipo_classif, setor, equip_nome, dt_prev)
                    if principal:
                        recomend = principal["nome"]
                        cargo = principal["cargo"]
                        escala = principal["escala"]
                        score = principal["score"]

                preventivas.append({
                    "data_prev": dt_prev.strftime("%d/%m/%Y"),
                    "dia_par": "Par" if dt_prev.day % 2 == 0 else "Ímpar",
                    "plano": p.get("descricao", ""),
                    "tipo": tipo,
                    "oficina": oficina,
                    "equipamento": equip_nome or "—",
                    "setor": setor or "—",
                    "os_vinculada": os_v.get("numero", "") or "—",
                    "os_situacao": SIT_MAP.get(os_v.get("situacao"), "—") if os_v.get("situacao") else "—",
                    "recomendado": recomend,
                    "cargo": cargo or "",
                    "escala": escala or "",
                    "score": score,
                })
            print(f"[GM preventivas] {idx}/{len(planos)} | {len(preventivas)} itens")

        _cache_module.set(ck, preventivas)
        return jsonify({"total": len(preventivas), "com_recomendacao": sum(1 for p in preventivas if p["recomendado"]), "itens": preventivas})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/planos")
def api_planos():
    try:
        cached = _cache_module.get(_ck("planos"))
        if cached:
            return jsonify(cached)

        h = get_headers()
        unidades = {"D": "Dias", "M": "Meses", "A": "Anos", "H": "Horas", "S": "Semanas"}
        todos = paginar(h, {
            "limit": 100,
            "orderBy": [{"column": "descricao", "ascending": True}],
            "filterGroups": [{"combineOperator": "AND", "filters": filtros_planos(CFG.EMPRESA_ID, CFG.OFICINA_ID, ativo=None)}],
        }, "/api/planosmanutencao/query")
        itens = [{
            "id": p.get("id", ""),
            "descricao": p.get("descricao", ""),
            "tipo": ((p.get("tipoManutencao") or {}).get("descricao") or ""),
            "periodicidade": f"{p.get('periodicidade', '')} {unidades.get(p.get('periodicidadeTempoUnidade', ''), '')}".strip(),
            "oficina": ((p.get("oficina") or {}).get("descricao") or ""),
            "procedimento": ((p.get("procedimento") or {}).get("nome") or ""),
            "ativo": p.get("ativo", False),
        } for p in todos]
        payload = {"total": len(itens), "itens": itens}
        _cache_module.set(_ck("planos"), payload)
        return jsonify(payload)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/colaboradores")
def api_colaboradores():
    try:
        colab = carregar_colaboradores()
        if colab is None:
            return jsonify({"erro": "Planilha de colaboradores não encontrada"}), 500
        itens = [{
            "funcionario": r["funcionario"], "cargo": r["cargo"],
            "turno": r["turno"], "regime": r["regime"], "horario": r.get("horario", ""),
        } for _, r in colab.iterrows()]
        return jsonify({"total": len(itens), "itens": itens})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@bp.route("/exportar")
def api_exportar():
    recomendacoes = _cache_module.get(_ck("recomendacoes"))
    if not recomendacoes:
        return jsonify({"erro": "Calcule as recomendações primeiro"}), 400
    from datetime import datetime as dt
    buf = gerar_excel_recomendacoes(recomendacoes, CFG.NOME)
    nome = f"gm_recomendacoes_{dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(buf, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/exportar_preventivas", methods=["POST"])
def api_exportar_preventivas():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"erro": "Nenhum dado para exportar"}), 400
        prev = body.get("itens", body) if isinstance(body, dict) else body
        d_ini, d_fim = _parse_dates()
        buf = gerar_excel_preventivas(prev, d_ini, d_fim, CFG.NOME)
        sufixo = f"{d_ini.strftime('%Y%m%d') if d_ini else 'inicio'}_{d_fim.strftime('%Y%m%d') if d_fim else 'fim'}"
        return send_file(buf, as_attachment=True, download_name=f"gm_preventivas_{sufixo}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/limpar_cache", methods=["POST"])
def api_limpar_cache():
    n = _cache_module.delete_prefix(_CACHE_PREFIX + "prev_")
    return jsonify({"removidas": n})
