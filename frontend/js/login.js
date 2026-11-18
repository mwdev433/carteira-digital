(function () {
  "use strict";

  const { Sessao, requisicao, toast, mostrarErro, esconderErro, carregando, configurarBotoesDeSenha } = window.App;

  const form = document.getElementById("form-login");
  const campoUsuario = document.getElementById("username");
  const campoSenha = document.getElementById("senha");
  const botao = document.getElementById("btn-login");

  configurarBotoesDeSenha();

  // Se já existe uma sessão, vai direto para o painel.
  if (Sessao.existe()) {
    window.location.replace("painel.html");
    return;
  }

  // Mensagens vindas de outras telas (?expirado=1 / ?novo=1).
  const params = new URLSearchParams(window.location.search);
  if (params.get("expirado") === "1") {
    toast("info", "Sessão encerrada", "Seu token expirou ou não é mais válido. Entre novamente.");
  }
  if (params.get("novo") === "1") {
    toast("success", "Conta criada!", "Agora faça login com suas credenciais.");
  }

  // Preenche o usuário quando vem do cadastro (?usuario=ana).
  const usuarioDaUrl = params.get("usuario");
  if (usuarioDaUrl) {
    campoUsuario.value = usuarioDaUrl;
    campoSenha.focus();
  } else {
    campoUsuario.focus();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    esconderErro("login-error");

    const username = campoUsuario.value.trim();
    const senha = campoSenha.value;

    if (username.length < 3) {
      mostrarErro("login-error", "Informe um nome de usuário com pelo menos 3 caracteres.");
      campoUsuario.focus();
      return;
    }
    if (senha.length < 6) {
      mostrarErro("login-error", "A senha deve ter pelo menos 6 caracteres.");
      campoSenha.focus();
      return;
    }

    carregando(botao, true);
    try {
      const dados = await requisicao("/auth/login", {
        metodo: "POST",
        corpo: { username, senha },
        autenticado: false,
      });

      Sessao.salvar(dados);
      toast("success", "Bem-vindo de volta, " + dados.usuario.username + "!", "Redirecionando para o painel…");
      setTimeout(() => window.location.replace("painel.html"), 450);
    } catch (erro) {
      if (erro.codigo === "CREDENCIAIS_INVALIDAS") {
        mostrarErro("login-error", "Usuário ou senha inválidos. Confira os dados e tente novamente.");
      } else if (erro.status === 0) {
        mostrarErro("login-error", erro.message);
      } else {
        mostrarErro("login-error", erro.message || "Não foi possível entrar. Tente novamente.");
      }
      campoSenha.select();
    } finally {
      carregando(botao, false);
    }
  });
})();
