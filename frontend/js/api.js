(function () {
  "use strict";

  const CFG = window.APP_CONFIG;
  const PAGINA_LOGIN = "index.html";

  /* ----------------------------- Sessão ------------------------------ */
  const Sessao = {
    salvar(dados) {
      localStorage.setItem(CFG.TOKEN_KEY, dados.token || dados.access_token);
      localStorage.setItem(CFG.USER_KEY, dados.usuario.username);
      if (dados.expira_em) {
        localStorage.setItem(CFG.EXPIRA_KEY, String(dados.expira_em));
      }
    },
    token() {
      return localStorage.getItem(CFG.TOKEN_KEY);
    },
    usuario() {
      return localStorage.getItem(CFG.USER_KEY) || "";
    },
    expiraEm() {
      return Number(localStorage.getItem(CFG.EXPIRA_KEY) || 0);
    },
    existe() {
      return Boolean(this.token());
    },
    limpar() {
      localStorage.removeItem(CFG.TOKEN_KEY);
      localStorage.removeItem(CFG.USER_KEY);
      localStorage.removeItem(CFG.EXPIRA_KEY);
    },
  };

  /* ------------------------------ API -------------------------------- */
  // Mensagens amigáveis por código de erro do contrato.
  const MENSAGENS_ERRO = {
    USUARIO_EXISTENTE: "Este nome de usuário já está em uso. Escolha outro.",
    DADOS_INVALIDOS: "Confira os dados informados e tente novamente.",
    SENHAS_NAO_CONFEREM: "As senhas não conferem.",
    CREDENCIAIS_INVALIDAS: "Usuário ou senha inválidos.",
    NAO_AUTENTICADO: "Sua sessão não é válida. Entre novamente.",
    VALOR_INVALIDO: "O valor deve ser um número inteiro maior que zero.",
    SALDO_INSUFICIENTE: "Saldo insuficiente para esta transferência.",
    DESTINO_INEXISTENTE: "O usuário de destino não foi encontrado.",
    MESMA_CONTA: "Você não pode transferir para a sua própria conta.",
    TRANSFERENCIA_DUPLICADA: "Uma transferência idêntica foi feita há menos de 60 segundos.",
  };

  /**
   * Faz uma chamada à API e devolve o JSON.
   * Em caso de erro, lança um Error com as propriedades: status e codigo.
   */
  async function requisicao(caminho, opcoes = {}) {
    const { metodo = "GET", corpo = null, autenticado = true, redirecionar401 = true } = opcoes;

    const cabecalhos = { Accept: "application/json" };
    if (corpo !== null) cabecalhos["Content-Type"] = "application/json";

    if (autenticado) {
      const token = Sessao.token();
      if (token) cabecalhos.Authorization = "Bearer " + token;
    }

    let resposta;
    try {
      resposta = await fetch(CFG.API_BASE + caminho, {
        method: metodo,
        headers: cabecalhos,
        body: corpo !== null ? JSON.stringify(corpo) : undefined,
      });
    } catch (erroDeRede) {
      const erro = new Error("Não foi possível conectar ao servidor. Verifique se a API está no ar.");
      erro.status = 0;
      erro.codigo = "SEM_CONEXAO";
      throw erro;
    }

    const texto = await resposta.text();
    let dados = null;
    try {
      dados = texto ? JSON.parse(texto) : null;
    } catch (_) {
      dados = null;
    }

    // 401 = token ausente/inválido (rotas protegidas) ou credenciais
    // inválidas (login). O código exato vem do corpo da API.
    if (resposta.status === 401) {
      if (autenticado && redirecionar401) {
        Sessao.limpar();
        window.location.replace(PAGINA_LOGIN + "?expirado=1");
      }
      const codigo401 = (dados && dados.error) || "NAO_AUTENTICADO";
      const erro = new Error(MENSAGENS_ERRO[codigo401] || codigo401);
      erro.status = 401;
      erro.codigo = codigo401;
      throw erro;
    }

    if (!resposta.ok) {
      const codigo = (dados && dados.error) || "ERRO";
      const erro = new Error(
        MENSAGENS_ERRO[codigo] || (dados && dados.mensagem) || "Ocorreu um erro inesperado."
      );
      erro.status = resposta.status;
      erro.codigo = codigo;
      throw erro;
    }

    return dados;
  }

  /* --------------------------- Formatação ---------------------------- */
  const formatadorMoedas = new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  function formatarMoedas(valor) {
    return formatadorMoedas.format(Number(valor || 0));
  }

  function formatarDataHora(iso) {
    if (!iso) return "—";
    // O MySQL devolve datetime sem fuso; consideramos UTC e exibimos local.
    const temFuso = /[zZ]$|[+-]\d{2}:\d{2}$/.test(iso);
    const data = new Date(temFuso ? iso : iso + "Z");
    if (Number.isNaN(data.getTime())) return iso;
    const dataTexto = data.toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
    const horaTexto = data.toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });
    return dataTexto + " às " + horaTexto;
  }

  function iniciais(nome) {
    if (!nome) return "?";
    const partes = nome.replace(/[._-]+/g, " ").trim().split(/\s+/);
    if (partes.length === 1) return partes[0].slice(0, 2);
    return (partes[0][0] + partes[1][0]).toUpperCase();
  }

  function escaparHtml(texto) {
    return String(texto == null ? "" : texto).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);
  }

  /* ----------------------------- Toasts ------------------------------ */
  const icones = {
    success:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>',
    error:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/></svg>',
    info:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.01"/></svg>',
  };

  function toast(tipo, titulo, mensagem = "", duracao = 4500) {
    const area = document.getElementById("toast-area");
    if (!area) return;

    const el = document.createElement("div");
    el.className = "toast toast--" + (tipo || "info");
    el.innerHTML =
      icones[tipo || "info"] +
      "<div><strong>" + escaparHtml(titulo) + "</strong>" +
      (mensagem ? "<span>" + escaparHtml(mensagem) + "</span>" : "") +
      "</div>";

    area.appendChild(el);

    const remover = () => {
      el.classList.add("is-leaving");
      setTimeout(() => el.remove(), 200);
    };

    el.addEventListener("click", remover);
    setTimeout(remover, duracao);
  }

  /* ------------------------ Estados de formulário -------------------- */
  function mostrarErro(elemento, mensagem) {
    const el = typeof elemento === "string" ? document.getElementById(elemento) : elemento;
    if (!el) return;
    el.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/></svg>' +
      "<span>" + escaparHtml(mensagem) + "</span>";
    el.hidden = false;
  }

  function esconderErro(elemento) {
    const el = typeof elemento === "string" ? document.getElementById(elemento) : elemento;
    if (el) el.hidden = true;
  }

  function carregando(botao, ativo) {
    if (!botao) return;
    botao.classList.toggle("is-loading", ativo);
    botao.disabled = ativo;
  }

  /* ---------------------- Mostrar/ocultar senha ---------------------- */
  function configurarBotoesDeSenha() {
    document.querySelectorAll("[data-reveal]").forEach((botao) => {
      botao.addEventListener("click", () => {
        const input = document.getElementById(botao.dataset.reveal);
        if (!input) return;
        const visivel = input.type === "text";
        input.type = visivel ? "password" : "text";
        botao.setAttribute("aria-pressed", String(!visivel));
        botao.setAttribute("aria-label", visivel ? "Mostrar senha" : "Ocultar senha");
        botao.innerHTML = visivel
          ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>'
          : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 6.2A10.9 10.9 0 0112 6c6.4 0 10 6 10 6a17.7 17.7 0 01-3.3 4.1M6.2 6.9C3.6 8.6 2 12 2 12s3.6 7 10 7c1.5 0 2.8-.3 4-.9"/><path d="M9.9 9.9a3 3 0 004.2 4.2"/></svg>';
        input.focus({ preventScroll: true });
      });
    });
  }

  /* --------------------------- Exportação ---------------------------- */
  window.App = {
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
    configurarBotoesDeSenha,
  };
})();
