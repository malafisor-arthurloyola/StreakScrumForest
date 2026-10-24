/* Defesa extra de CSRF: todo pedido que altera dados leva um cabecalho que so o proprio
   site envia (o servidor exige esse cabecalho quando o codigo de acesso esta ativo). */
(function () {
  var original = window.fetch;
  window.fetch = function (url, opcoes) {
    opcoes = opcoes || {};
    var metodo = (opcoes.method || 'GET').toUpperCase();
    if (metodo !== 'GET' && metodo !== 'HEAD') {
      opcoes.headers = Object.assign({ 'X-Requested-With': 'fetch' }, opcoes.headers || {});
    }
    return original.call(this, url, opcoes);
  };
})();

var CORES_CONFETE = ['#c6f24e', '#6db9ff', '#ff9ec4', '#ffd35c', '#4fdb9b', '#ff8d76'];
var CORES_CHAMA = ['#ff7a1a', '#ffd35c', '#ff4d2e', '#ffe9a8'];
var MARCOS_SEQUENCIA = [3, 5, 7, 10, 14, 20, 30, 40];

function mostrarToast(msg, tipo) {
  var container = document.getElementById('toast-container');
  if (!container) return;
  var t = document.createElement('div');
  t.className = 'toast toast-' + (tipo || 'info');
  t.textContent = msg;
  container.appendChild(t);
  requestAnimationFrame(function () { t.classList.add('toast-visivel'); });
  setTimeout(function () {
    t.classList.remove('toast-visivel');
    setTimeout(function () { t.remove(); }, 300);
  }, 3600);
}

function rotuloDias(n) {
  return n === 1 ? 'dia' : 'dias';
}

/* -------------------------------------------------------------- dia cheio (1.2)
   Celebracao quando o dia passa de "nao cheio" para "cheio" durante o uso da tela.
   Nunca dispara ao abrir/recarregar: o estado inicial vem do servidor em
   data-dia-cheio-inicial. Nao repete na mesma sessao (sessionStorage). */
var diaCheioAnterior = (function () {
  var sec = document.querySelector('.registro[data-dia-data]');
  return sec ? sec.dataset.diaCheioInicial === 'true' : false;
})();

function dataVista() {
  var sec = document.querySelector('.registro[data-dia-data]');
  return sec ? sec.dataset.diaData : '';
}

function jaCelebrou(data) {
  try { return sessionStorage.getItem('jardim.diaCheio.' + data) === '1'; }
  catch (e) { return false; }
}

function marcarCelebrado(data) {
  try { sessionStorage.setItem('jardim.diaCheio.' + data, '1'); } catch (e) {}
}

