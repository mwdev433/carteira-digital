"""
Contratos de entrada e saída da API (schemas do Pydantic).

Os schemas de resposta seguem exatamente os nomes de campo do contrato do
projeto. Erros usam sempre {"error": "CODIGO"}.
"""

from datetime import datetime
from typing import Annotated

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------- #
# Regras de usuário e senha
# ---------------------------------------------------------------------- #
USERNAME_PATTERN = r"^[A-Za-z0-9._-]{3,32}$"

Username = Annotated[
    str,
    Field(
        min_length=3,
        max_length=32,
        pattern=USERNAME_PATTERN,
        validation_alias=AliasChoices("username", "usuario", "nome"),
        examples=["joao"],
    ),
]

# O bcrypt só considera os primeiros 72 bytes da senha.
Senha = Annotated[
    str,
    Field(
        min_length=1,
        max_length=72,
        validation_alias=AliasChoices("senha", "password"),
        examples=["senha123"],
    ),
]


def _validar_tamanho_em_bytes(senha: str) -> str:
    if len(senha.encode("utf-8")) > 72:
        raise ValueError("A senha deve ter no máximo 72 bytes.")
    return senha


# ---------------------------------------------------------------------- #
# Autenticação
# ---------------------------------------------------------------------- #
class RegistroRequest(BaseModel):
    username: Username
    senha: Senha
    # Campo opcional: se o cliente enviar, é apenas conferido.
    confirmacao_senha: str | None = Field(
        default=None,
        validation_alias=AliasChoices("confirmacao_senha", "confirmar_senha", "confirmacao"),
    )

    @field_validator("senha")
    @classmethod
    def senha_valida(cls, valor: str) -> str:
        return _validar_tamanho_em_bytes(valor)

    def senhas_conferem(self) -> bool:
        if self.confirmacao_senha is None:
            return True
        return self.confirmacao_senha == self.senha


class LoginRequest(BaseModel):
    # Sem validação de formato: credenciais erradas devem devolver
    # 401 CREDENCIAIS_INVALIDAS, e não um erro de validação.
    username: str = Field(validation_alias=AliasChoices("username", "usuario", "nome"))
    senha: str = Field(validation_alias=AliasChoices("senha", "password"))


class UsuarioResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class RegistroResposta(BaseModel):
    username: str
    conta_id: int
    saldo: int
    usuario: UsuarioResposta


class LoginResposta(BaseModel):
    # `token` é o nome exigido pelo contrato; `access_token` é o alias
    # padrão OAuth2, mantido para compatibilidade com clientes genéricos.
    token: str
    access_token: str
    token_type: str = "bearer"
    expira_em: int
    usuario: UsuarioResposta


# ---------------------------------------------------------------------- #
# Conta
# ---------------------------------------------------------------------- #
class ContaResposta(BaseModel):
    username: str
    saldo: int
    conta_id: int


# ---------------------------------------------------------------------- #
# Transferências
# ---------------------------------------------------------------------- #
class TransferenciaResposta(BaseModel):
    id: int
    origem: str
    destino: str
    valor: int
    saldo: int


class ExtratoItem(BaseModel):
    id: int
    direcao: str  # ENVIADA ou RECEBIDA
    origem: str
    destino: str
    valor: int
    criada_em: datetime


class ExtratoResposta(BaseModel):
    conta_id: int
    saldo: int
    total: int
    transferencias: list[ExtratoItem]


# ---------------------------------------------------------------------- #
# Auditoria (rota pública)
# ---------------------------------------------------------------------- #
class AuditoriaResposta(BaseModel):
    usuarios: int
    somaSaldos: int  # noqa: N815 - nome exigido pelo contrato
    transferencias: int
