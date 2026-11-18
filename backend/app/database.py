"""
Conexão com o banco de dados.

Em produção usamos MySQL 8 (driver PyMySQL). Para testes rápidos sem Docker,
basta definir DATABASE_URL=sqlite:///./carteira.db.

A conexão é criada uma vez e reaproveitada pelas requisições.
"""

import logging
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)

URL = settings.url_banco
EH_SQLITE = URL.startswith("sqlite")

if EH_SQLITE:
    engine = create_engine(
        URL,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _configurar_sqlite(conexao_dbapi, _registro):  # pragma: no cover - infra
        cursor = conexao_dbapi.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

else:
    # READ COMMITTED: leituras dentro da transação enxergam o que já foi
    # confirmado por outra transação. Isso é essencial para a checagem de
    # duplicidade depois de obter o bloqueio da conta de origem.
    engine = create_engine(
        URL,
        pool_pre_ping=True,
        pool_recycle=1800,
        isolation_level="READ COMMITTED",
        future=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


class Base(DeclarativeBase):
    """Classe base de todos os modelos (tabelas) do projeto."""


def get_db():
    """
    Dependência do FastAPI: entrega uma sessão do banco para a rota
    e garante que ela seja fechada no final, mesmo se der erro.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_database(max_tentativas: int = 40, espera_segundos: float = 2.0) -> None:
    """Aguarda o MySQL ficar disponível (útil no `docker compose up`)."""
    for tentativa in range(1, max_tentativas + 1):
        try:
            with engine.connect() as conexao:
                conexao.execute(text("SELECT 1"))
            logger.info("Conexão com o banco estabelecida.")
            return
        except Exception as erro:  # noqa: BLE001 - queremos tentar de novo
            logger.warning(
                "Banco ainda não disponível (tentativa %s/%s): %s",
                tentativa,
                max_tentativas,
                erro,
            )
            time.sleep(espera_segundos)

    raise RuntimeError("Não foi possível conectar ao banco. Verifique o docker compose e o .env.")
