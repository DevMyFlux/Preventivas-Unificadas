"""
Blueprint Flask — Hospital Municipal Brasilândia.
Rotas: /api/brasilandia/*
"""
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

from core import cache as _cache_module
from core.neovero_client import get_headers, paginar, buscar_itens_plano, filtros_planos, SIT_MAP
from core.exporters import gerar_excel_preventivas
from units.brasilandia import config as CFG
from units.brasilandia.colaboradores import carregar_colaboradores
from units.brasilandia.motor import indicar_responsavel

bp = Blueprint("brasilandia", __name__, url_prefix="/api/brasilandia")

_CACHE_PREFIX = "br_"


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
            print(f"[BR preventivas] {idx}/{len(planos)} | {len(preventivas)} itens")

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
            "filterGroups": [{"combineOperator": "AND", "filters": filtros_planos(CFG.EMPRESA_ID, CFG.OFICINA_ID)}],
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
        } for _, r in colab.iterrows()]
        return jsonify({"total": len(itens), "itens": itens})
    except Exception as e:
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
