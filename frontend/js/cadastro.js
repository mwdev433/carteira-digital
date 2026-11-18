(function () {
  "use strict";

  const { Sessao, requisicao, toast, mostrarErro, esconderErro, carregando, configurarBotoesDeSenha } = window.App;

  const form = document.getElementById("form-cadastro");
  const campoUsuario = document.getElementById("username");
  const campoSenha = document.getElementById("senha");
  const campoConfirmacao = document.getElementById("confirmacao_senha");
  const botao = document.getElementById("btn-cadastrar");
  const strength = document.getElementById("strength");
  const strengthLabel = document.getElementById("strength-label");
  const sucesso = document.getElementById("cadastro-success");

  const REGEX_USUARIO = /^[A-Za-z0-9._-]{3,32}$/;

  configurarBotoesDeSenha();

  if (Sessao.existe()) {
    window.location.replace("painel.html");
    return;
  }

  /* --------------------- Força da senha (visual) --------------------- */
  function avaliarForca(senha) {
    let pontos = 0;
    if (senha.length >= 6) pontos += 1;
    if (senha.length >= 10) pontos += 1;
    if (/[A-Z]/.test(senha) && /[a-z]/.test(senha)) pontos += 1;
    if (/\d/.test(senha) && /[^A-Za-z0-9]/.test(senha)) pontos += 1;
    return Math.min(pontos, 4);
  }

  const rotulos = ["aguardando…", "fraca", "razoável", "boa", "forte"];

  campoSenha.addEventListener("input", () => {
    const senha = campoSenha.value;
    if (!senha) {
      strength.dataset.level = "0";
      strengthLabel.textContent = "Força da senha: aguardando…";
      return;
    }
    const nivel = avaliarForca(senha);
    strength.dataset.level = String(nivel);
    strengthLabel.textContent = "Força da senha: " + rotulos[nivel];
  });

  /* ---------------------------- Envio -------------------------------- */
  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    esconderErro("cadastro-error");
    sucesso.hidden = true;

    const username = campoUsuario.value.trim();
    const senha = campoSenha.value;
    const confirmacao = campoConfirmacao.value;

    if (!REGEX_USUARIO.test(username)) {
      mostrarErro(
        "cadastro-error",
        "O nome de usuário deve ter de 3 a 32 caracteres e usar apenas letras, números, ponto, hífen ou underline."
      );
      campoUsuario.focus();
      return;
    }
    if (senha.length < 6) {
      mostrarErro("cadastro-error", "A senha deve ter pelo menos 6 caracteres.");
      campoSenha.focus();
      return;
    }
    if (senha !== confirmacao) {
      mostrarErro("cadastro-error", "As senhas não conferem. Digite a mesma senha nos dois campos.");
      campoConfirmacao.focus();
      return;
    }

    carregando(botao, true);
    try {
      const dados = await requisicao("/auth/registrar", {
        metodo: "POST",
        corpo: {
          username,
          senha,
          confirmacao_senha: confirmacao,
        },
        autenticado: false,
      });

      sucesso.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>' +
        "<span>Conta <strong>@" + window.App.escaparHtml(dados.usuario.username) + "</strong> criada com saldo de " +
        window.App.formatarMoedas(dados.saldo) + " moedas. Redirecionando para o login…</span>";
      sucesso.hidden = false;
      form.querySelectorAll("input").forEach((input) => (input.disabled = true));
      toast("success", "Cadastro concluído", "Sua conta foi criada com 1.000 moedas.");

      setTimeout(() => {
        window.location.href = "index.html?usuario=" + encodeURIComponent(dados.usuario.username) + "&novo=1";
      }, 1600);
    } catch (erro) {
      if (erro.codigo === "USUARIO_EXISTENTE") {
        mostrarErro("cadastro-error", "Este nome de usuário já está em uso. Escolha outro.");
        campoUsuario.focus();
        campoUsuario.select();
      } else if (erro.codigo === "SENHAS_NAO_CONFEREM") {
        mostrarErro("cadastro-error", "As senhas não conferem.");
      } else if (erro.codigo === "DADOS_INVALIDOS") {
        mostrarErro("cadastro-error", erro.message);
      } else if (erro.status === 0) {
        mostrarErro("cadastro-error", erro.message);
      } else {
        mostrarErro("cadastro-error", erro.message || "Não foi possível cadastrar. Tente novamente.");
      }
    } finally {
      carregando(botao, false);
    }
  });
})();
