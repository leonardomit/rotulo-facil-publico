/* ══════════════════════════════════════════════════════════════════════
   fito-ui.js — camada de UI do Rótulo Fácil (tema claro/escuro)
   Cuida de duas coisas: modo noturno e barra de navegação entre os apps.

   Arquivo idêntico em lotes-dashboard-v2, lotes-dashboard (OPs) e
   rotulo-facil. O dash-comercial usa a versão React equivalente
   (src/components/FitoBar.tsx) — ao mudar aqui, replicar lá.

   Uso no HTML:
     <script src="/static/fito-ui.js"></script>
     <div data-fito-bar data-fito-current="lotes"></div>

   O <html data-theme="..."> precisa ser escrito ANTES da primeira pintura
   pelo trecho inline em fito-theme-inline (ver README do bloco abaixo),
   senão a página pisca em claro antes de virar escura.
   ══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var STORAGE_KEY = 'fito-theme';

  /* ── Ícones ──────────────────────────────────────────────────────────
     Traçado sobre viewBox 24×24, sem preenchimento, herdando a cor do texto
     (currentColor) — o mesmo desenho do painel de OPs. Substituem os emojis,
     que variavam de forma entre sistemas e não acompanhavam a cor do tema. */
  var ICONES = {
    busca:      '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    fabrica:    '<path d="M3 21V10l6 4V10l6 4V7l6 4v10z"/><path d="M3 21h18"/>',
    etiqueta:   '<path d="M20.6 13.4 12 22l-9-9V3h10l7.6 7.6a2 2 0 0 1 0 2.8Z"/><circle cx="7.5" cy="7.5" r="1.3"/>',
    grafico:    '<path d="M3 3v18h18"/><path d="M7 15v3M12 10v8M17 6v12"/>',
    subindo:    '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    caixa:      '<path d="M21 8v8a2 2 0 0 1-1 1.7l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8a2 2 0 0 1 1-1.7l7-4a2 2 0 0 1 2 0l7 4A2 2 0 0 1 21 8Z"/><path d="m3.3 7 8.7 5 8.7-5M12 22V12"/>',
    atualizar:  '<path d="M3 12a9 9 0 0 1 15.4-6.4L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.4 6.4L3 16"/><path d="M3 21v-5h5"/>',
    imprimir:   '<path d="M6 9V3h12v6"/><path d="M6 18H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v7H6z"/>',
    usuario:    '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    cadeado:    '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    chave:      '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9 2 2-2 2 2 2-2 2-2-2-3 3"/>',
    engrenagem: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 7 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H1a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 2.6 7a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H7a1.7 1.7 0 0 0 1-1.5V1a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V7a1.7 1.7 0 0 0 1.5 1H23a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
    alerta:     '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    check:      '<path d="m20 6-11 11-5-5"/>',
    fechar:     '<path d="M18 6 6 18M6 6l12 12"/>',
    olho:       '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    olhoCortado:'<path d="M9.9 4.2A10 10 0 0 1 12 4c6.4 0 10 7 10 7a18 18 0 0 1-3 4M6 6a18 18 0 0 0-4 5s3.6 7 10 7a10 10 0 0 0 4.5-1"/><path d="m2 2 20 20"/>',
    documento:  '<path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7Z"/><path d="M14 2v5h5"/>',
    banco:      '<path d="m3 10 9-6 9 6"/><path d="M5 10v9M10 10v9M14 10v9M19 10v9"/><path d="M3 21h18"/>',
    folha:      '<path d="M11 20A7 7 0 0 1 4 13c0-6 5-9 16-10 0 10-4 17-9 17Z"/><path d="M6 21c1-6 4-9 9-11"/>',
    lista:      '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6M9 16h6"/>',
    frasco:     '<path d="M9 2v6L4 19a2 2 0 0 0 1.8 3h12.4A2 2 0 0 0 20 19L15 8V2"/><path d="M8 2h8M7 15h10"/>',
    lapis:      '<path d="M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>',
    relogio:    '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    proibido:   '<circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/>',
    sol:        '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4"/>',
    lua:        '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>'
  };

  /** Devolve o SVG do ícone como texto, para montar HTML. */
  function icone(nome, classe) {
    var d = ICONES[nome];
    if (!d) return '';
    return '<svg class="fito-icon' + (classe ? ' ' + classe : '') + '" viewBox="0 0 24 24" ' +
           'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
           'stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
  }

  /* Barra de apps desativada nesta distribuição — adicione seus painéis aqui se desejar. */
  var APPS = [];

  /* Cada app escuta em todas as interfaces, então responde no mesmo host por
     onde o usuário chegou — seja localhost, o IP da LAN ou o nome do Tailscale.
     Só a porta muda. (Pelo Tailscale o tráfego já vai cifrado pelo WireGuard,
     por isso http aqui não expõe nada na rede.) */
  function appUrl(port) {
    return 'http://' + window.location.hostname + ':' + port + '/';
  }

  /* ── Tema ────────────────────────────────────────────────────────── */

  /* A preferência vive num cookie, não em localStorage: localStorage é isolado
     por origem, e cada painel roda numa porta diferente — a escolha não passaria
     de um app para o outro. Cookie ignora a porta, então o mesmo host serve os
     quatro com uma escolha só. */
  function storedTheme() {
    var m = document.cookie.match(/(?:^|;\s*)fito-theme=(dark|light)/);
    return m ? m[1] : null;
  }

  function saveTheme(theme) {
    // 1 ano; Lax basta porque só é lido em navegação de primeira parte.
    document.cookie = STORAGE_KEY + '=' + theme + ';path=/;max-age=31536000;SameSite=Lax';
  }

  function systemTheme() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark' : 'light';
  }

  function currentTheme() {
    return document.documentElement.getAttribute('data-theme') || storedTheme() || systemTheme();
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    /* O Bootstrap 5.3 tem modo escuro próprio, acionado por este atributo; é o
       que reveste tabelas, formulários e dropdowns no Rótulo Fácil. Nos painéis
       sem Bootstrap o atributo fica inerte. */
    document.documentElement.setAttribute('data-bs-theme', theme);
    var escuro = theme === 'dark';
    var botoes = document.querySelectorAll('[data-fito-theme-toggle]');
    for (var i = 0; i < botoes.length; i++) {
      var b = botoes[i];
      b.setAttribute('aria-pressed', escuro ? 'true' : 'false');
      var rotulo = escuro ? 'Mudar para modo claro' : 'Mudar para modo noturno';
      b.setAttribute('aria-label', rotulo);
      b.setAttribute('title', rotulo);
      b.innerHTML = icone(escuro ? 'sol' : 'lua');
    }
    /* Quem desenha com cores lidas do CSS (ex.: gráficos Chart.js) precisa
       redesenhar quando o tema troca — só o CSS não alcança o <canvas>. */
    try {
      document.dispatchEvent(new CustomEvent('fito:themechange', { detail: { theme: theme } }));
    } catch (e) { /* navegador antigo sem CustomEvent construível */ }
  }

  function toggleTheme() {
    var novo = currentTheme() === 'dark' ? 'light' : 'dark';
    saveTheme(novo);
    applyTheme(novo);
  }

  /* Enquanto o usuário não escolher manualmente, seguimos o sistema ao vivo. */
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var aoMudar = function (e) { if (!storedTheme()) applyTheme(e.matches ? 'dark' : 'light'); };
    if (mq.addEventListener) mq.addEventListener('change', aoMudar);
    else if (mq.addListener) mq.addListener(aoMudar);
  }

  /* ── Barra de apps ───────────────────────────────────────────────── */

  function montarBarra(container) {
    var atual = container.getAttribute('data-fito-current') || '';
    var noEscuro = container.hasAttribute('data-fito-on-dark');
    /* data-fito-hide="comercial,ops" omite painéis desta barra — os painéis de
       operação não linkam para painéis de outro domínio. */
    var ocultos = (container.getAttribute('data-fito-hide') || '')
      .split(',').map(function (s) { return s.trim(); }).filter(Boolean);

    container.classList.add('fito-bar');
    if (noEscuro) container.classList.add('fito-bar--on-dark');
    container.innerHTML = '';

    APPS.filter(function (app) {
      return ocultos.indexOf(app.key) === -1;
    }).forEach(function (app) {
      var ehAtual = app.key === atual;
      // O app atual vira <span>: clicar nele recarregaria a página à toa.
      var el = document.createElement(ehAtual ? 'span' : 'a');
      el.className = 'fito-app';
      if (ehAtual) {
        el.setAttribute('aria-current', 'page');
      } else {
        el.href = appUrl(app.port);
        el.title = 'Abrir ' + app.label;
      }
      el.innerHTML = icone(app.icon) + '<span>' + app.label + '</span>';
      container.appendChild(el);
    });

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'fito-theme-btn';
    btn.setAttribute('data-fito-theme-toggle', '');
    container.appendChild(btn);
  }

  /* Links avulsos para outro app: <a data-fito-link="ops">…</a>.
     O href é preenchido aqui pelo mesmo motivo da barra — depende do host. */
  function preencherLinks() {
    var links = document.querySelectorAll('[data-fito-link]');
    for (var i = 0; i < links.length; i++) {
      var chave = links[i].getAttribute('data-fito-link');
      for (var j = 0; j < APPS.length; j++) {
        if (APPS[j].key === chave) {
          links[i].href = appUrl(APPS[j].port);
          break;
        }
      }
    }
  }

  function init() {
    var barras = document.querySelectorAll('[data-fito-bar]');
    for (var i = 0; i < barras.length; i++) montarBarra(barras[i]);
    preencherLinks();
    applyTheme(currentTheme());
  }

  /* Delegação: pega também botões inseridos depois do carregamento. */
  document.addEventListener('click', function (e) {
    var alvo = e.target;
    while (alvo && alvo !== document) {
      if (alvo.hasAttribute && alvo.hasAttribute('data-fito-theme-toggle')) {
        e.preventDefault();
        toggleTheme();
        return;
      }
      alvo = alvo.parentNode;
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.FitoUI = { toggleTheme: toggleTheme, currentTheme: currentTheme, appUrl: appUrl, APPS: APPS, icone: icone };
})();
