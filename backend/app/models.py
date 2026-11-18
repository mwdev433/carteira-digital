"""
Modelos (tabelas) do banco de dados.

  usuarios       -> login e senha protegida com bcrypt
  contas         -> saldo em moedas inteiras (1 conta por usuário)
  transferencias -> histórico de transferências efetivadas
  auditoria      -> registro de eventos (rota pública /auditoria)

Os valores monetários são INTEGER: o projeto trabalha com moedas inteiras.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # unique=True impede dois usuários com o mesmo nome.
    # No MySQL a collation utf8mb4_0900_ai_ci não diferencia maiúsculas,
    # então "Joao" e "joao" também são considerados iguais.
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    # NUNCA guardamos a senha em texto puro: apenas o hash gerado pelo bcrypt.
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    conta: Mapped["Conta"] = relationship(back_populates="usuario", uselist=False)


class Conta(Base):
    __tablename__ = "contas"
    __table_args__ = (
        CheckConstraint("saldo >= 0", name="ck_contas_saldo_nao_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Uma conta por usuário: UNIQUE garante isso no próprio banco.
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    saldo: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1000)
    criada_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    usuario: Mapped[Usuario] = relationship(back_populates="conta")


class Transferencia(Base):
    __tablename__ = "transferencias"
    __table_args__ = (
        CheckConstraint("valor > 0", name="ck_transferencias_valor_positivo"),
        # Índice que acelera a checagem de duplicidade (origem, destino, valor, data).
        Index(
            "ix_transferencias_duplicidade",
            "origem_conta_id",
            "destino_conta_id",
            "valor",
            "criada_em",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    origem_conta_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id"), nullable=False, index=True
    )
    destino_conta_id: Mapped[int] = mapped_column(
        ForeignKey("contas.id"), nullable=False, index=True
    )
    valor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Pode ser nulo em eventos de sistema (ex.: falha de login de usuário inexistente).
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Ex.: REGISTRO, LOGIN_OK, LOGIN_FALHA, TRANSFERENCIA, ACESSO_NEGADO
    evento: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    usuario: Mapped[Usuario | None] = relationship()
