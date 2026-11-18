"""
Registro de auditoria.

A rota /auditoria é pública, por isso guardamos apenas informações não
sensíveis: evento, descrição e o usuário relacionado. Senhas, tokens e
saldos NÃO entram na auditoria.

A auditoria nunca derruba a API: falhas ao gravar o evento são apenas
registradas no log.
"""

import logging

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Auditoria

logger = logging.getLogger(__name__)


def registrar_evento(
    evento: str,
    usuario_id: int | None = None,
    descricao: str | None = None,
    db: Session | None = None,
) -> None:
    """
    Grava um evento de auditoria.

    Se `db` for informado, usa a transação em andamento (o commit fica com
    quem chamou). Caso contrário, abre uma sessão própria e confirma na hora,
    o que é útil em caminhos de erro.
    """
    registro = Auditoria(usuario_id=usuario_id, evento=evento, descricao=descricao)

    if db is not None:
        db.add(registro)
        return

    try:
        with SessionLocal() as sessao:
            sessao.add(registro)
            sessao.commit()
    except Exception as erro:  # noqa: BLE001 - auditoria nunca derruba a API
        logger.warning("Falha ao registrar auditoria: %s", erro)
