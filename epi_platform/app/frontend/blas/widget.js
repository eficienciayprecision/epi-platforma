/*
 * Widget de Blas — burbuja de chat con pinta de WhatsApp para incrustar en
 * www.eficienciayprecisionindustrial.com.
 *
 * Uso: justo antes de </body> en la web de la empresa:
 *   <script src="https://epi.eficienciayprecisionindustrial.com/blas/widget.js"></script>
 *
 * Todo el CSS/JS va en un unico fichero (sin dependencias) para que sea
 * plug&play en cualquier pagina, con clases prefijadas "blas-" para no
 * chocar con los estilos de la web. API_BASE se calcula a partir de la
 * propia URL de este script (origen + carpeta), asi funciona tanto si se
 * sirve en la raiz como bajo /blas (que es el caso ahora, montado dentro
 * de EPi).
 */
(function () {
  "use strict";

  var currentScript = document.currentScript || (function () {
    var scripts = document.getElementsByTagName("script");
    return scripts[scripts.length - 1];
  })();
  var scriptUrl = new URL(currentScript.src);
  var API_BASE = scriptUrl.origin + scriptUrl.pathname.replace(/\/widget\.js$/, "");

  var SESSION_KEY = "blas_web_session_id";
  function getSessionId() {
    var id = window.localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = "web-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
      window.localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  var STYLE = "" +
    ".blas-bubble-btn{position:fixed;bottom:22px;right:22px;width:60px;height:60px;" +
    "border-radius:50%;background:#25D366;box-shadow:0 4px 14px rgba(0,0,0,.25);" +
    "display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:999998;" +
    "border:none;transition:transform .15s ease;}" +
    ".blas-bubble-btn:hover{transform:scale(1.06);}" +
    ".blas-bubble-btn svg{width:30px;height:30px;}" +
    ".blas-panel{position:fixed;bottom:96px;right:22px;width:340px;max-width:92vw;height:480px;" +
    "max-height:75vh;background:#e5ddd5;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.3);" +
    "display:none;flex-direction:column;overflow:hidden;z-index:999999;" +
    "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;}" +
    ".blas-panel.open{display:flex;}" +
    ".blas-header{background:#075E54;color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px;}" +
    ".blas-header .blas-avatar{width:36px;height:36px;border-radius:50%;background:#0e2b4d;" +
    "display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;flex-shrink:0;}" +
    ".blas-header .blas-title{font-weight:600;font-size:15px;line-height:1.2;}" +
    ".blas-header .blas-subtitle{font-size:11.5px;opacity:.85;}" +
    ".blas-header .blas-close{margin-left:auto;cursor:pointer;opacity:.9;font-size:20px;line-height:1;" +
    "background:none;border:none;color:#fff;}" +
    ".blas-body{flex:1;overflow-y:auto;padding:14px 10px;display:flex;flex-direction:column;gap:6px;}" +
    ".blas-msg{max-width:78%;padding:7px 10px;border-radius:8px;font-size:13.5px;line-height:1.35;" +
    "box-shadow:0 1px 1px rgba(0,0,0,.08);white-space:pre-wrap;word-wrap:break-word;}" +
    ".blas-msg.bot{align-self:flex-start;background:#fff;border-top-left-radius:0;}" +
    ".blas-msg.user{align-self:flex-end;background:#dcf8c6;border-top-right-radius:0;}" +
    ".blas-inputbar{display:flex;align-items:center;gap:8px;padding:8px;background:#f0f0f0;}" +
    ".blas-inputbar input{flex:1;border:none;border-radius:20px;padding:10px 14px;font-size:13.5px;outline:none;}" +
    ".blas-inputbar button{background:#25D366;border:none;border-radius:50%;width:38px;height:38px;" +
    "display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;}" +
    ".blas-inputbar button svg{width:18px;height:18px;fill:#fff;}";

  function injectStyle() {
    var tag = document.createElement("style");
    tag.textContent = STYLE;
    document.head.appendChild(tag);
  }

  var WHATSAPP_ICON = '<svg viewBox="0 0 32 32" fill="#fff"><path d="M16.04 3C9.4 3 4 8.4 4 15.04c0 2.3.64 4.44 1.75 6.28L4 29l7.86-1.7a12 12 0 0 0 4.18.75h.01c6.64 0 12.03-5.4 12.03-12.03C28.08 8.4 22.68 3 16.04 3zm0 21.9c-1.5 0-2.94-.4-4.19-1.16l-.3-.18-4.66 1 1.02-4.55-.2-.3a9.85 9.85 0 0 1-1.5-5.27c0-5.46 4.44-9.9 9.9-9.9a9.83 9.83 0 0 1 7 2.9 9.83 9.83 0 0 1 2.9 7c0 5.46-4.5 9.46-10 9.46zm5.4-7.4c-.3-.15-1.76-.87-2.03-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.17-.17.2-.35.22-.65.07-.3-.15-1.24-.46-2.36-1.46a8.8 8.8 0 0 1-1.63-2.02c-.17-.3 0-.46.13-.6.13-.14.3-.35.44-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.07-.15-.67-1.6-.9-2.2-.24-.58-.5-.5-.68-.5h-.58c-.2 0-.53.07-.8.37-.28.3-1.06 1.03-1.06 2.5s1.08 2.9 1.23 3.1c.15.2 2.13 3.24 5.15 4.55.72.3 1.28.5 1.72.65.72.23 1.38.2 1.9.12.58-.09 1.76-.72 2-1.4.25-.7.25-1.3.17-1.4-.07-.13-.27-.2-.57-.35z"/></svg>';
  var SEND_ICON = '<svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>';

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function BlasWidget() {
    injectStyle();

    var btn = el("button", "blas-bubble-btn", WHATSAPP_ICON);
    var panel = el("div", "blas-panel");
    var header = el("div", "blas-header");
    header.innerHTML =
      '<div class="blas-avatar">B</div>' +
      '<div><div class="blas-title">Blas</div>' +
      '<div class="blas-subtitle">Eficiencia y Precisión Industrial</div></div>' +
      '<button class="blas-close" aria-label="Cerrar">×</button>';
    var body = el("div", "blas-body");
    var inputBar = el("div", "blas-inputbar");
    var input = el("input");
    input.type = "text";
    input.placeholder = "Escribe un mensaje...";
    var sendBtn = el("button", "", SEND_ICON);
    inputBar.appendChild(input);
    inputBar.appendChild(sendBtn);

    panel.appendChild(header);
    panel.appendChild(body);
    panel.appendChild(inputBar);
    document.body.appendChild(btn);
    document.body.appendChild(panel);

    var sessionId = getSessionId();
    var started = false;

    function addMessage(direction, text) {
      var bubble = el("div", "blas-msg " + (direction === "in" ? "user" : "bot"), escapeHtml(text));
      body.appendChild(bubble);
      body.scrollTop = body.scrollHeight;
    }

    function escapeHtml(s) {
      var d = document.createElement("div");
      d.innerText = s;
      return d.innerHTML;
    }

    function renderHistory(messages) {
      body.innerHTML = "";
      messages.forEach(function (m) { addMessage(m.direction, m.body); });
    }

    function start() {
      if (started) return;
      started = true;
      fetch(API_BASE + "/api/v1/widget/start", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ web_session_id: sessionId }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) { renderHistory(data.messages || []); })
        .catch(function () {
          addMessage("out", "No hemos podido conectar con Blas ahora mismo. Prueba de nuevo en un momento.");
        });
    }

    function send() {
      var text = input.value.trim();
      if (!text) return;
      input.value = "";
      addMessage("in", text);
      fetch(API_BASE + "/api/v1/widget/message", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ web_session_id: sessionId, text: text }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) { addMessage("out", data.reply); })
        .catch(function () {
          addMessage("out", "No hemos podido enviar tu mensaje. Prueba de nuevo en un momento.");
        });
    }

    btn.addEventListener("click", function () {
      panel.classList.toggle("open");
      if (panel.classList.contains("open")) { start(); input.focus(); }
    });
    header.querySelector(".blas-close").addEventListener("click", function () {
      panel.classList.remove("open");
    });
    sendBtn.addEventListener("click", send);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", BlasWidget);
  } else {
    BlasWidget();
  }
})();
