"""
Funções de segurança: hash de senha (bcrypt) e token JWT.

  * A senha NUNCA é salva em texto puro: apenas o hash do bcrypt.
  * O bcrypt é lento de propósito: dificulta ataques de força bruta.
  * O token JWT é assinado com uma chave secreta vinda do ambiente.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


# ---------------------------------------------------------------------- #
# Senhas com bcrypt
# ---------------------------------------------------------------------- #
def hash_senha(senha: str) -> str:
    """Gera o hash bcrypt da senha para guardar no banco."""
    senha_bytes = senha.encode("utf-8")
    if len(senha_bytes) > 72:
        # O bcrypt só usa os primeiros 72 bytes; recusamos senhas maiores
        # para não dar a falsa impressão de que o restante é considerado.
        raise ValueError("A senha deve ter no máximo 72 bytes.")
    return bcrypt.hashpw(senha_bytes, bcrypt.gensalt(rounds=10)).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Compara a senha digitada com o hash salvo, sem expor a senha."""
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------- #
# Token JWT
# ---------------------------------------------------------------------- #
def criar_token(username: str, usuario_id: int, minutos: int | None = None) -> tuple[str, int]:
    """Cria um token JWT assinado. Retorna (token, expira_em_timestamp)."""
    validade = minutos if minutos is not None else settings.access_token_expire_minutes
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(minutes=validade)

    payload = {
        "sub": username,       # quem é o usuário
        "uid": usuario_id,     # id do usuário no banco
        "iat": int(agora.timestamp()),
        "exp": int(expira.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expira.timestamp())


def decodificar_token(token: str) -> dict | None:
    """Valida assinatura e expiração. Retorna o payload ou None."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
