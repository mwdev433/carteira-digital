"""
Erros padronizados da API.

Toda rejeição de negócio tem EXATAMENTE este formato:

    {"error": "CODIGO_DO_ERRO"}

Nenhum campo extra é enviado, pois o contrato do projeto exige a grafia
exata do código.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Erro de negócio com código estável."""

    def __init__(self, status_code: int, error: str, headers: dict | None = None):
        super().__init__(error)
        self.status_code = status_code
        self.error = error
        self.headers = headers or {}


def _resposta(status_code: int, error: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


def registrar_handlers(app: FastAPI) -> None:
    """Liga os tratadores de erro personalizados à aplicação."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _resposta(exc.status_code, exc.error, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError):
        # No POST /transferencias qualquer corpo inválido é um valor inválido
        # (o contrato só prevê 422 VALOR_INVALIDO para esse endpoint).
        if request.url.path.rstrip("/").endswith("/transferencias"):
            return _resposta(422, "VALOR_INVALIDO")

        if any("password" in str(erro.get("loc", ())) or "senha" in str(erro.get("loc", ()))
               for erro in exc.errors()):
            return _resposta(422, "DADOS_INVALIDOS")

        return _resposta(422, "DADOS_INVALIDOS")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        # Mantém o padrão {"error": ...} também para rotas inexistentes.
        codigos = {404: "NAO_ENCONTRADO", 405: "METODO_NAO_PERMITIDO"}
        codigo = codigos.get(exc.status_code, "ERRO_HTTP")
        return _resposta(exc.status_code, codigo, getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _erro_inesperado(_: Request, exc: Exception):
        # Nunca devolvemos detalhes internos (stack trace) para o cliente.
        logger.exception("Erro inesperado: %s", exc)
        return _resposta(500, "ERRO_INTERNO")