function prefereSemMovimento() {
  return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function fecharCelebracao(el) {
  if (!el || el.dataset.fechando) return;
  el.dataset.fechando = '1';
  el.classList.remove('visivel');
  setTimeout(function () { el.remove(); }, 400);
}

function celebrarDiaCheio() {
  var data = dataVista();
  if (jaCelebrou(data)) return;
  marcarCelebrado(data);

  if (prefereSemMovimento()) {
    // Sem movimento: so um aviso fixo e discreto, sem tela cheia nem peatalas.
    mostrarToast('Dia cheio! +1 semente para todos.', 'sucesso');
    return;
  }

  var tela = document.createElement('div');
  tela.className = 'dia-cheio-festa';
  tela.setAttribute('role', 'status');
  tela.setAttribute('aria-live', 'polite');

  var petalas = document.createElement('div');
  petalas.className = 'dc-petalas';
  petalas.setAttribute('aria-hidden', 'true');
  var cores = ['#ff9ec4', '#ffd35c', '#c6f24e', '#6db9ff', '#ff8d76'];
  for (var i = 0; i < 28; i++) {
    var p = document.createElement('i');
    p.style.left = Math.random() * 100 + '%';
    p.style.background = cores[i % cores.length];
    p.style.setProperty('--atraso', (Math.random() * 1.2).toFixed(2) + 's');
    p.style.setProperty('--giro', (Math.random() * 360).toFixed(0) + 'deg');
    p.style.setProperty('--desvio', (Math.random() * 60 - 30).toFixed(0) + 'px');
    petalas.appendChild(p);
  }

  var msg = document.createElement('div');
  msg.className = 'dc-msg';
  msg.innerHTML = '<strong>Dia cheio!</strong><span>+1 semente para todos</span>';

  tela.appendChild(petalas);
  tela.appendChild(msg);
  document.body.appendChild(tela);
  requestAnimationFrame(function () { tela.classList.add('visivel'); });

  // Dispensa por clique ou Esc, e some sozinha em ~3,5s.
  tela.addEventListener('click', function () { fecharCelebracao(tela); });
  function porEsc(ev) {
    if (ev.key === 'Escape') { fecharCelebracao(tela); document.removeEventListener('keydown', porEsc); }
  }
  document.addEventListener('keydown', porEsc);
  setTimeout(function () { fecharCelebracao(tela); document.removeEventListener('keydown', porEsc); }, 3500);
}

/* Olha a flag dia_cheio da resposta da API e celebra so na transicao nao-cheio -> cheio. */
function verificarDiaCheio(data) {
  if (data.dia_cheio === undefined) return;
  var agora = !!data.dia_cheio;
  if (agora && !diaCheioAnterior) celebrarDiaCheio();
  diaCheioAnterior = agora;
}

function confete(memberId, cores) {
  var item = document.querySelector('.canteiro-item[data-member-id="' + memberId + '"]');
  if (!item) return;
  var paleta = cores || CORES_CONFETE;
  var caixa = document.createElement('div');
  caixa.className = 'confete';
  caixa.setAttribute('aria-hidden', 'true');
  for (var i = 0; i < 18; i++) {
    var p = document.createElement('i');
    var ang = (Math.PI * 2 * i) / 18 + Math.random() * 0.4;
    var dist = 46 + Math.random() * 54;
    p.style.setProperty('--dx', Math.cos(ang) * dist + 'px');
    p.style.setProperty('--dy', Math.sin(ang) * dist - 30 + 'px');
    p.style.background = paleta[i % paleta.length];
    caixa.appendChild(p);
  }
  item.appendChild(caixa);
  setTimeout(function () { caixa.remove(); }, 1100);
}

/* Ceu que acompanha a hora. Mesma regra de game.periodo_do_dia (Python). */
function periodoPorHora(h) {
  if (h < 5) return 'madrugada';
  if (h < 7.5) return 'amanhecer';
  if (h < 12) return 'manha';
  if (h < 14) return 'meiodia';
  if (h < 17.5) return 'tarde';
  if (h < 19) return 'entardecer';
  return 'noite';
}

function posicaoAstro(h, inicio, duracao) {
  var t = (((h - inicio) % 24) + 24) % 24 / duracao;
  t = Math.min(Math.max(t, 0), 1);
  return [8 + 84 * t, 66 - 56 * Math.sin(Math.PI * t)];
}

function atualizarCena() {
  var d = new Date();
  var h = d.getHours() + d.getMinutes() / 60;
  var periodo = periodoPorHora(h);
  var sol = posicaoAstro(h, 5.5, 13);
  var lua = posicaoAstro(h, 18.5, 11);
  document.querySelectorAll('.cena').forEach(function (c) {
    c.dataset.periodo = periodo;
    c.style.setProperty('--sx', sol[0].toFixed(1) + '%');
    c.style.setProperty('--sy', sol[1].toFixed(1) + '%');
    c.style.setProperty('--lx', lua[0].toFixed(1) + '%');
    c.style.setProperty('--ly', lua[1].toFixed(1) + '%');
  });
}
atualizarCena();
setInterval(atualizarCena, 60000);

function aplicarEstagioPrincipal(jogo) {
  var anterior = { estagio: 0, dia: null };
  document.querySelectorAll('.planta[data-member-id="' + jogo.id + '"]').forEach(function (svg) {
    anterior.estagio = parseInt(svg.dataset.stage, 10) || 0;
    anterior.dia = svg.dataset.dia;
    svg.dataset.stage = jogo.estagio;
    svg.dataset.vigor = jogo.vigor;
    svg.dataset.frutos = jogo.frutos;
    svg.dataset.floresceu = jogo.floresceu ? 'true' : 'false';
    svg.dataset.dia = jogo.dia_status;
    svg.style.setProperty('--p', jogo.progresso);
    svg.querySelectorAll('[data-min]').forEach(function (g) {
      var min = parseInt(g.dataset.min, 10);
      var max = g.dataset.max ? parseInt(g.dataset.max, 10) : 99;
      g.classList.toggle('on', jogo.estagio >= min && jogo.estagio <= max);
    });
    svg.querySelectorAll('[data-prog]').forEach(function (g) {
      g.classList.toggle('on', jogo.estagio >= 1 && jogo.progresso >= parseFloat(g.dataset.prog));
    });
    svg.querySelectorAll('[data-fruto]').forEach(function (f) {
      f.classList.toggle('on', (jogo.frutos || 0) >= parseInt(f.dataset.fruto, 10));
    });
  });
  return anterior;
}

/* Plantinhas extras (compradas na loja) acompanham a principal, um pouco menores. */
function aplicarEstagio(jogo) {
  var anterior = aplicarEstagioPrincipal(jogo);
  var estExtra = Math.floor(jogo.estagio * 7 / 10);
  document.querySelectorAll('.planta[data-extra-de="' + jogo.id + '"]').forEach(function (svg) {
    svg.dataset.stage = estExtra;
    svg.dataset.vigor = jogo.vigor;
    svg.querySelectorAll('[data-min]').forEach(function (g) {
      var min = parseInt(g.dataset.min, 10);
      var max = g.dataset.max ? parseInt(g.dataset.max, 10) : 99;
      g.classList.toggle('on', estExtra >= min && estExtra <= max);
    });
  });
  return anterior;
}

function atualizarSementes(jogo) {
  if (jogo.sementes === undefined) return;
  document.querySelectorAll('[data-sementes-for="' + jogo.id + '"] b').forEach(function (b) {
    var antes = parseInt(b.textContent, 10) || 0;
    b.textContent = jogo.sementes;
    if (jogo.sementes > antes) {
      var mais = document.createElement('span');
      mais.className = 'sementes-mais';
      mais.textContent = '+' + (jogo.sementes - antes);
      b.parentElement.appendChild(mais);
      setTimeout(function () { mais.remove(); }, 1300);
    }
  });
}

/* Atualiza o contador de sementes de todos os membros da lista (cada item tem id e
   sementes). Usado quando marcar um evento fecha o dia cheio: todos ganham +1, nao
   so quem foi marcado. Reaproveita a animacao de "+N" de atualizarSementes. */
function atualizarSementesTodos(lista) {
  if (!lista) return;
  lista.forEach(function (m) { atualizarSementes(m); });
}

function regar(memberId) {
  document.querySelectorAll('.planta[data-member-id="' + memberId + '"]').forEach(function (svg) {
    svg.classList.remove('regando');
    void svg.getBoundingClientRect();
    svg.classList.add('regando');
    setTimeout(function () { svg.classList.remove('regando'); }, 1500);
  });
}

function atualizarChama(jogo) {
  var anteriorStreak = 0;
  document.querySelectorAll('.chama[data-membro="' + jogo.id + '"]').forEach(function (el) {
    anteriorStreak = parseInt(el.dataset.streak, 10) || 0;
    el.dataset.tier = jogo.chama;
    el.dataset.streak = jogo.streak;
    el.dataset.aceso = jogo.aceso ? 'true' : 'false';
    var n = el.querySelector('.chama-n');
    if (n) n.textContent = jogo.streak;
    var un = el.querySelector('.chama-un');
    if (un) un.textContent = ' ' + rotuloDias(jogo.streak);
  });
  return anteriorStreak;
}

function atualizarProximo(jogo) {
  document.querySelectorAll('[data-prox-barra="' + jogo.id + '"]').forEach(function (b) {
    b.style.width = Math.round(jogo.progresso * 100) + '%';
  });
  document.querySelectorAll('[data-prox-for="' + jogo.id + '"]').forEach(function (el) {
    if (jogo.floresceu) el.textContent = 'Floresceu';
    else if (jogo.dias_ate_proximo) el.textContent = 'faltam ' + jogo.dias_ate_proximo + ' ' + rotuloDias(jogo.dias_ate_proximo);
    else el.textContent = '';
  });
  document.querySelectorAll('[data-estagio-for="' + jogo.id + '"]').forEach(function (el) {
    el.textContent = jogo.estagio_nome;
  });
}

function atualizarSemana(jogo) {
  document.querySelectorAll('.semana[data-semana-for="' + jogo.id + '"] .dia-pt[data-data="' + jogo.data + '"]').forEach(function (p) {
    p.dataset.estado = jogo.dia_estado;
  });
}

document.querySelectorAll('.status-toggle').forEach(function (wrapper) {
  wrapper.querySelectorAll('.btn-status').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var jaAtivo = btn.classList.contains('active');
      var novoStatus = jaAtivo ? null : btn.dataset.status;

      fetch('/api/attendance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          member_id: parseInt(wrapper.dataset.memberId, 10),
          event_date: wrapper.dataset.eventDate,
          event_type: wrapper.dataset.eventType,
          status: novoStatus,
        }),
      })
        .then(function (r) {
          if (!r.ok) throw new Error('Falha ao salvar');
          return r.json();
        })
        .then(function (data) {
          wrapper.querySelectorAll('.btn-status').forEach(function (b) {
            b.classList.remove('active');
          });
          if (novoStatus) btn.classList.add('active');

          if (!data.jogo) return;
          var j = data.jogo;
          var antes = aplicarEstagio(j);
          var streakAntes = atualizarChama(j);
          atualizarProximo(j);
          atualizarSemana(j);
          // Atualiza o contador de todos os ativos (dia cheio da +1 para todos);
          // se o servidor nao mandar a lista, cai no do membro marcado.
          if (data.sementes_membros) atualizarSementesTodos(data.sementes_membros);
          else atualizarSementes(j);
          verificarDiaCheio(data);

          var nome = '';
          var linha = wrapper.closest('[data-member-row]');
          if (linha) {
            var el = linha.querySelector('.linha-nome');
            if (el) nome = el.textContent.trim();
          }

          if (j.dia_status === 'regada' && antes.dia !== 'regada') {
            regar(j.id);
          }

          if (j.estagio > antes.estagio) {
            confete(j.id);
            mostrarToast((nome ? nome + ' chegou ao estágio ' : 'Chegou ao estágio ') + j.estagio + ': ' + j.estagio_nome, 'sucesso');
          }

          if (j.streak > streakAntes && MARCOS_SEQUENCIA.indexOf(j.streak) !== -1) {
            confete(j.id, CORES_CHAMA);
            mostrarToast((nome ? nome + ': ' : '') + j.streak + ' dias seguidos!', 'sucesso');
          }
        })
        .catch(function () {
          alert('Não foi possível salvar. Verifique se o servidor ainda está rodando.');
        });
    });
  });
});

