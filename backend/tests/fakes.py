"""Fábricas de dados falsos no formato da API do Neovero (campos reais observados)."""
import pandas as pd


def colaboradores_df(linhas: list[dict]) -> pd.DataFrame:
    """DataFrame de colaboradores com todas as colunas que o motor/serviços esperam."""
    base = {"turno": "Diurno", "regime": "Fixo", "horario": "", "dias_plantao": {}, "status": "Ativo",
            "habilidades": [], "bloqueado": False, "aviso": None, "data_admissao": None, "data_desligamento": None,
            "fora_da_escala": False}
    df = pd.DataFrame([{**base, **l} for l in linhas])
    for col in ("aviso", "data_admissao", "data_desligamento"):
        df[col] = df[col].astype(object).where(df[col].notna(), None)
    return df


def os_neovero(numero, dia_iso, *, plano_id=1, plano="PM - MENSAL - SPLIT", tipo="PREVENTIVA", tipo_id=2, situacao=1,
               responsavel=None, responsavel_id=None, equip_id=10, equip="SPLIT 1", setor="BLOCO A", setor_id=5,
               oficina="CLIMATIZAÇÃO", hora="00:12", periodicidade=1, unidade_tempo="M", os_id=None, empresa_id=2):
    return {
        "id": os_id or int(numero), "numero": str(numero), "situacao": situacao,
        "dataHoraAbertura": f"{dia_iso}T{hora}:00.000000", "tipoManutencao": {"id": tipo_id, "descricao": tipo},
        "planoManutencaoId": plano_id,
        "planoManutencao": {"id": plano_id, "descricao": plano, "periodicidade": periodicidade,
                            "periodicidadeTempoUnidade": unidade_tempo, "oficina": {"descricao": oficina}},
        "oficina": {"descricao": oficina}, "equipamentoId": equip_id, "equipamento": {"id": equip_id, "nome": equip},
        "setorId": setor_id, "setor": {"id": setor_id, "nome": setor},
        "responsavelId": responsavel_id, "responsavel": ({"id": responsavel_id, "nome": responsavel} if responsavel else None),
        "empresa": {"id": empresa_id},
    }


def plano_neovero(plano_id, descricao, *, oficina="CLIMATIZAÇÃO", periodicidade=1, unidade="M", tipo_id=2):
    return {"id": plano_id, "descricao": descricao, "tipoManutencao": {"id": tipo_id, "descricao": descricao},
            "oficina": {"descricao": oficina}, "periodicidade": periodicidade, "periodicidadeTempoUnidade": unidade,
            "ativo": True, "procedimento": {"nome": "PROC"}}


def item_plano(item_id, dia_iso, *, equip_id=10, equip="SPLIT 1", setor="BLOCO A", setor_id=5, os_ligada=None):
    return {"id": item_id, "dataProximaPreventiva": f"{dia_iso}T00:00:00.000000", "equipamentoId": equip_id,
            "equipamento": {"id": equip_id, "nome": equip, "setorAtual": {"id": setor_id, "nome": setor}},
            "setor": {"id": setor_id, "nome": setor}, "ordemServico": os_ligada or {}}
