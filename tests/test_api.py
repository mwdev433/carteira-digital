"""
Testes automatizados da Carteira Digital.

Rodam contra o MESMO banco configurado para a API. Dentro do Docker:

    docker compose exec api python -m pytest tests -v

Também é possível rodar localmente com SQLite:

    DATABASE_URL=sqlite:///./teste.db JWT_SECRET=teste \
        python -m pytest tests -v
"""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "carteira")
os.environ.setdefault("DB_PASSWORD", "carteira")
os.environ.setdefault("DB_NAME", "carteira")
os.environ.setdefault("JWT_SECRET", "chave-de-teste-automatizado-com-mais-de-32-bytes")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, text  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import EH_SQLITE, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Auditoria, Conta, Transferencia, Usuario  # noqa: E402

SUFIXO = "t" + uuid.uuid4().hex[:8]
SENHA = "senha-segura-123"
VALOR_INICIAL = 1000


def nome(base: str) -> str:
    return f"{SUFIXO}_{base}"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as cliente:
        yield cliente


def criar_usuario(client, username: str) -> str:
    resposta = client.post(
        "/auth/registrar", json={"username": username, "password": SENHA}
    )
    assert resposta.status_code == 201, resposta.text
    login = client.post("/auth/login", json={"username": username, "password": SENHA})
    assert login.status_code == 200, login.text
    return login.json()["token"]


@pytest.fixture(scope="module")
def usuarios(client):
    dados = {}
    for base in ("alice", "bob", "carol", "dave", "erin", "frank"):
        username = nome(base)
        dados[base] = username
        dados["token_" + base] = criar_usuario(client, username)
    return dados


def saldo_de(client, token: str) -> int:
    resposta = client.get("/conta", headers=auth(token))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["saldo"]


def transferir(client, token: str, destino: str, valor):
    return client.post(
        "/transferencias", headers=auth(token), json={"destino": destino, "valor": valor}
    )


# ---------------------------------------------------------------------- #
# 1-4. Cadastro e login
# ---------------------------------------------------------------------- #
def test_01_cadastro_cria_conta_com_mil_moedas(client):
    username = nome("novo")
    resposta = client.post("/auth/registrar", json={"username": username, "password": SENHA})
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["username"] == username
    assert corpo["saldo"] == VALOR_INICIAL

    token = client.post(
        "/auth/login", json={"username": username, "password": SENHA}
    ).json()["token"]
    assert saldo_de(client, token) == VALOR_INICIAL


def test_02_cadastro_duplicado_retorna_409(client, usuarios):
    resposta = client.post(
        "/auth/registrar", json={"username": usuarios["alice"], "password": SENHA}
    )
    assert resposta.status_code == 409
    assert resposta.json() == {"error": "USUARIO_EXISTENTE"}


