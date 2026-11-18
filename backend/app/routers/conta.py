"""
Rota da conta do usuário.

GET /conta -> devolve o nome e o saldo do usuário AUTENTICADO.
              Qualquer parâmetro de nome enviado pelo cliente é ignorado.
"""

from fastapi import APIRouter, Depends

from ..deps import get_conta_do_usuario
from ..schemas import ContaResposta

router = APIRouter(prefix="/conta", tags=["Conta"])


@router.get("", response_model=ContaResposta, summary="Dados da própria conta (autenticado)")
def minha_conta(dados=Depends(get_conta_do_usuario)):
    usuario, conta = dados
    return ContaResposta(
        username=usuario.username,
        saldo=int(conta.saldo),
        conta_id=conta.id,
    )
