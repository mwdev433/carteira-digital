"""
Configuração central da aplicação.

Todas as informações sensíveis (senha do banco e chave do JWT) vêm de
variáveis de ambiente, nunca ficam escritas no código.

O docker-compose.yml já fornece valores padrão para desenvolvimento, então o
projeto sobe apenas com:

    docker compose down -v
    docker compose up --build -d

Em produção, defina JWT_SECRET e as senhas do MySQL em um arquivo .env
(veja .env.example).
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# Pasta do front-end estático servido pela própria API.
# No container: /app/frontend. Rodando localmente: <raiz do projeto>/frontend.
_PADRAO_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


class Settings(BaseSettings):
    # ------------------------------------------------------------------ #
    # Banco de dados MySQL
    # ------------------------------------------------------------------ #
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "carteira"
    db_password: str = "carteira"
    db_name: str = "carteira"

    # Permite usar outro banco (ex.: SQLite em testes locais).
    # Ex.: DATABASE_URL=sqlite:///./carteira.db
    database_url: str | None = None

    # ------------------------------------------------------------------ #
    # JWT
    # ------------------------------------------------------------------ #
    jwt_secret: str = "chave-de-desenvolvimento-troque-em-producao-000000"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ------------------------------------------------------------------ #
    # Regras de negócio
    # ------------------------------------------------------------------ #
    saldo_inicial: int = 1000
    # Janela de proteção contra transferências duplicadas (segundos).
    janela_duplicidade_segundos: int = 60

    # ------------------------------------------------------------------ #
    # Front-end e CORS
    # ------------------------------------------------------------------ #
    # A API serve o front-end na mesma origem, então o CORS é apenas um
    # reforço para acesso direto à porta 8080.
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"
    frontend_dir: str = str(_PADRAO_FRONTEND)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def url_banco(self) -> str:
        """URL de conexão usada pelo SQLAlchemy."""
        if self.database_url:
            return self.database_url
        # quote_plus permite senhas com caracteres especiais (@, #, etc.).
        return (
            f"mysql+pymysql://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origem.strip() for origem in self.cors_origins.split(",") if origem.strip()]


@lru_cache
def get_settings() -> Settings:
    """Mantém uma única instância das configurações durante toda a execução."""
    return Settings()


settings = get_settings()