/* Convidados no jardim (Hoje e Painel): 3 modos (ocultos, em faixa ou no fundo do jardim),
   lembrados no localStorage (com try/catch). Os dados de cada convidado aparecem num cartao
   que sobe ao passar o mouse (e abre/fecha por toque no celular). */
(function () {
  var bloco = document.querySelector('.jardim-bloco[data-tem-convidados="true"]');
  if (!bloco) return;
  var KEY = 'jardim.modoConvidados';
  var MODOS = ['oculto', 'faixa', 'fundo'];
  var cena = bloco.querySelector('.jardim-cena');
  var botoes = bloco.querySelectorAll('.chip-modo');

  function aplicar(modo) {
    if (MODOS.indexOf(modo) < 0) modo = 'fundo';
    MODOS.forEach(function (m) { if (cena) cena.classList.toggle('modo-' + m, m === modo); });
    botoes.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.modo === modo ? 'true' : 'false'); });
    try { localStorage.setItem(KEY, modo); } catch (e) {}
    posicionarFundo();
    esconder();
  }

  // Convidados "no fundo": ficam nas frestas reais entre os vasos do time.
  function posicionarFundo() {
    var linha = bloco.querySelector('.cena-plantas');
    if (!linha) return;
    var itens = linha.querySelectorAll('.canteiro-item');
    var guests = linha.querySelectorAll('.conv-fundo');
    if (itens.length === 0 || guests.length === 0) return;
    var planta = linha.querySelector('.canteiro-item .planta');
    if (planta) {
      var h = linha.getBoundingClientRect().bottom - planta.getBoundingClientRect().bottom;
      if (h > 0) linha.style.setProperty('--placa-h', Math.round(h) + 'px');
    }
    var n = itens.length;
    var contagem = {};
    guests.forEach(function (g) { var k = g.dataset.gap; contagem[k] = (contagem[k] || 0) + 1; });
    var visto = {};
    guests.forEach(function (g) {
      var gap = Math.max(0, Math.min(parseInt(g.dataset.gap, 10) || 0, n));
      var x;
      if (gap === 0) { x = itens[0].offsetLeft + 6; }
      else if (gap >= n) { x = itens[n - 1].offsetLeft + itens[n - 1].offsetWidth - 6; }
      else { x = (itens[gap - 1].offsetLeft + itens[gap - 1].offsetWidth + itens[gap].offsetLeft) / 2; }
      // varios convidados na mesma fresta: abre um leque curto para nao empilhar
      var total = contagem[g.dataset.gap], i = visto[g.dataset.gap] || 0;
      visto[g.dataset.gap] = i + 1;
      x += (i - (total - 1) / 2) * 34;
      g.style.left = Math.round(x) + 'px';
    });
  }

  var tip = document.createElement('div');
  tip.className = 'conv-tip';
  tip.setAttribute('role', 'tooltip');
  tip.innerHTML = '<div class="conv-tip-topo"><b class="t-nome"></b><span class="chip chip-convidado">convidado</span></div>' +
    '<dl><div><dt>Sequência</dt><dd><svg class="chama-svg" viewBox="0 0 24 24" aria-hidden="true"><use href="#p-chama" class="chama-corpo"/><use href="#p-chama-miolo" class="chama-miolo"/></svg><span class="t-seq"></span></dd></div>' +
    '<div><dt>Estágio</dt><dd class="t-estagio"></dd></div>' +
    '<div><dt>Sementes</dt><dd class="t-sementes"></dd></div></dl>' +
    '<a class="t-link" href="#">Ver perfil</a>';
  document.body.appendChild(tip);
  var atual = null, timer = null;

  function esconder() {
    clearTimeout(timer);
    tip.classList.remove('visivel');
    document.querySelectorAll('.convidado-tip.aberto').forEach(function (o) { o.classList.remove('aberto'); });
    atual = null;
  }
  function agendarEsconder() { clearTimeout(timer); timer = setTimeout(esconder, 220); }

  function mostrar(alvo) {
    clearTimeout(timer);
    if (atual && atual !== alvo) atual.classList.remove('aberto');
    atual = alvo; alvo.classList.add('aberto');
    var d = alvo.dataset, n = parseInt(d.streak, 10);
    tip.querySelector('.t-nome').textContent = d.nome;
    tip.querySelector('.t-seq').textContent = n + (n === 1 ? ' dia' : ' dias');
    tip.querySelector('.t-estagio').textContent = d.estagio;
    tip.querySelector('.t-sementes').textContent = d.sementes;
    tip.querySelector('.t-link').href = d.perfil;
    tip.classList.remove('abaixo');
    tip.classList.add('visivel');
    var r = alvo.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    var cx = r.left + r.width / 2;
    var left = Math.max(8, Math.min(cx - w / 2, window.innerWidth - w - 8));
    var top = r.top - h - 12;
    if (top < 8) { top = r.bottom + 12; tip.classList.add('abaixo'); }
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
    tip.style.setProperty('--seta', Math.round(cx - left) + 'px');
  }

  bloco.querySelectorAll('.convidado-tip').forEach(function (el) {
    el.addEventListener('mouseenter', function () { mostrar(el); });
    el.addEventListener('mouseleave', agendarEsconder);
    el.addEventListener('focus', function () { mostrar(el); });
    el.addEventListener('blur', agendarEsconder);
    el.addEventListener('click', function (e) {      // toque no celular (sem hover)
      e.stopPropagation();
      mostrar(el);
    });
  });
  tip.addEventListener('mouseenter', function () { clearTimeout(timer); });
  tip.addEventListener('mouseleave', agendarEsconder);
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.convidado-tip') && !e.target.closest('.conv-tip')) esconder();
  });
  window.addEventListener('resize', function () { posicionarFundo(); esconder(); });
  window.addEventListener('scroll', esconder, { passive: true });
  var linhaScroll = bloco.querySelector('.cena-plantas');
  if (linhaScroll) linhaScroll.addEventListener('scroll', esconder, { passive: true });

  var salvo = 'fundo';
  try { var v = localStorage.getItem(KEY); if (v) salvo = v; } catch (e) {}
  aplicar(salvo);
  botoes.forEach(function (b) { b.addEventListener('click', function () { aplicar(b.dataset.modo); }); });
  window.addEventListener('load', posicionarFundo);
})();
