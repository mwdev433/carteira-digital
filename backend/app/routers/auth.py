"""
Rotas de cadastro e login.

POST /auth/registrar -> cria o usuário e a conta com 1000 moedas
POST /auth/login     -> confere a senha e devolve o token JWT
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import registrar_evento
from ..config import settings
from ..database import get_db
from ..errors import ApiError
from ..models import Conta, Usuario
from ..schemas import (
    LoginRequest,
    LoginResposta,
    RegistroRequest,
    RegistroResposta,
    UsuarioResposta,
)
from ..security import criar_token, hash_senha, verificar_senha

router = APIRouter(prefix="/auth", tags=["Autenticação"])

# Hash descartável usado quando o usuário não existe. Assim o tempo de
# resposta do login é parecido nos dois casos, dificultando descobrir
# quais nomes de usuário estão cadastrados.
_HASH_FALSO = hash_senha("senha-inexistente-apenas-para-tempo")


@router.post(
    "/registrar",
    response_model=RegistroResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um usuário e cria sua conta com 1000 moedas",
)
def registrar(dados: RegistroRequest, db: Session = Depends(get_db)):
    # 1) A confirmação de senha (quando enviada) precisa bater.
    if not dados.senhas_conferem():
        raise ApiError(422, "SENHAS_NAO_CONFEREM")

    username = dados.username.strip()

    # 2) Nome de usuário já existente? (comparação sem diferenciar maiúsculas)
    existente = (
        db.query(Usuario).filter(func.lower(Usuario.username) == username.lower()).one_or_none()
    )
    if existente is not None:
        registrar_evento("REGISTRO_NEGADO", existente.id, f"@{username} já cadastrado")
        raise ApiError(409, "USUARIO_EXISTENTE")

    # 3) Cria o usuário com a senha protegida e a conta com 1000 moedas.
    usuario = Usuario(username=username, senha_hash=hash_senha(dados.senha))
    usuario.conta = Conta(saldo=int(settings.saldo_inicial))
    db.add(usuario)

    try:
        db.flush()
        registrar_evento("REGISTRO", usuario.id, f"Conta {usuario.conta.id} criada", db=db)
        db.commit()
    except IntegrityError:
        # Proteção extra: se duas requisições chegarem ao mesmo tempo, a
        # restrição UNIQUE do banco garante que só uma será cadastrada.
        db.rollback()
        raise ApiError(409, "USUARIO_EXISTENTE")

    db.refresh(usuario)

    return RegistroResposta(
        username=usuario.username,
        conta_id=usuario.conta.id,
        saldo=int(usuario.conta.saldo),
        usuario=UsuarioResposta.model_validate(usuario),
    )


@router.post(
    "/login",
    response_model=LoginResposta,
    summary="Valida as credenciais e devolve o token JWT",
)
def login(dados: LoginRequest, db: Session = Depends(get_db)):
    username = dados.username.strip()
    usuario = (
        db.query(Usuario).filter(func.lower(Usuario.username) == username.lower()).one_or_none()
    )

    # Verifica a senha sempre com bcrypt. Se o usuário não existe, usamos um
    # hash falso só para manter o tempo de resposta parecido.
    if usuario is None:
        verificar_senha(dados.senha, _HASH_FALSO)
        registrar_evento("LOGIN_FALHA", None, f"Usuário inexistente: {username[:32]}")
        raise ApiError(401, "CREDENCIAIS_INVALIDAS")

    if not verificar_senha(dados.senha, usuario.senha_hash):
        registrar_evento("LOGIN_FALHA", usuario.id, "Senha incorreta")
        raise ApiError(401, "CREDENCIAIS_INVALIDAS")

    token, expira_em = criar_token(usuario.username, usuario.id)

    registrar_evento("LOGIN_OK", usuario.id, "Login realizado", db=db)
    db.commit()

    return LoginResposta(
        token=token,
        access_token=token,
        expira_em=expira_em,
        usuario=UsuarioResposta.model_validate(usuario),
    )
