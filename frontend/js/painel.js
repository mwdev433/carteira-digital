(function () {
  "use strict";

  const {
    Sessao,
    requisicao,
    formatarMoedas,
    formatarDataHora,
    iniciais,
    escaparHtml,
    toast,
    mostrarErro,
    esconderErro,
    carregando,
  } = window.App;

  // Sem token não há painel: volta para o login imediatamente.
  if (!Sessao.existe()) {
    window.location.replace("index.html");
    return;
  }

  const el = (id) => document.getElementById(id);

  let saldoAtual = 0;
  let saldoOculto = false;
  let contaAtual = null;
  let transferindo = false;

  const ROTULOS_AUDITORIA = {
    REGISTRO: "Cadastro realizado",
    REGISTRO_NEGADO: "Cadastro recusado",
    LOGIN_OK: "Login realizado",
    LOGIN_FALHA: "Tentativa de login falhou",
    TRANSFERENCIA: "Transferência realizada",
    ACESSO_NEGADO: "Acesso negado",
  };

  /* ------------------------- Cabeçalho / sessão ---------------------- */
  function preencherCabecalho() {
    const nome = Sessao.usuario();
    el("user-name").textContent = nome || "usuário";
    el("chip-username").textContent = nome || "usuário";
    el("avatar").textContent = iniciais(nome);
    el("origem-label").textContent = "@" + (nome || "usuário");
  }

  function atualizarContadorSessao() {
    const expiraEm = Sessao.expiraEm();
    const alvo = el("sessao-expira");
    if (!expiraEm) {
      alvo.textContent = "Sessão ativa";
      return;
    }

    const restante = expiraEm * 1000 - Date.now();
    if (restante <= 0) {
      Sessao.limpar();
      toast("info", "Sessão expirada", "Faça login novamente para continuar.", 6000);
      setTimeout(() => window.location.replace("index.html?expirado=1"), 700);
      return;
    }

    const minutos = Math.floor(restante / 60000);
    const horas = Math.floor(minutos / 60);
    if (horas >= 1) {
      alvo.textContent = horas + "h " + String(minutos % 60).padStart(2, "0") + "min";
    } else {
      alvo.textContent = Math.max(minutos, 1) + " min";
    }
  }

  /* ------------------------------- Saldo ----------------------------- */
  function renderizarSaldo() {
    const valor = el("saldo");
    valor.classList.remove("skeleton");
    valor.textContent = saldoOculto ? "••••••" : formatarMoedas(saldoAtual);
    valor.setAttribute("aria-label", saldoOculto ? "Saldo oculto" : "Saldo " + formatarMoedas(saldoAtual) + " moedas");

    el("conta-saldo").textContent = saldoOculto
      ? "•••••• moedas"
      : formatarMoedas(saldoAtual) + " moedas";
  }

  async function carregarConta() {
    const conta = await requisicao("/conta");
    contaAtual = conta;
    saldoAtual = Number(conta.saldo);

    el("conta-id").textContent = conta.conta_id;
    el("conta-identificador").textContent = "#" + conta.conta_id;
    el("conta-usuario").textContent = "@" + conta.username;
    el("atualizado-em").textContent = new Date().toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });

    renderizarSaldo();
  }

  /* ------------------------------ Extrato ---------------------------- */
  function svgSeta(entrada) {
    return entrada
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 7l10 10M17 9v8H9"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 17L7 7M7 15V7h8"/></svg>';
  }

  function estadoVazio(icone, texto) {
    return (
      '<div class="empty-state">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      icone +
      "</svg><span>" +
      escaparHtml(texto) +
      "</span></div>"
    );
  }

  async function carregarExtrato() {
    const lista = el("extrato-list");
    try {
      const dados = await requisicao("/transferencias?limite=10");

      if (!dados.transferencias.length) {
        lista.innerHTML = estadoVazio(
          '<circle cx="12" cy="12" r="9"/><path d="M12 8v5l3 2"/>',
          "Nenhuma transferência ainda. Sua primeira movimentação aparecerá aqui."
        );
        return;
      }

      lista.innerHTML = dados.transferencias
        .map((tx) => {
          const entrada = tx.direcao === "RECEBIDA";
          const titulo = entrada ? "Recebido de @" + tx.origem : "Enviado para @" + tx.destino;
          return (
            '<article class="tx ' + (entrada ? "tx--in" : "tx--out") + '">' +
            '<span class="tx__icon">' + svgSeta(entrada) + "</span>" +
            '<div class="tx__main">' +
            '<div class="tx__title">' + escaparHtml(titulo) + "</div>" +
            '<div class="tx__sub">' + escaparHtml(formatarDataHora(tx.criada_em)) + " · #" + tx.id + "</div>" +
            "</div>" +
            '<div class="tx__value">' + (entrada ? "+" : "−") + formatarMoedas(tx.valor) + "</div>" +
            "</article>"
          );
        })
        .join("");
    } catch (erro) {
      if (erro.status === 401) return;
      lista.innerHTML = estadoVazio(
        '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/>',
        "Não foi possível carregar o histórico."
      );
    }
  }

  /* ----------------------------- Auditoria --------------------------- */
  // A rota pública /auditoria devolve os totais do sistema calculados no banco.
  async function carregarAuditoria() {
    const lista = el("audit-list");
    try {
      const dados = await requisicao("/auditoria", { autenticado: false, redirecionar401: false });

      const itens = [
        { rotulo: "Usuários cadastrados", valor: formatarMoedas(dados.usuarios), ok: true },
        { rotulo: "Soma dos saldos", valor: formatarMoedas(dados.somaSaldos) + " moedas", ok: true },
        { rotulo: "Transferências efetivadas", valor: formatarMoedas(dados.transferencias), ok: true },
      ];

      lista.innerHTML = itens
        .map(
          (item) =>
            '<div class="audit-item">' +
            '<span class="audit-item__dot audit-item__dot--ok"></span>' +
            '<div class="audit-item__body"><strong>' + escaparHtml(item.rotulo) + "</strong></div>" +
            "<time>" + escaparHtml(item.valor) + "</time>" +
            "</div>"
        )
        .join("");

      // Confere a regra de integridade: soma dos saldos = 1000 x usuários.
      const esperado = Number(dados.usuarios) * 1000;
      const selo = el("servidor-status");
      if (selo && Number(dados.somaSaldos) !== esperado) {
        toast("error", "Inconsistência na auditoria", "A soma dos saldos não confere com o esperado.");
      }
    } catch (erro) {
      lista.innerHTML = estadoVazio(
        '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/>',
        "Auditoria indisponível no momento."
      );
    }
  }

  /* ----------------------------- Servidor ---------------------------- */
  async function verificarServidor() {
    const selo = el("servidor-status");
    try {
      const dados = await requisicao("/health", { autenticado: false, redirecionar401: false });
      selo.textContent = dados.banco === "conectado" ? "MySQL online" : "online";
      selo.className = "badge badge--success";
    } catch (_) {
      selo.textContent = "offline";
      selo.className = "badge badge--neutral";
    }
  }

  /* --------------------------- Carregar tudo ------------------------- */
  async function carregarTudo(mostrarToque = false) {
    const resultados = await Promise.allSettled([
      carregarConta(),
      carregarExtrato(),
      carregarAuditoria(),
      verificarServidor(),
    ]);

    if (resultados[0].status === "rejected" && resultados[0].reason.status === 401) {
      return; // a camada de API já redirecionou
    }

    const falhou = resultados.some((r) => r.status === "rejected");
    if (falhou && mostrarToque) {
      toast("error", "Alguns dados não puderam ser carregados", "Tente atualizar novamente.");
    } else if (mostrarToque) {
      toast("success", "Dados atualizados", "Saldo, histórico e auditoria estão em dia.");
    }
  }

  /* ------------------------------ Eventos ---------------------------- */
  function configurarEventos() {
    // Mostrar / ocultar saldo
    el("btn-ocultar").addEventListener("click", () => {
      saldoOculto = !saldoOculto;
      const botao = el("btn-ocultar");
      botao.setAttribute("aria-pressed", String(saldoOculto));
      botao.setAttribute("aria-label", saldoOculto ? "Mostrar saldo" : "Ocultar saldo");
      botao.innerHTML = saldoOculto
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 6.2A10.9 10.9 0 0112 6c6.4 0 10 6 10 6a17.7 17.7 0 01-3.3 4.1M6.2 6.9C3.6 8.6 2 12 2 12s3.6 7 10 7c1.5 0 2.8-.3 4-.9"/><path d="M9.9 9.9a3 3 0 004.2 4.2"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
      renderizarSaldo();
    });

    // Atualizações
    const atualizar = async (botao) => {
      botao.disabled = true;
      await carregarTudo(true);
      botao.disabled = false;
    };

    el("btn-atualizar").addEventListener("click", (e) => atualizar(e.currentTarget));
    el("btn-atualizar-saldo").addEventListener("click", (e) => atualizar(e.currentTarget));
    el("btn-atualizar-extrato").addEventListener("click", async () => {
      await carregarExtrato();
      await carregarConta();
    });
    el("btn-atualizar-auditoria").addEventListener("click", () => carregarAuditoria());

    // Sair
    el("btn-logout").addEventListener("click", () => {
      Sessao.limpar();
      toast("info", "Você saiu da conta", "Sua sessão local foi encerrada.");
      setTimeout(() => window.location.replace("index.html"), 350);
    });

    // Transferência
    const form = el("form-transferencia");
    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      esconderErro("transferencia-error");

      if (transferindo) return;

      const destino = el("destino").value.trim();
      const valorTexto = String(el("valor").value).trim();
      const valorNumerico = Number(valorTexto);

      if (!/^[A-Za-z0-9._-]{3,32}$/.test(destino)) {
        mostrarErro("transferencia-error", "Informe um nome de usuário de destino válido (3 a 32 caracteres).");
        el("destino").focus();
        return;
      }
      if (!valorTexto || !Number.isFinite(valorNumerico) || !Number.isInteger(valorNumerico) || valorNumerico <= 0) {
        mostrarErro("transferencia-error", "O valor deve ser um número inteiro maior que zero.");
        el("valor").focus();
        return;
      }

      const botao = el("btn-transferir");
      transferindo = true;
      carregando(botao, true);
      try {
        // Repare: enviamos apenas destino e valor.
        // A conta de origem vem do token no backend, não do navegador.
        const resultado = await requisicao("/transferencias", {
          metodo: "POST",
          corpo: { destino, valor: valorNumerico },
        });

        form.reset();
        toast(
          "success",
          "Transferência concluída",
          formatarMoedas(resultado.valor) + " moedas para @" + resultado.destino +
            ". Seu novo saldo é " + formatarMoedas(resultado.saldo) + "."
        );

        await Promise.allSettled([carregarConta(), carregarExtrato(), carregarAuditoria()]);
      } catch (erro) {
        const mensagens = {
          SALDO_INSUFICIENTE: "Saldo insuficiente para esta transferência.",
          DESTINO_INEXISTENTE: "O usuário de destino não foi encontrado.",
          MESMA_CONTA: "Você não pode transferir para a sua própria conta.",
          TRANSFERENCIA_DUPLICADA: "Uma transferência idêntica foi feita há menos de 60 segundos. Aguarde para repetir.",
          VALOR_INVALIDO: "O valor deve ser um número inteiro maior que zero.",
          DADOS_INVALIDOS: "Os dados enviados são inválidos.",
        };
        mostrarErro("transferencia-error", mensagens[erro.codigo] || erro.message || "Não foi possível transferir.");
      } finally {
        transferindo = false;
        carregando(botao, false);
      }
    });

    // Atualiza o saldo quando a aba volta a ficar visível.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && Sessao.existe()) {
        carregarConta().catch(() => {});
      }
    });
  }

  /* ------------------------------- Início ---------------------------- */
  preencherCabecalho();
  configurarEventos();
  atualizarContadorSessao();
  setInterval(atualizarContadorSessao, 30000);
  carregarTudo();

  // Expõe para depuração no console (útil em apresentação).
  window.painel = { get conta() { return contaAtual; } };
})();
