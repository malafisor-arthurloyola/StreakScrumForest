/* Controle da rodada de fala na tela Hoje (so o Scrum/administrador).
   Sorteia a ordem e, a cada pessoa, acende o holofote (o painel e as plantas ficam em holofote.js).
   A ordem sorteada vai para o servidor junto com o holofote: todas as telas mostram quem vem a seguir,
   e outro aparelho do Scrum que abrir a tela Hoje continua a mesma rodada. */
(function () {
  var box = document.getElementById('rodada');
  if (!box) return;
  var DATA = box.dataset.data;
  var EH_HOJE = box.dataset.hoje === '1';
  // hoje, depois das 15h45 abre na Day Closing; num dia que ja passou, abre na Daily
  var TIPO = (EH_HOJE && new Date().getHours() * 60 + new Date().getMinutes() >= 15 * 60 + 45) ? 'fechamento' : 'daily';
  var chipsTipo = document.querySelectorAll('#rodada-tipo [data-tipo]');
  function chave() { return 'rodada-hoje:' + DATA + ':' + TIPO; }
  var painel = document.getElementById('rodada-painel');
  var botIni = document.getElementById('rodada-iniciar');
  var estado = null;      // { ordem: [ids], i: n, modo: 'celular' | 'scrum' }
  var nomes = {};

  document.querySelectorAll('.canteiro-item').forEach(function (it) {
    var a = it.querySelector('.placa-nome');
    if (a) nomes[it.dataset.memberId] = a.textContent.trim();
  });

  function ler() { try { return JSON.parse(localStorage.getItem(chave())); } catch (e) { return null; } }
  function gravar() { try { if (estado) localStorage.setItem(chave(), JSON.stringify(estado)); else localStorage.removeItem(chave()); } catch (e) {} }
  function postar(url, corpo) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); });
  }
  function estadoDaAta() {
    return fetch('/api/ata/estado?data=' + DATA + '&tipo=' + TIPO).then(function (r) { return r.json(); });
  }
  function statusDe(res, mid) {
    var l = ((res && res.linhas) || []).filter(function (x) { return String(x.id) === String(mid); })[0];
    return l ? (l.status || '') : '';
  }
  function embaralhar(ids) {
    for (var i = ids.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1)); var t = ids[i]; ids[i] = ids[j]; ids[j] = t;
    }
    return ids;
  }

  function acender() {
    postar('/api/holofote', {
      member_id: parseInt(estado.ordem[estado.i], 10), modo: estado.modo, tipo: TIPO, data: DATA,
      ordem: estado.ordem.map(function (x) { return parseInt(x, 10); }),
    })
      .then(function () { document.dispatchEvent(new Event('holofote:refresh')); });
  }

  function desenharTipo() {
    chipsTipo.forEach(function (b) {
      var ativo = b.dataset.tipo === TIPO;
      b.setAttribute('aria-pressed', ativo ? 'true' : 'false');
      b.disabled = !!estado;            // so troca de reuniao entre rodadas
    });
  }

  function mostrar() {
    desenharTipo();
    if (!estado) { painel.hidden = true; botIni.hidden = false; return; }
    var mid = estado.ordem[estado.i];
    var nome = nomes[mid] || 'Pessoa';
    botIni.hidden = true; painel.hidden = false;
    document.getElementById('rodada-prog').textContent = 'Pessoa ' + (estado.i + 1) + ' de ' + estado.ordem.length;
    document.getElementById('rodada-nome').textContent = 'Vez de ' + nome;
    document.getElementById('rodada-ant').disabled = estado.i === 0;
    document.getElementById('rodada-prox').textContent = estado.i === estado.ordem.length - 1 ? 'Terminar a rodada' : 'Próxima pessoa';
    document.getElementById('rodada-modo').textContent = estado.modo === 'scrum'
      ? 'Você está preenchendo por ' + nome + '. O texto aparece na tela de todos.'
      : nome + ' preenche no próprio celular (precisa estar logado em Meu jardim). O texto aparece na tela de todos.';
    document.getElementById('rodada-trocar').textContent = estado.modo === 'scrum'
      ? 'Deixar ' + nome + ' preencher' : 'Preencher por ' + nome;
    estadoDaAta().then(function (res) {
      var st = statusDe(res, mid);
      document.querySelectorAll('#rodada-status [data-rst]').forEach(function (b) {
        b.setAttribute('aria-pressed', st === b.dataset.rst ? 'true' : 'false');
      });
    }).catch(function () {});
    acender();
    gravar();
  }

  function encerrar(aviso) {
    estado = null; gravar(); mostrar();
    postar('/api/holofote', { member_id: null }).then(function () { document.dispatchEvent(new Event('holofote:refresh')); });
    if (aviso && window.Som) Som.tocar('rodadaFim');
    if (aviso && window.mostrarToast) mostrarToast('Rodada concluída. Quem ainda não preencheu pode usar o QR ou o Meu jardim.', 'info');
  }

  function avancar() {
    if (!estado) return;
    if (estado.i >= estado.ordem.length - 1) { encerrar(true); return; }
    estado.i++; estado.modo = 'celular'; mostrar();
  }

  function comecar() {
    estadoDaAta().then(function (res) {
      var ids = Object.keys(nomes).filter(function (mid) {
        var st = statusDe(res, mid);
        return st !== 'justificada' && st !== 'faltou';
      });
      if (!ids.length) { if (window.mostrarToast) mostrarToast('Todos já estão marcados como avisou ou faltou.', 'info'); return; }
      estado = { ordem: embaralhar(ids), i: 0, modo: 'celular' };
      if (window.Som) Som.tocar('sorteio');
      // quem conduz vira o relator da ata (se ainda nao ha um): assim o bonus de relator vale
      postar('/api/ata/assumir', { data: DATA, tipo: TIPO });
      mostrar();
    });
  }

  botIni.addEventListener('click', comecar);
  document.getElementById('rodada-sortear').addEventListener('click', comecar);
  document.getElementById('rodada-ant').addEventListener('click', function () {
    if (estado && estado.i > 0) { estado.i--; estado.modo = 'celular'; mostrar(); }
  });
  document.getElementById('rodada-prox').addEventListener('click', avancar);
  document.getElementById('rodada-fim').addEventListener('click', function () { encerrar(false); });
  document.getElementById('rodada-trocar').addEventListener('click', function () {
    if (!estado) return;
    estado.modo = estado.modo === 'scrum' ? 'celular' : 'scrum';
    mostrar();
  });
  document.querySelectorAll('#rodada-status [data-rst]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (!estado) return;
      var mid = estado.ordem[estado.i];
      var novo = b.getAttribute('aria-pressed') === 'true' ? '' : b.dataset.rst;
      if (window.Som && novo !== 'presente') Som.tocar('neutro');
      postar('/api/ata/salvar', { data: DATA, tipo: TIPO, campo: 'status', member_id: mid, valor: novo }).then(function (res) {
        if (!res.ok) { if (window.mostrarToast) mostrarToast((res.j && res.j.erro) || 'Não salvou.', 'info'); return; }
        if (res.j.jogo_resposta && window.aplicarJogoNaTela) aplicarJogoNaTela(res.j.jogo_resposta, nomes[mid]);
        if (novo === 'justificada' || novo === 'faltou') setTimeout(avancar, 450); else mostrar();
      });
    });
  });

  // quem esta no painel marcou Avisou ou Faltou: segue para a proxima pessoa (se ainda for a mesma da vez)
  document.addEventListener('holofote:avancar', function (e) {
    if (!estado || !e.detail) return;
    if (String(estado.ordem[estado.i]) === String(e.detail.id)) avancar();
  });

  // o Scrum trocou "quem preenche" pelo proprio painel: a rodada passa a lembrar disso
  document.addEventListener('holofote:modo', function (e) {
    if (!estado || !e.detail) return;
    estado.modo = e.detail.modo; gravar(); mostrar();
  });

  chipsTipo.forEach(function (b) {
    b.addEventListener('click', function () {
      if (estado || b.dataset.tipo === TIPO) return;
      TIPO = b.dataset.tipo;
      estado = ler();
      if (estado && (!estado.ordem || !estado.ordem.length || estado.i >= estado.ordem.length)) estado = null;
      mostrar();
    });
  });

  estado = ler();
  if (estado && (!estado.ordem || !estado.ordem.length || estado.i >= estado.ordem.length)) estado = null;
  if (estado) { mostrar(); return; }
  desenharTipo();
  // sem rodada neste navegador: se outra tela do Scrum ja comecou uma hoje, continua dela
  fetch('/api/holofote').then(function (r) { return r.json(); }).then(function (j) {
    if (estado || !j || !j.member_id || j.data !== DATA || !j.ordem || !j.ordem.length || j.pos === null) return;
    TIPO = j.tipo;
    estado = { ordem: j.ordem.map(function (p) { return String(p.id); }), i: j.pos, modo: j.modo };
    j.ordem.forEach(function (p) { if (!nomes[p.id]) nomes[p.id] = p.nome; });
    mostrar();
  }).catch(function () {});
})();
