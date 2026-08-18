"""
Blueprint Flask — Hospital Municipal Brasilândia.
Rotas: /api/brasilandia/*
"""
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

from core import cache as _cache_module
from core import colaboradores_overlay
from core.motor_base import HABILIDADES, HABILIDADES_POR_ID
from core.neovero_client import (
    get_headers, paginar, buscar_itens_varios_planos, filtros_planos, os_vinculada_visivel,
)
from core.exporters import gerar_excel_preventivas
from core.planejamento import detectar_paridade, expandir_ocorrencias as _expandir_ocorrencias
from units.brasilandia import config as CFG
from units.brasilandia.colaboradores import carregar_colaboradores, invalidar_cache as invalidar_cache_colaboradores
from units.brasilandia.motor import indicar_responsavel

bp = Blueprint("brasilandia", __name__, url_prefix="/api/brasilandia")

_CACHE_PREFIX = "br_"


def _ck(key: str) -> str:
    return _CACHE_PREFIX + key


def _colab_ativos(colab):
    """Colaboradores Desligados nunca são recomendados para novas preventivas, mas
    continuam existindo na planilha/overlay e em listagens/histórico."""
    if colab is None:
        return None
    return colab[colab["status"] == "Ativo"]


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@bp.route("/colaborador/<path:nome>")
def api_colaborador(nome):
    try:
        colab = carregar_colaboradores()
        if colab is None:
            return jsonify({"erro": "Planilha de colaboradores não encontrada"}), 500

        row = colab[colab["funcionario"].str.strip().str.upper() == nome.strip().upper()]
        if row.empty:
            primeiro = nome.strip().upper().split()[0]
            row = colab[colab["funcionario"].str.strip().str.upper().str.startswith(primeiro)]
        if row.empty:
            return jsonify({"erro": "Funcionário não encontrado"}), 404
        row = row.iloc[0]

        return jsonify({
            "funcionario": nome,
            "cargo": row["cargo"],
            "turno": row["turno"],
            "regime": row["regime"],
            "horario": row.get("horario", ""),
            "status": row.get("status", "Ativo"),
            "habilidades": list(row.get("habilidades", []) or []),
            "bloqueado": bool(row.get("bloqueado", False)),
            "aviso": row.get("aviso"),
            "os_abertas": [],
            "total_abertas": 0,
            "total_historico": 0,
            "tipos_servico": [],
            "equipamentos": [],
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
        colab = _colab_ativos(carregar_colaboradores())
        hist_tipo = defaultdict(int)
        hist_ativo = defaultdict(int)
        carga = defaultdict(int)

        planos = paginar(h, {
            "limit": 100,
            "orderBy": [{"column": "descricao", "ascending": True}],
            "filterGroups": [{"combineOperator": "AND", "filters": filtros_planos(CFG.EMPRESA_ID, CFG.OFICINA_ID, ativo=True)}],
        }, "/api/planosmanutencao/query")

        itens_por_plano = buscar_itens_varios_planos(h, planos)

        preventivas = []
        for idx, p in enumerate(planos, 1):
            itens = itens_por_plano.get(p["id"], [])
            tipo = ((p.get("tipoManutencao") or {}).get("descricao") or "").strip()
            oficina = ((p.get("oficina") or {}).get("descricao") or "").strip()
            tipo_classif = f"{tipo} {p.get('descricao', '')} {oficina}".strip()
            periodicidade = int(p.get("periodicidade") or 0)
            unidade = str(p.get("periodicidadeTempoUnidade") or "D")
            paridade = detectar_paridade(p.get("descricao", ""))

            for item in itens:
                dt_str = str(item.get("dataProximaPreventiva") or "")[:10]
                if not dt_str:
                    continue
                try:
                    dt_base = datetime.strptime(dt_str, "%Y-%m-%d").date()
                except Exception:
                    continue

                equip = item.get("equipamento") or {}
                setor = (item.get("setor") or equip.get("setorAtual") or {}).get("nome", "") or ""
                os_numero, os_situacao = os_vinculada_visivel(item.get("ordemServico"))
                equip_nome = (equip.get("nome") or "").strip()

                datas = _expandir_ocorrencias(dt_base, periodicidade, unidade, d_ini, d_fim, paridade)

                for dt_prev in datas:
                    recomend, cargo, escala, score = (None, None, None, -999)
                    if colab is not None:
                        principal, _, _ = indicar_responsavel(colab, hist_tipo, hist_ativo, carga, tipo_classif, setor, equip_nome, dt_prev)
                        if principal:
                            recomend = principal["nome"]
                            cargo = principal["cargo"]
                            escala = principal["escala"]
                            score = principal["score"]
                            carga[recomend] += 1

                    preventivas.append({
                        "data_prev": dt_prev.strftime("%d/%m/%Y"),
                        "dia_par": "Par" if dt_prev.day % 2 == 0 else "Ímpar",
                        "plano": p.get("descricao", ""),
                        "tipo": tipo,
                        "oficina": oficina,
                        "equipamento": equip_nome or "—",
                        "setor": setor or "—",
                        "os_vinculada": os_numero,
                        "os_situacao": os_situacao,
                        "recomendado": recomend,
                        "cargo": cargo or "",
                        "escala": escala or "",
                        "score": score,
                    })
            print(f"[BR preventivas] {idx}/{len(planos)} | {len(preventivas)} itens")

        preventivas.sort(key=lambda x: datetime.strptime(x["data_prev"], "%d/%m/%Y"))
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
            return jsonify({"erro": "colaboradores.xlsx não encontrado"}), 500
        itens = [{
            "funcionario": r["funcionario"], "cargo": r["cargo"],
            "turno": r["turno"], "regime": r["regime"], "horario": r.get("horario", ""),
            "status": r.get("status", "Ativo"), "habilidades": list(r.get("habilidades", []) or []),
            "bloqueado": bool(r.get("bloqueado", False)), "aviso": r.get("aviso"),
        } for _, r in colab.iterrows()]
        return jsonify({"total": len(itens), "itens": itens})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@bp.route("/habilidades")
def api_habilidades():
    return jsonify({"itens": HABILIDADES})


@bp.route("/colaborador/<path:nome>/status", methods=["PATCH"])
def api_colaborador_status(nome):
    try:
        body = request.get_json(silent=True) or {}
        status = body.get("status")
        if status not in ("Ativo", "Desligado"):
            return jsonify({"erro": "status deve ser 'Ativo' ou 'Desligado'"}), 400
        colaboradores_overlay.set_status(CFG.DATA_DIR, nome, status)
        invalidar_cache_colaboradores()
        return jsonify({"funcionario": nome, "status": status})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/colaborador/<path:nome>/habilidades", methods=["POST"])
def api_colaborador_add_habilidade(nome):
    try:
        body = request.get_json(silent=True) or {}
        habilidade_id = body.get("habilidade_id")
        if habilidade_id not in HABILIDADES_POR_ID:
            return jsonify({"erro": f"habilidade_id desconhecido: {habilidade_id!r}"}), 400
        habilidades = colaboradores_overlay.adicionar_habilidade(CFG.DATA_DIR, nome, habilidade_id)
        invalidar_cache_colaboradores()
        return jsonify({"funcionario": nome, "habilidades": habilidades})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/colaborador/<path:nome>/habilidades/<habilidade_id>", methods=["DELETE"])
def api_colaborador_remove_habilidade(nome, habilidade_id):
    try:
        habilidades = colaboradores_overlay.remover_habilidade(CFG.DATA_DIR, nome, habilidade_id)
        invalidar_cache_colaboradores()
        return jsonify({"funcionario": nome, "habilidades": habilidades})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


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
        return send_file(buf, as_attachment=True, download_name=f"br_preventivas_{sufixo}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


@bp.route("/limpar_cache", methods=["POST"])
def api_limpar_cache():
    n = _cache_module.delete_prefix(_CACHE_PREFIX + "prev_")
    return jsonify({"removidas": n})


@bp.route("/debug_itens")
def api_debug_itens():
    """Diagnóstico: descobre qual endpoint Neovero retorna os itens do período."""
    import requests as _req
    from core.neovero_client import URL_BASE
    try:
        d_ini, d_fim = _parse_dates()
        if not d_ini or not d_fim:
            return jsonify({"erro": "Informe data_ini e data_fim"}), 400

        h = get_headers()
        resultado = {}

        # 1. Quantos planos existem (ativo=None)?
        r_planos = _req.post(URL_BASE + "/api/planosmanutencao/query",
            headers={**h, "content-type": "application/json"},
            json={"limit": 1, "offset": 0, "filterGroups": [{"combineOperator": "AND", "filters": filtros_planos(CFG.EMPRESA_ID, CFG.OFICINA_ID, ativo=None)}]},
            timeout=15)
        if r_planos.status_code == 200:
            d = r_planos.json()
            resultado["total_planos_neovero"] = d.get("total", d.get("totalRecords", "?"))

        # 2. Testa endpoints alternativos de itens com filtro de data
        payloads = [
            # Payload A: filtro por periodo de data prevista
            {"limit": 10, "offset": 0, "filterGroups": [{"combineOperator": "AND", "filters": [
                {"property": "empresa.id", "value": CFG.EMPRESA_ID},
                {"property": "periodo", "value": {"rangeType": "CUSTOM",
                    "customStart": d_ini.strftime("%Y-%m-%dT00:00:00"),
                    "customEnd": d_fim.strftime("%Y-%m-%dT23:59:59")}},
            ]}]},
            # Payload B: filtro por dataProximaPreventiva
            {"limit": 10, "offset": 0, "filterGroups": [{"combineOperator": "AND", "filters": [
                {"property": "plano.empresa.id", "value": CFG.EMPRESA_ID},
                {"property": "dataProximaPreventiva", "value": {"rangeType": "CUSTOM",
                    "customStart": d_ini.strftime("%Y-%m-%dT00:00:00"),
                    "customEnd": d_fim.strftime("%Y-%m-%dT23:59:59")}},
            ]}]},
        ]
        endpoints = [
            "/api/planosmanutencao/itens/query",
            "/api/itenspreventivasmanutencao/query",
            "/api/itensplanosmanutencao/query",
            "/api/preventivas/query",
        ]
        for endpoint in endpoints:
            for i, payload in enumerate(payloads):
                try:
                    r = _req.post(URL_BASE + endpoint,
                                  headers={**h, "content-type": "application/json"},
                                  json=payload, timeout=10)
                    key = f"{endpoint}__payload{i+1}"
                    if r.status_code == 200:
                        d = r.json()
                        resultado[key] = {
                            "status": 200,
                            "total": d.get("total", d.get("totalRecords", "?")),
                            "keys": list(d.keys())[:6],
                        }
                    else:
                        resultado[key] = {"status": r.status_code, "body": r.text[:200]}
                except Exception as ex:
                    resultado[f"{endpoint}__payload{i+1}"] = {"erro": str(ex)[:100]}

        return jsonify(resultado)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"erro": str(e)}), 500