def test_03_login_valido_devolve_token(client, usuarios):
    resposta = client.post(
        "/auth/login", json={"username": usuarios["alice"], "password": SENHA}
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["token"]
    assert corpo["token"] == corpo["access_token"]


def test_04_login_invalido_retorna_401(client, usuarios):
    errado = client.post(
        "/auth/login", json={"username": usuarios["alice"], "password": "senha-errada"}
    )
    assert errado.status_code == 401
    assert errado.json() == {"error": "CREDENCIAIS_INVALIDAS"}

    inexistente = client.post(
        "/auth/login", json={"username": nome("fantasma"), "password": SENHA}
    )
    assert inexistente.status_code == 401
    assert inexistente.json() == {"error": "CREDENCIAIS_INVALIDAS"}


# ---------------------------------------------------------------------- #
# 5-7. Autenticação e conta
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize("rota", ["/conta", "/transferencias"])
def test_05_acesso_sem_token_retorna_401(client, rota):
    resposta = client.get(rota) if rota == "/conta" else client.post(
        rota, json={"destino": "qualquer", "valor": 1}
    )
    assert resposta.status_code == 401
    assert resposta.json() == {"error": "NAO_AUTENTICADO"}


@pytest.mark.parametrize(
    "cabecalho",
    [
        {"Authorization": "Bearer token-invalido"},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer "},
    ],
)
def test_06_token_invalido_retorna_401(client, cabecalho):
    resposta = client.get("/conta", headers=cabecalho)
    print(resposta.text)
    assert resposta.status_code == 401
    assert resposta.json() == {"error": "NAO_AUTENTICADO"}


def test_07_consulta_saldo(client, usuarios):
    resposta = client.get("/conta", headers=auth(usuarios["token_alice"]))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["username"] == usuarios["alice"]
    assert corpo["saldo"] == VALOR_INICIAL


def test_07b_nao_le_conta_de_outro_usuario(client, usuarios):
    # A rota ignora qualquer parâmetro: a identidade vem só do token.
    resposta = client.get(
        f"/conta?username={usuarios['bob']}", headers=auth(usuarios["token_alice"])
    )
    assert resposta.status_code == 200
    assert resposta.json()["username"] == usuarios["alice"]
    assert resposta.json()["saldo"] == VALOR_INICIAL


# ---------------------------------------------------------------------- #
# 8-13. Transferências
# ---------------------------------------------------------------------- #
def test_08_transferencia_valida(client, usuarios):
    resposta = transferir(client, usuarios["token_alice"], usuarios["bob"], 150)
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["origem"] == usuarios["alice"]
    assert corpo["destino"] == usuarios["bob"]
    assert corpo["valor"] == 150
    assert corpo["saldo"] == VALOR_INICIAL - 150
    assert isinstance(corpo["id"], int)

    assert saldo_de(client, usuarios["token_alice"]) == VALOR_INICIAL - 150
    assert saldo_de(client, usuarios["token_bob"]) == VALOR_INICIAL + 150


def test_09_transferencia_para_si_mesmo(client, usuarios):
    resposta = transferir(client, usuarios["token_alice"], usuarios["alice"], 10)
    assert resposta.status_code == 422
    assert resposta.json() == {"error": "MESMA_CONTA"}


def test_10_destino_inexistente(client, usuarios):
    resposta = transferir(client, usuarios["token_alice"], nome("naoexiste"), 10)
    assert resposta.status_code == 404
    assert resposta.json() == {"error": "DESTINO_INEXISTENTE"}


@pytest.mark.parametrize(
    "corpo",
    [
        {"destino": "fulano"},
        {"destino": "fulano", "valor": "150"},
        {"destino": "fulano", "valor": 0},
        {"destino": "fulano", "valor": -5},
        {"destino": "fulano", "valor": 10.5},
        {"destino": "fulano", "valor": None},
        {"destino": "fulano", "valor": True},
    ],
)
def test_11_valor_invalido(client, usuarios, corpo):
    resposta = client.post(
        "/transferencias", headers=auth(usuarios["token_alice"]), json=corpo
    )
    assert resposta.status_code == 422, resposta.text
    assert resposta.json() == {"error": "VALOR_INVALIDO"}


def test_12_saldo_insuficiente(client, usuarios):
    # carol tem 1000; tenta enviar 1001 (valor único, sem duplicidade).
    resposta = transferir(client, usuarios["token_carol"], usuarios["dave"], 1001)
    assert resposta.status_code == 409
    assert resposta.json() == {"error": "SALDO_INSUFICIENTE"}
    assert saldo_de(client, usuarios["token_carol"]) == VALOR_INICIAL


def test_13_transferencia_duplicada_em_menos_de_60s(client, usuarios):
    primeira = transferir(client, usuarios["token_dave"], usuarios["carol"], 222)
    assert primeira.status_code == 201, primeira.text

    segunda = transferir(client, usuarios["token_dave"], usuarios["carol"], 222)
    assert segunda.status_code == 409
    assert segunda.json() == {"error": "TRANSFERENCIA_DUPLICADA"}


def test_13b_duplicidade_antes_de_saldo_insuficiente(client):
    # Usuário dedicado: envia 999 (sobra 1) e tenta repetir.
    origem = criar_usuario(client, nome("dupsaldo"))
    destino = nome("dupsaldodestino")
    criar_usuario(client, destino)

    assert transferir(client, origem, destino, 999).status_code == 201
    repetida = transferir(client, origem, destino, 999)
    assert repetida.status_code == 409
    assert repetida.json() == {"error": "TRANSFERENCIA_DUPLICADA"}


def test_13c_janela_de_60s_expira(client):
    origem = criar_usuario(client, nome("janela"))
    destino = nome("janeladestino")
    criar_usuario(client, destino)

    assert transferir(client, origem, destino, 77).status_code == 201

    # Move a transferência para 61 segundos atrás.
    username_origem = client.get("/conta", headers=auth(origem)).json()["username"]
    with SessionLocal() as sessao:
        usuario_origem = sessao.query(Usuario).filter(Usuario.username == username_origem).one()
        conta_origem = sessao.query(Conta).filter(Conta.usuario_id == usuario_origem.id).one()
        transferencia = (
            sessao.query(Transferencia)
            .filter(Transferencia.origem_conta_id == conta_origem.id)
            .order_by(Transferencia.id.desc())
            .first()
        )
        transferencia.criada_em = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=61)
        sessao.commit()

    assert transferir(client, origem, destino, 77).status_code == 201


def test_13d_mesmo_valor_para_destino_diferente_e_permitido(client, usuarios):
    assert transferir(client, usuarios["token_erin"], usuarios["bob"], 31).status_code == 201
    assert transferir(client, usuarios["token_erin"], usuarios["carol"], 31).status_code == 201


