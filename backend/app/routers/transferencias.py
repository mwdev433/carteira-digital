"""
Rotas de transferência.

POST /transferencias -> transfere moedas para outro usuário
GET  /transferencias -> histórico do próprio usuário

SEGURANÇA: a conta de origem é SEMPRE a conta do usuário autenticado pelo
token. Se o cliente enviar "origem" no corpo, o campo é ignorado.

CONCORRÊNCIA E ATOMICIDADE:
  * as duas contas são travadas com SELECT ... FOR UPDATE, sempre na ordem
    do id (evita deadlock entre A->B e B->A);
  * a checagem de duplicidade, a checagem de saldo, o débito, o crédito e o
    registro da transferência acontecem na MESMA transação;
  * qualquer falha faz rollback completo: nunca existe débito sem crédito;
  * o bloqueio da conta de origem serializa transferências da mesma origem,
    garantindo que duas requisições idênticas simultâneas resultem em
    exatamente uma transferência efetivada;
  * deadlocks do MySQL são repetidos automaticamente (poucas tentativas).
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy import func, or_
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from ..audit import registrar_evento
from ..config import settings
from ..database import get_db
from ..deps import get_usuario_atual
from ..errors import ApiError
from ..locks import travar_contas
from ..models import Conta, Transferencia, Usuario
from ..schemas import ExtratoItem, ExtratoResposta, TransferenciaResposta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transferencias", tags=["Transferências"])

_MAX_TENTATIVAS = 5


def _extrair_valor(payload: dict) -> int:
    """Valida o campo `valor`: precisa ser número inteiro e maior que zero."""
    if not isinstance(payload, dict) or "valor" not in payload:
        raise ApiError(422, "VALOR_INVALIDO")

    valor = payload["valor"]

    # bool é subclasse de int em Python: recusamos True/False explicitamente.
    if isinstance(valor, bool) or valor is None:
        raise ApiError(422, "VALOR_INVALIDO")

    # Texto como "150" é inválido, conforme o contrato.
    if isinstance(valor, str):
        raise ApiError(422, "VALOR_INVALIDO")

    if isinstance(valor, float):
        # 150.0 é aceito como 150; 150.5 (ou NaN/inf) é inválido.
        if not valor.is_integer():
            raise ApiError(422, "VALOR_INVALIDO")
    elif not isinstance(valor, int):
        raise ApiError(422, "VALOR_INVALIDO")

    valor = int(valor)
    if valor <= 0:
        raise ApiError(422, "VALOR_INVALIDO")

    return valor


def _extrair_destino(payload: dict) -> str:
    """Valida o campo `destino`: precisa ser um nome de usuário em texto."""
    destino = payload.get("destino") if isinstance(payload, dict) else None
    if not isinstance(destino, str) or not destino.strip():
        # Destino em branco/ausente não é um usuário cadastrado.
        raise ApiError(404, "DESTINO_INEXISTENTE")
    return destino.strip()


def _eh_deadlock(erro: OperationalError) -> bool:
    codigo = getattr(getattr(erro, "orig", None), "args", [None])[0]
    return codigo in (1213, 1205)


@router.post(
    "",
    response_model=TransferenciaResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Transfere moedas para outro usuário (autenticado)",
)
def transferir(
    payload: dict = Body(default={}),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
):
    # 1) Validações de entrada (antes de qualquer acesso ao banco).
    valor = _extrair_valor(payload)
    destino_nome = _extrair_destino(payload)

    # 2) Origem: sempre a conta do usuário do token.
    conta_origem = db.query(Conta).filter(Conta.usuario_id == usuario.id).one_or_none()
    if conta_origem is None:
        raise ApiError(404, "CONTA_NAO_ENCONTRADA")

    # 3) Destino precisa existir.
    destino_usuario = (
        db.query(Usuario)
        .filter(func.lower(Usuario.username) == destino_nome.lower())
        .one_or_none()
    )
    if destino_usuario is None or destino_usuario.conta is None:
        raise ApiError(404, "DESTINO_INEXISTENTE")

    # 4) Não pode transferir para si mesmo.
    if destino_usuario.id == usuario.id or destino_usuario.conta.id == conta_origem.id:
        raise ApiError(422, "MESMA_CONTA")

    ids_contas = sorted([conta_origem.id, destino_usuario.conta.id])
    limite_duplicidade = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=settings.janela_duplicidade_segundos
    )

    # Bloqueio em memória (defesa em profundidade, sem deadlock).
    with travar_contas(ids_contas):
        for tentativa in range(1, _MAX_TENTATIVAS + 1):
            try:
                # 5) Trava as DUAS contas em ordem determinística de id.
                contas = (
                    db.query(Conta)
                    .filter(Conta.id.in_(ids_contas))
                    .order_by(Conta.id)
                    .with_for_update()
                    .all()
                )
                por_id = {conta.id: conta for conta in contas}
                if len(por_id) != 2:
                    raise ApiError(404, "CONTA_NAO_ENCONTRADA")

                origem = por_id[conta_origem.id]
                destino = por_id[destino_usuario.conta.id]

                # 6) Duplicidade: mesma origem + destino + valor nos últimos 60 s.
                #    A leitura FOR UPDATE enxerga o que foi confirmado por outra
                #    transação, mesmo com o snapshot do READ COMMITTED.
                #    Esta checagem vem ANTES da checagem de saldo, como exige o
                #    contrato.
                duplicada = (
                    db.query(Transferencia.id)
                    .filter(
                        Transferencia.origem_conta_id == origem.id,
                        Transferencia.destino_conta_id == destino.id,
                        Transferencia.valor == valor,
                        Transferencia.criada_em >= limite_duplicidade,
                    )
                    .order_by(Transferencia.id.desc())
                    .with_for_update()
                    .first()
                )
                if duplicada is not None:
                    raise ApiError(409, "TRANSFERENCIA_DUPLICADA")

                # 7) Saldo suficiente?
                if int(origem.saldo) < valor:
                    raise ApiError(409, "SALDO_INSUFICIENTE")

                # 8) Débito + crédito + registro na MESMA transação.
                origem.saldo = int(origem.saldo) - valor
                destino.saldo = int(destino.saldo) + valor

                transferencia = Transferencia(
                    origem_conta_id=origem.id,
                    destino_conta_id=destino.id,
                    valor=valor,
                )
                db.add(transferencia)
                db.flush()  # garante o id antes do commit

                registrar_evento(
                    "TRANSFERENCIA",
                    usuario.id,
                    f"Para @{destino_usuario.username}: {valor}",
                    db=db,
                )
                db.commit()

                novo_saldo = int(origem.saldo)
                break

            except ApiError:
                db.rollback()
                raise
            except OperationalError as erro:
                db.rollback()
                if _eh_deadlock(erro) and tentativa < _MAX_TENTATIVAS:
                    logger.warning(
                        "Deadlock na transferência (tentativa %s), repetindo.", tentativa
                    )
                    time.sleep(0.05 * tentativa)
                    continue
                logger.exception("Erro de banco na transferência")
                raise ApiError(500, "ERRO_INTERNO")
            except SQLAlchemyError:
                db.rollback()
                logger.exception("Erro de banco na transferência")
                raise ApiError(500, "ERRO_INTERNO")
        else:  # pragma: no cover - todas as tentativas falharam por deadlock
            db.rollback()
            raise ApiError(500, "ERRO_INTERNO")

    return TransferenciaResposta(
        id=transferencia.id,
        origem=usuario.username,
        destino=destino_usuario.username,
        valor=valor,
        saldo=novo_saldo,
    )


@router.get(
    "",
    response_model=ExtratoResposta,
    summary="Histórico de transferências do usuário (autenticado)",
)
def extrato(
    limite: int = Query(default=20, ge=1, le=100),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
):
    conta = db.query(Conta).filter(Conta.usuario_id == usuario.id).one_or_none()
    if conta is None:
        raise ApiError(404, "CONTA_NAO_ENCONTRADA")

    conta_origem_alias = aliased(Conta)
    conta_destino_alias = aliased(Conta)
    usuario_origem_alias = aliased(Usuario)
    usuario_destino_alias = aliased(Usuario)

    linhas = (
        db.query(Transferencia, usuario_origem_alias.username, usuario_destino_alias.username)
        .join(conta_origem_alias, Transferencia.origem_conta_id == conta_origem_alias.id)
        .join(usuario_origem_alias, conta_origem_alias.usuario_id == usuario_origem_alias.id)
        .join(conta_destino_alias, Transferencia.destino_conta_id == conta_destino_alias.id)
        .join(usuario_destino_alias, conta_destino_alias.usuario_id == usuario_destino_alias.id)
        .filter(
            or_(
                Transferencia.origem_conta_id == conta.id,
                Transferencia.destino_conta_id == conta.id,
            )
        )
        .order_by(Transferencia.criada_em.desc(), Transferencia.id.desc())
        .limit(limite)
        .all()
    )

    itens = []
    for transferencia, nome_origem, nome_destino in linhas:
        enviada = transferencia.origem_conta_id == conta.id
        itens.append(
            ExtratoItem(
                id=transferencia.id,
                direcao="ENVIADA" if enviada else "RECEBIDA",
                origem=nome_origem,
                destino=nome_destino,
                valor=int(transferencia.valor),
                criada_em=transferencia.criada_em,
            )
        )

    return ExtratoResposta(
        conta_id=conta.id,
        saldo=int(conta.saldo),
        total=len(itens),
        transferencias=itens,
    )
