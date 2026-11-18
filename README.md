# Carteira Digital — Sistema de Transferências

API de carteira digital com autenticação JWT, senhas bcrypt, transferências
atômicas e proteção real contra duplicidade. O front-end original (tema escuro,
roxo/azul, Inter) foi preservado e é servido **pela própria API** na mesma
origem, em `http://localhost:8080`.

Stack: **FastAPI + SQLAlchemy + MySQL 8 + JWT + bcrypt + Docker Compose**.
Valores monetários são **inteiros** (moedas).

---

## 1. Como executar

Pré-requisito: Docker com Compose.

```bash
docker compose down -v
docker compose up --build -d
```

Aguarde o MySQL ficar saudável (o `api` só inicia depois disso) e abra:

- Aplicação: http://localhost:8080
- Documentação interativa: http://localhost:8080/docs
- Health check: http://localhost:8080/health

Não é obrigatório criar `.env`: o `docker-compose.yml` já traz valores padrão
de desenvolvimento. Para trocar senhas/chave JWT:

```bash
cp .env.example .env
# edite .env e rode novamente: docker compose up --build -d
```

### Persistência

Os dados ficam no volume nomeado `mysql-data`. Eles sobrevivem a
`docker compose restart`, `docker compose down` e ao rebuild. Apenas
`docker compose down -v` remove o volume (começo limpo).

```bash
docker compose restart        # dados preservados
docker compose down           # dados preservados
docker compose down -v        # apaga o banco (reset)
```

---

## 2. Estrutura do projeto

```
carteira-digital/
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   │   ├── auth.py            # /auth/registrar, /auth/login
│   │   │   ├── conta.py           # /conta
│   │   │   ├── transferencias.py  # POST/GET /transferencias
│   │   │   └── auditoria.py       # /auditoria (pública)
│   │   ├── models.py              # usuarios, contas, transferencias, auditoria
│   │   ├── schemas.py             # contratos de entrada/saída
│   │   ├── database.py            # engine, sessão, espera do MySQL
│   │   ├── security.py            # bcrypt + JWT
│   │   ├── config.py              # variáveis de ambiente
│   │   ├── deps.py                # usuário autenticado (Bearer)
│   │   ├── errors.py              # {"error": "CODIGO"} padronizado
│   │   ├── audit.py               # gravação de eventos
│   │   └── main.py                # app, rotas e front-end estático
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── css/styles.css             # identidade visual original preservada
│   ├── js/
│   │   ├── api.js
│   │   ├── config.js
│   │   ├── login.js
│   │   ├── cadastro.js
│   │   └── painel.js
│   ├── index.html                 # login
│   ├── cadastro.html
│   └── painel.html
├── tests/
│   └── test_api.py                # 20 testes automatizados
├── scripts/
│   └── testes_manuais.sh          # smoke test via curl
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 3. Contrato da API

Toda rejeição tem exatamente o formato `{"error": "CODIGO"}`.

| Rota                  | Autenticação | Sucesso                                                       |
| --------------------- | ------------ | ------------------------------------------------------------- |
| `POST /auth/registrar`| pública      | `201` usuário + conta com 1000 moedas                          |
| `POST /auth/login`    | pública      | `200 {"token": "..."}`                                         |
| `GET /conta`          | Bearer       | `200 {"username": "...", "saldo": 1000, "conta_id": 1}`        |
| `POST /transferencias`| Bearer       | `201 {"id","origem","destino","valor","saldo"}`                |
| `GET /transferencias` | Bearer       | `200` histórico (enviadas e recebidas)                          |
| `GET /auditoria`      | pública      | `200 {"usuarios","somaSaldos","transferencias"}`               |
| `GET /health`         | pública      | `200 {"status":"ok","banco":"conectado"}`                      |

### Erros implementados

| Status | Código                     | Quando                                            |
| ------ | -------------------------- | ------------------------------------------------- |
| 422    | `VALOR_INVALIDO`           | valor ausente, texto, decimal, `null`, `<= 0`      |
| 422    | `MESMA_CONTA`              | destino igual à origem                             |
| 404    | `DESTINO_INEXISTENTE`      | destino não cadastrado                             |
| 409    | `TRANSFERENCIA_DUPLICADA`  | mesma origem+destino+valor há menos de 60 s        |
| 409    | `SALDO_INSUFICIENTE`       | saldo menor que o valor                            |
| 409    | `USUARIO_EXISTENTE`        | cadastro com nome já usado                         |
| 401    | `CREDENCIAIS_INVALIDAS`    | login inválido                                     |
| 401    | `NAO_AUTENTICADO`          | token ausente/inválido/expirado                    |

A ordem de checagem em `/transferencias` é a do enunciado: valor → destino →
mesma conta → **duplicidade** → saldo. Ou seja, uma repetição é recusada como
`TRANSFERENCIA_DUPLICADA` mesmo que o saldo já não seja suficiente.

### Exemplos com curl

```bash
# cadastro
curl -s -X POST localhost:8080/auth/registrar \
  -H 'Content-Type: application/json' \
  -d '{"username":"joao","password":"senha123"}'

