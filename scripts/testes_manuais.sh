#!/usr/bin/env bash
# Testes manuais rápidos do contrato da API.
# Uso:  bash scripts/testes_manuais.sh
#       API=http://localhost:8080 bash scripts/testes_manuais.sh

set -u

API="${API:-http://localhost:8080}"
SUFIXO="$(date +%s)"
USER_A="ana_${SUFIXO}"
USER_B="bruno_${SUFIXO}"
SENHA="segredo123"
TMP="$(mktemp -d)"
TOTAL=0
OK=0
FALHAS=0

trap 'rm -rf "$TMP"' EXIT

http() {
  # http METODO CAMINHO [JSON] [TOKEN]
  local metodo="$1" caminho="$2" dados="${3:-}" token="${4:-}"
  local argumentos=(-s -o "$TMP/resp.json" -w "%{http_code}" -X "$metodo" "$API$caminho")

  [[ -n "$dados" ]] && argumentos+=(-H "Content-Type: application/json" -d "$dados")
  [[ -n "$token" ]] && argumentos+=(-H "Authorization: Bearer $token")

  STATUS="$(curl "${argumentos[@]}")"
  BODY="$(cat "$TMP/resp.json" 2>/dev/null || echo '')"
  CODIGO="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("error",""))
except Exception:
    print("")' "$TMP/resp.json" 2>/dev/null || true)"
}

checar() {
  # checar "descrição" STATUS_ESPERADO [CODIGO_ESPERADO]
  local descricao="$1" esperado="$2" codigo_esperado="${3:-}"
  TOTAL=$((TOTAL + 1))
  if [[ "$STATUS" == "$esperado" ]] && { [[ -z "$codigo_esperado" ]] || [[ "$CODIGO" == "$codigo_esperado" ]]; }; then
    echo "  ok   $descricao ($STATUS${CODIGO:+ $CODIGO})"
    OK=$((OK + 1))
  else
    echo "  FALHA $descricao -> status=$STATUS codigo=$CODIGO body=$BODY"
    FALHAS=$((FALHAS + 1))
  fi
}

echo "API: $API"

http POST /auth/registrar "{\"username\":\"$USER_A\",\"password\":\"$SENHA\"}"
checar "cadastro de $USER_A" 201

http POST /auth/registrar "{\"username\":\"$USER_A\",\"password\":\"$SENHA\"}"
checar "cadastro duplicado" 409 USUARIO_EXISTENTE

http POST /auth/registrar "{\"username\":\"$USER_B\",\"password\":\"$SENHA\"}"
checar "cadastro de $USER_B" 201

http POST /auth/login "{\"username\":\"$USER_A\",\"password\":\"$SENHA\"}"
checar "login válido" 200
TOKEN_A="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$TMP/resp.json")"

http POST /auth/login "{\"username\":\"$USER_A\",\"password\":\"errada\"}"
checar "login inválido" 401 CREDENCIAIS_INVALIDAS

http GET /conta
checar "conta sem token" 401 NAO_AUTENTICADO

http GET /conta "" "$TOKEN_A"
checar "consulta de saldo" 200
[[ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["saldo"])' "$TMP/resp.json")" == "1000" ]] \
  && echo "  ok   saldo inicial 1000" || { echo "  FALHA saldo inicial"; FALHAS=$((FALHAS + 1)); }

http POST /transferencias "{\"destino\":\"$USER_B\",\"valor\":150}" "$TOKEN_A"
checar "transferência válida" 201
[[ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["saldo"])' "$TMP/resp.json")" == "850" ]] \
  && echo "  ok   saldo após transferência 850" || { echo "  FALHA saldo após transferência"; FALHAS=$((FALHAS + 1)); }

http POST /transferencias "{\"destino\":\"$USER_B\",\"valor\":150}" "$TOKEN_A"
checar "transferência duplicada" 409 TRANSFERENCIA_DUPLICADA

http POST /transferencias "{\"destino\":\"$USER_A\",\"valor\":10}" "$TOKEN_A"
checar "transferência para si mesmo" 422 MESMA_CONTA

http POST /transferencias "{\"destino\":\"nao_existe_$SUFIXO\",\"valor\":10}" "$TOKEN_A"
checar "destino inexistente" 404 DESTINO_INEXISTENTE

http POST /transferencias "{\"destino\":\"$USER_B\",\"valor\":\"150\"}" "$TOKEN_A"
checar "valor em texto" 422 VALOR_INVALIDO

http POST /transferencias "{\"destino\":\"$USER_B\",\"valor\":0}" "$TOKEN_A"
checar "valor zero" 422 VALOR_INVALIDO

http POST /transferencias "{\"destino\":\"$USER_B\",\"valor\":999999}" "$TOKEN_A"
checar "saldo insuficiente" 409 SALDO_INSUFICIENTE

http GET /auditoria
checar "auditoria pública" 200

echo
echo "Resultado: $OK/$TOTAL verificações ok, $FALHAS falha(s)."
[[ "$FALHAS" -eq 0 ]] || exit 1
