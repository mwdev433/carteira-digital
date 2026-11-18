# Roteiro da apresentação (5 minutos)

## 0:00–0:40 — O problema
Uma transferência precisa acontecer **exatamente uma vez**, mesmo com cliques
repetidos, requisições simultâneas e queda do servidor. Regras fixas: 1000
moedas por usuário, soma constante, saldo nunca negativo, duplicidade bloqueada
por 60 s e nenhuma transferência pela metade.

## 0:40–1:30 — Arquitetura
- Front-end original (HTML/CSS/JS) preservado e servido pela própria API.
- FastAPI + SQLAlchemy, MySQL 8, JWT + bcrypt.
- Um único `docker compose up --build -d` sobe `db` + `api` em
  `http://localhost:8080`; volume nomeado preserva os dados.
- A origem da transferência vem **somente do token**, nunca do corpo.

## 1:30–3:00 — Estratégia de concorrência (o coração)
1. **Uma transação ACID por transferência**: validação, bloqueio, duplicidade,
   saldo, débito, crédito e registro; `COMMIT` ou `ROLLBACK` completo.
2. **`SELECT ... FOR UPDATE` nas duas contas**, sempre em ordem crescente de
   id — evita deadlock entre A→B e B→A.
3. **Isolamento READ COMMITTED** para que a checagem de duplicidade, feita
   depois do bloqueio, enxergue o que a transação anterior confirmou.
4. **Bloqueio em memória por conta** (mesma ordem) como defesa em profundidade
   e para reduzir contenção.
5. **Deadlock 1213** é repetido automaticamente até 5 vezes.
6. Banco ainda tem `CHECK saldo >= 0` e `CHECK valor > 0`.

## 3:00–3:50 — Duplicidade
Mesma origem + destino + valor, janela de 60 s. A checagem acontece **antes**
do saldo. Duas requisições idênticas simultâneas: a segunda espera o bloqueio
da conta de origem, encontra a transferência recém-gravada e recebe
`409 TRANSFERENCIA_DUPLICADA`. Exatamente uma é efetivada.

## 3:50–4:30 — Queda do servidor
Se o processo cair antes do `COMMIT`, o MySQL desfaz tudo. Se cair depois, tudo
está gravado. Não existe débito sem crédito: os dois saldos e o registro estão
na mesma transação.

## 4:30–5:00 — Demonstração
```bash
docker compose down -v && docker compose up --build -d
docker compose exec api python -m pytest tests -v
bash scripts/testes_manuais.sh
```
Mostrar: cadastro, saldo 1000, transferência 150 → saldo 850, repetição em
menos de 60 s → `TRANSFERENCIA_DUPLICADA`, `/auditoria` com
`somaSaldos = 1000 × usuarios`.

## Perguntas prováveis
- **Por que não usar apenas um `UNIQUE`?** Porque a regra é temporal (60 s):
  o mesmo trio pode se repetir depois da janela. O índice
  `(origem, destino, valor, criada_em)` acelera a checagem.
- **Por que travar as duas contas?** Para ninguém ler um saldo enquanto outro
  escreve; e em ordem de id para não gerar deadlock.
- **E se houver mais de um worker/processo?** Os bloqueios do MySQL valem entre
  processos; o bloqueio em memória é só otimização dentro do processo.
- **Por que moedas inteiras?** O enunciado trabalha com inteiros; evita erros de
  arredondamento e simplifica a auditoria.
