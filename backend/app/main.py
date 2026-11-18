"""
Ponto de entrada da API (FastAPI).

A API e o front-end estático rodam no MESMO serviço/porta (8080), conforme o
contrato do projeto:

    http://localhost:8080/            -> front-end (index.html)
    http://localhost:8080/docs        -> documentação interativa
    http://localhost:8080/auth/login  -> API

Para rodar localmente:
    uvicorn app.main:app --reload --port 8080
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import models  # noqa: F401 - importa os modelos para criar as tabelas
from .config import settings
from .database import Base, engine, wait_for_database
from .errors import registrar_handlers
from .routers import auditoria, auth, conta, transferencias

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("carteira")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executado ao iniciar e ao encerrar a API."""
    # 1) Espera o MySQL ficar pronto (importante no docker compose).
    wait_for_database()
    # 2) Cria as tabelas que ainda não existem (idempotente).
    Base.metadata.create_all(bind=engine)
    logger.info("Banco de dados pronto. API iniciada na porta 8080.")
    yield
    logger.info("API encerrada.")


app = FastAPI(
    title="Carteira Digital — Autenticação e Segurança",
    description=(
        "API de cadastro, login e transferências com JWT e bcrypt.\n\n"
        "Rotas protegidas: /conta e /transferencias (token Bearer).\n"
        "Rota pública: /auditoria."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

registrar_handlers(app)

# Rotas da API (registradas ANTES do front-end estático).
app.include_router(auth.router)
app.include_router(conta.router)
app.include_router(transferencias.router)
app.include_router(auditoria.router)


@app.get("/health", tags=["Status"], summary="Verifica se a API e o banco estão no ar")
def health():
    from .errors import ApiError

    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception as erro:  # noqa: BLE001
        logger.error("Health check falhou: %s", erro)
        raise ApiError(503, "BANCO_INDISPONIVEL")

    return {"status": "ok", "banco": "conectado"}


# Front-end estático servido pela própria API (mesma origem, sem CORS).
frontend_dir = Path(settings.frontend_dir)
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:  # pragma: no cover - aviso útil em execução local sem a pasta
    logger.warning("Pasta do front-end não encontrada: %s", frontend_dir)