# ---------------------------------------------------------------------- #
# 14-15. Concorrência
# ---------------------------------------------------------------------- #
@pytest.mark.skipif(EH_SQLITE, reason="Bloqueios SELECT FOR UPDATE exigem MySQL")
def test_14_transferencias_simultaneas_de_contas_diferentes(client):
    # 8 remetentes novos transferem ao mesmo tempo para o mesmo destino.
    destino = nome("central")
    criar_usuario(client, destino)

    remetentes = []
    for i in range(8):
        remetentes.append(criar_usuario(client, nome(f"conc{i}")))

    with ThreadPoolExecutor(max_workers=8) as executor:
        respostas = list(
            executor.map(lambda token: transferir(client, token, destino, 100), remetentes)
        )

    assert all(r.status_code == 201 for r in respostas), [r.text for r in respostas]
    assert all(r.json()["valor"] == 100 for r in respostas)

    auditoria = client.get("/auditoria").json()
    assert auditoria["somaSaldos"] == VALOR_INICIAL * auditoria["usuarios"]


@pytest.mark.skipif(EH_SQLITE, reason="Bloqueios SELECT FOR UPDATE exigem MySQL")
def test_15_duas_transferencias_identicas_simultaneas(client):
    origem = criar_usuario(client, nome("simorigem"))
    destino = nome("simdestino")
    criar_usuario(client, destino)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futuros = [
            executor.submit(transferir, client, origem, destino, 250) for _ in range(10)
        ]
    respostas = [f.result() for f in futuros]

    sucessos = [r for r in respostas if r.status_code == 201]
    recusas = [r for r in respostas if r.status_code == 409]
    assert len(sucessos) == 1, [r.text for r in respostas]
    assert len(recusas) == 9
    assert all(r.json() == {"error": "TRANSFERENCIA_DUPLICADA"} for r in recusas)

    with SessionLocal() as sessao:
        conta = (
            sessao.query(Conta)
            .join(Usuario, Usuario.id == Conta.usuario_id)
            .filter(Usuario.username == origem)
            .one()
        )
        assert conta.saldo == VALOR_INICIAL - 250


# ---------------------------------------------------------------------- #
# 16. Integridade / auditoria
# ---------------------------------------------------------------------- #
def test_16_auditoria_publica_e_soma_dos_saldos(client):
    resposta = client.get("/auditoria")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert set(dados) == {"usuarios", "somaSaldos", "transferencias"}
    assert dados["somaSaldos"] == VALOR_INICIAL * dados["usuarios"]
    assert dados["usuarios"] >= 6
    assert dados["transferencias"] >= 1

    with SessionLocal() as sessao:
        soma = sessao.query(func.coalesce(func.sum(Conta.saldo), 0)).scalar()
        assert int(soma) == dados["somaSaldos"]


# ---------------------------------------------------------------------- #
# 17. Persistência
# ---------------------------------------------------------------------- #
def test_17_dados_persistidos_no_banco(client, usuarios):
    # Consulta por uma conexão nova, sem cache da sessão da API.
    with SessionLocal() as sessao:
        usuario = sessao.query(Usuario).filter(Usuario.username == usuarios["alice"]).one()
        conta = sessao.query(Conta).filter(Conta.usuario_id == usuario.id).one()
        assert conta.saldo == saldo_de(client, usuarios["token_alice"])
        assert sessao.execute(text("SELECT 1")).scalar() == 1


# ---------------------------------------------------------------------- #
# 18. Atomicidade em caso de falha
# ---------------------------------------------------------------------- #
def test_18_atomicidade_em_caso_de_falha(client, usuarios, monkeypatch):
    saldo_antes = saldo_de(client, usuarios["token_frank"])

    def commit_com_falha(self):
        raise SQLAlchemyError("falha simulada antes do commit")

    monkeypatch.setattr(Session, "commit", commit_com_falha)
    resposta = transferir(client, usuarios["token_frank"], usuarios["bob"], 42)
    monkeypatch.undo()

    assert resposta.status_code == 500
    assert resposta.json() == {"error": "ERRO_INTERNO"}

    # Nada foi movimentado: débito e crédito são da mesma transação.
    assert saldo_de(client, usuarios["token_frank"]) == saldo_antes
    with SessionLocal() as sessao:
        origem = sessao.query(Usuario).filter(Usuario.username == usuarios["frank"]).one()
        conta = sessao.query(Conta).filter(Conta.usuario_id == origem.id).one()
        assert conta.saldo == saldo_antes


# ---------------------------------------------------------------------- #
# Extras: front-end servido e hash de senha
# ---------------------------------------------------------------------- #
def test_19_frontend_servido_na_mesma_porta(client):
    resposta = client.get("/")
    assert resposta.status_code == 200
    assert "Carteira Digital" in resposta.text


def test_20_senha_armazenada_com_bcrypt(client, usuarios):
    with SessionLocal() as sessao:
        usuario = sessao.query(Usuario).filter(Usuario.username == usuarios["alice"]).one()
        assert usuario.senha_hash != SENHA
        assert usuario.senha_hash.startswith("$2")

        evento = sessao.query(Auditoria).filter(Auditoria.evento == "LOGIN_OK").first()
        assert evento is not None
