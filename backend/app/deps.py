"""
Dependências de autenticação.

A identidade do usuário vem SEMPRE do token JWT, nunca de campos enviados
pelo frontend (como um nome de usuário no corpo da requisição).
"""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .errors import ApiError
from .models import Conta, Usuario
from .security import decodificar_token

# auto_error=False: assim nós mesmos montamos a resposta 401 padronizada.
_bearer = HTTPBearer(auto_error=False)


def _nao_autenticado() -> ApiError:
    # Corpo exatamente {"error": "NAO_AUTENTICADO"}.
    return ApiError(401, "NAO_AUTENTICADO", headers={"WWW-Authenticate": "Bearer"})


def get_usuario_atual(
    request: Request,
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Lê o token do cabeçalho `Authorization: Bearer <token>` e devolve o
    usuário dono do token.

    Recusa com 401 NAO_AUTENTICADO:
      * requisição sem token;
      * token com assinatura inválida ou formato errado;
      * token expirado;
      * token válido, mas de um usuário que não existe mais.
    """
    if credenciais is None or not credenciais.credentials:
        raise _nao_autenticado()

    payload = decodificar_token(credenciais.credentials)
    if payload is None:
        raise _nao_autenticado()

    username = payload.get("sub")
    usuario_id = payload.get("uid")
    if not isinstance(username, str) or not isinstance(usuario_id, int):
        raise _nao_autenticado()

    usuario = db.get(Usuario, usuario_id)
    if usuario is None or usuario.username != username:
        raise _nao_autenticado()

    request.state.usuario = usuario
    return usuario


def get_conta_do_usuario(
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> tuple[Usuario, Conta]:
    """Devolve o usuário autenticado e a conta que pertence a ele."""
    conta = db.query(Conta).filter(Conta.usuario_id == usuario.id).one_or_none()
    if conta is None:
        raise ApiError(404, "CONTA_NAO_ENCONTRADA")
    return usuario, conta
