"""
Bloqueios em memória por conta.

Defesa em profundidade para concorrência:

  * o banco (MySQL) é a fonte de verdade: SELECT ... FOR UPDATE nas duas
    contas impede leitura/atualização concorrente do mesmo saldo;
  * este módulo adiciona um bloqueio por conta dentro do processo, sempre na
    ordem crescente de id (mesma ordem usada no banco). Isso reduz a
    contenção no banco e protege o processo contra duas operações
    simultâneas na mesma conta.

Como os bloqueios são adquiridos em ordem determinística, não há deadlock
entre transferências A->B e B->A.
"""

import threading
from contextlib import contextmanager


class _GerenciadorDeBloqueios:
    def __init__(self) -> None:
        self._guarda = threading.Lock()
        # id da conta -> [bloqueio, quantidade de usuários esperando/usando]
        self._bloqueios: dict[int, list] = {}

    @contextmanager
    def travar_contas(self, ids: list[int]):
        ids_ordenados = sorted(set(ids))
        entradas = []

        with self._guarda:
            for conta_id in ids_ordenados:
                entrada = self._bloqueios.get(conta_id)
                if entrada is None:
                    entrada = [threading.RLock(), 0]
                    self._bloqueios[conta_id] = entrada
                entrada[1] += 1
                entradas.append(entrada)

        try:
            for entrada in entradas:
                entrada[0].acquire()
            yield
        finally:
            for entrada in reversed(entradas):
                entrada[0].release()
            with self._guarda:
                for conta_id in ids_ordenados:
                    entrada = self._bloqueios[conta_id]
                    entrada[1] -= 1
                    if entrada[1] <= 0:
                        self._bloqueios.pop(conta_id, None)


gerenciador_de_bloqueios = _GerenciadorDeBloqueios()


def travar_contas(ids: list[int]):
    """Context manager que serializa operações sobre as contas informadas."""
    return gerenciador_de_bloqueios.travar_contas(ids)
