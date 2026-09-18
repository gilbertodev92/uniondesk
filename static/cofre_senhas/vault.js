(function () {
  const display = document.getElementById("vault-display");
  const keys = document.querySelectorAll(".cofre-key");
  const unlockBtn = document.getElementById("unlock-btn");
  const lockBtn = document.getElementById("lock-btn");
  const panel = document.getElementById("cofre-panel");
  const content = document.getElementById("vault-content");
  const cardsContainer = document.getElementById("cards-container");
  const clearBtn = document.getElementById("key-clear");
  const delBtn = document.getElementById("key-del");
  const hideBtn = document.getElementById("hide-panel-btn");

  let code = "";

  function updateDisplay() {
    display.textContent = code.length === 0 ? "••••" : "•".repeat(code.length);
  }

  function showError(msg) {
    if (!cardsContainer) return;
    const div = document.createElement("div");
    div.className = "cofre-alert";
    div.textContent = msg;
    cardsContainer.prepend(div);
    setTimeout(() => div.remove(), 4000);
  }

  keys.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const v = e.target.textContent.trim();
      if (v === "C") {
        code = "";
        updateDisplay();
        return;
      }
      if (v === "←") {
        code = code.slice(0, -1);
        updateDisplay();
        return;
      }
      if (code.length >= 12) return;
      code += v;
      updateDisplay();
    });
  });

  unlockBtn.addEventListener("click", async () => {
    if (code.length === 0) {
      showError("Digite o PIN");
      return;
    }
    unlockBtn.disabled = true;
    unlockBtn.textContent = "Verificando...";
    try {
      const resp = await fetch("/cofre/unlock/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({ pin: code }),
      });

      if (resp.status === 200) {
        const data = await resp.json();
        // animação de abrir
        panel.classList.remove("cofre-locked");
        panel.classList.add("cofre-unlocked");
        content.classList.remove("cofre-hidden");
        document.querySelector(".cofre-page").classList.add("cofre-opened");
        if (hideBtn) hideBtn.classList.remove("cofre-hidden");
        renderCards(data.credentials);
      } else {
        let msg = "Erro ao desbloquear.";
        try {
          const data = await resp.json();
          if (data && data.error) {
            msg = data.error + " (" + (data.type || "erro") + ")";
          }
        } catch (e) {}
        showError(msg);
      }
    } catch (err) {
      showError("Erro de comunicação com o servidor.");
    } finally {
      unlockBtn.disabled = false;
      unlockBtn.textContent = "Abrir Cofre";
      code = "";
      updateDisplay();
    }
  });

  // fechar cofre
  if (lockBtn) {
    lockBtn.addEventListener("click", async () => {
      await fetch("/cofre/unlock/lock/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
      });
      panel.classList.remove("cofre-unlocked");
      content.classList.add("cofre-hidden");
      const page = document.querySelector(".cofre-page");
      page.classList.remove("cofre-opened", "cofre-panel-hidden");
      if (hideBtn) hideBtn.classList.add("cofre-hidden");
      cardsContainer.innerHTML = "";
    });
  }

  // botão de esconder painel
  if (hideBtn) {
    hideBtn.addEventListener("click", () => {
      const page = document.querySelector(".cofre-page");
      if (page.classList.contains("cofre-panel-hidden")) {
        page.classList.remove("cofre-panel-hidden");
        hideBtn.textContent = "Esconder painel";
      } else {
        page.classList.add("cofre-panel-hidden");
        hideBtn.textContent = "Mostrar painel";
      }
    });
  }

  function renderCards(list) {
    cardsContainer.innerHTML = "";
    if (!list || list.length === 0) {
      cardsContainer.innerHTML = "<p>Nenhuma credencial cadastrada.</p>";
      return;
    }
    list.forEach((item) => {
      const el = document.createElement("div");
      el.className = "cofre-card";
      el.innerHTML = `
        <h3>${escapeHtml(item.title)} ${
        item.tags ? `<small>${escapeHtml(item.tags)}</small>` : ""
      }</h3>
        <p><strong>Usuário:</strong> ${escapeHtml(item.username || "")}</p>
        <p><strong>Senha:</strong> <span id="mask-${
          item.id
        }" class="cofre-mask">••••••••</span></p>
        <div class="cofre-card-actions">
          <button class="cofre-reveal" data-id="${item.id}">Revelar</button>
          <a href="/cofre/edit/${item.id}/" class="cofre-edit">Editar</a>
        </div>
      `;
      cardsContainer.appendChild(el);
    });

    document.querySelectorAll(".cofre-reveal").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const id = e.target.dataset.id;
        e.target.disabled = true;
        e.target.textContent = "Carregando...";
        try {
          const resp = await fetch(`/cofre/unlock/view/${id}/`, {
            credentials: "same-origin",
          });
          if (resp.status === 200) {
            const data = await resp.json();
            const mask = document.getElementById(`mask-${id}`);
            mask.textContent = data.password;
            await fetch(`/cofre/unlock/log/${id}/`, {
              method: "POST",
              credentials: "same-origin",
              headers: { "X-CSRFToken": getCookie("csrftoken") },
            });
          } else {
            showError("Sessão expirada ou sem permissão.");
          }
        } catch (err) {
          showError("Erro de comunicação ao revelar senha.");
        } finally {
          e.target.disabled = false;
          e.target.textContent = "Revelar";
        }
      });
    });
  }

  function getCookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  function escapeHtml(text) {
    if (!text) return "";
    return text.replace(/[&<>"']/g, function (m) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      }[m];
    });
  }

  updateDisplay();
})();