# login (guarde o token)
TOKEN=$(curl -s -X POST localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"joao","password":"senha123"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')

# saldo
curl -s localhost:8080/conta -H "Authorization: Bearer $TOKEN"

# transferência (valor INTEIRO)
curl -s -X POST localhost:8080/transferencias \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"destino":"maria","valor":150}'

# auditoria (pública)
curl -s localhost:8080/auditoria
```

---

## 4. Concorrência, atomicidade e duplicidade

Cada `POST /transferencias` executa **uma única transação** no MySQL:

1. valida o corpo (inteiro > 0);
2. resolve a conta de origem **pelo token** (nunca pelo corpo);
3. localiza o destino e recusa a própria conta;
4. abre a transação e trava as duas contas com `SELECT ... FOR UPDATE`
   **em ordem crescente de id** (evita deadlock entre A→B e B→A);
5. consulta transferências idênticas nos últimos 60 s — a leitura `FOR UPDATE`
   enxerga o que outra transação já confirmou (`READ COMMITTED`);
6. confere o saldo;
7. debita a origem, credita o destino, grava a transferência e o evento de
   auditoria;
8. faz `COMMIT` (ou `ROLLBACK` completo em qualquer erro).

Por que duas requisições idênticas simultâneas resultam em exatamente uma
transferência: as duas precisam do bloqueio da **mesma linha da conta de
origem**. A primeira conclui e confirma; a segunda só entra depois, já enxerga
a transferência recém-gravada e recebe `409 TRANSFERENCIA_DUPLICADA`.

Por que nunca há inconsistência: débito, crédito e registro estão na mesma
transação ACID. Se o processo cair antes do `COMMIT`, o MySQL desfaz tudo; se
cair depois, tudo está gravado. Nunca existe débito sem crédito. A soma dos
saldos é sempre `1000 × usuários`, e o banco ainda tem
`CHECK (saldo >= 0)` e `CHECK (valor > 0)` como última linha de defesa.
Deadlocks (1213) são repetidos automaticamente até 5 vezes.

---

## 5. Testes

### Automatizados (dentro do container, contra o MySQL real)

```bash
docker compose exec api python -m pytest tests -v
```

Cobrem: cadastro, duplicado, login válido/inválido, acesso sem/inválido token,
saldo, transferência válida, mesma conta, destino inexistente, valor inválido,
saldo insuficiente, duplicidade em 60 s (e após a janela), 8 transferências
simultâneas, 10 transferências idênticas simultâneas (exatamente 1 sucesso),
integridade da soma, persistência, atomicidade com falha simulada no commit,
front-end servido e hash bcrypt.

> Os dois testes de concorrência usam `SELECT ... FOR UPDATE` e são executados
> no MySQL. Em execução local com SQLite eles são marcados como *skip*.

### Manuais (smoke test do contrato)

```bash
bash scripts/testes_manuais.sh
```

### Sem Docker (opcional, SQLite)

```bash
pip install -r backend/requirements.txt
cd backend
DATABASE_URL=sqlite:///./local.db JWT_SECRET=teste \
  python -m pytest ../tests -v
```

---

## 6. Usuários de teste

Não há usuários pré-cadastrados (nada de dados fictícios no banco). Crie quantos
quiser pela tela de cadastro ou por `POST /auth/registrar`; cada um nasce com
**1000 moedas**. Os testes automatizados criam usuários com sufixo aleatório,
então podem rodar repetidamente.

---

## 7. Front-end

O design original foi mantido (fundo `#05060b`, cartões `#0e1220`, roxo
`#7c5cff`, azul `#3b82f6`, Inter, orbes, gradientes). Ajustes feitos apenas para
integrar de verdade com a API:

- `js/config.js` aponta para a mesma origem (`API_BASE: ""`);
- login/cadastro usam os endpoints e exibem os códigos de erro do contrato;
- o painel lê saldo, histórico e auditoria do banco, bloqueia envio duplo
  enquanto a requisição está em andamento e envia o valor como **inteiro**;
- o painel de auditoria mostra os totais públicos (`usuarios`, `somaSaldos`,
  `transferencias`), calculados no banco.
