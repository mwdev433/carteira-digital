"""
Rota pública de auditoria.

GET /auditoria devolve os totais calculados diretamente no banco:

    {"usuarios": 50, "somaSaldos": 50000, "transferencias": 1234}

Não exige token. Não expõe senhas, tokens nem dados individuais.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conta, Transferencia, Usuario
from ..schemas import AuditoriaResposta

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])


@router.get("", response_model=AuditoriaResposta, summary="Totais do sistema (público)")
def auditar(db: Session = Depends(get_db)):
    usuarios = db.query(func.count(Usuario.id)).scalar() or 0
    soma_saldos = db.query(func.coalesce(func.sum(Conta.saldo), 0)).scalar() or 0
    transferencias = db.query(func.count(Transferencia.id)).scalar() or 0

    return AuditoriaResposta(
        usuarios=int(usuarios),
        somaSaldos=int(soma_saldos),
        transferencias=int(transferencias),
    )
