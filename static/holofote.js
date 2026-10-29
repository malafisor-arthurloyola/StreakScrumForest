/* Holofote da rodada de fala da Daily.
   Quem conduz (o Scrum) acende a planta de quem esta falando. Em todas as telas abertas:
   - a planta ganha o destaque e o resto da tela escurece um pouco;
   - aparece um painel com os tres campos da daily e os cards sugeridos do GitLab.
   Quem preenche: por padrao a propria pessoa, no celular dela (e todos veem o texto aparecer);
   o Scrum pode assumir e preencher por ela (e ganha o bonus de relator, como na ata). */
(function () {
  // campos e origem dos cards sugeridos, por tipo de ata (a Day Closing nao tem o campo de revisao)
  var CAMPOS_POR_TIPO = {
    daily: [
      ['feito', 'O que eu fiz de ontem para hoje', 'fiz'],
      ['planejado', 'O que vou fazer hoje', 'fazer'],
      ['review', 'Cards aguardando revisão', 'revisar'],
    ],
    fechamento: [
      ['feito', 'O que concluí hoje', 'concluidos'],
      ['planejado', 'O que fica para amanhã', 'fazer'],
    ],
  };
  function campos(j) { return CAMPOS_POR_TIPO[j.tipo] || CAMPOS_POR_TIPO.daily; }
  function cardsDe(res, origem) {
    if (origem === 'concluidos') {          // Day Closing: o que concluiu hoje pode ainda estar em Doing
      var vistos = {};
      return (res.fazer || []).concat(res.fiz || []).filter(function (c) { if (vistos[c.iid]) return false; vistos[c.iid] = true; return true; });
    }
    return res[origem] || [];
  }
  var pop = null;
  var chave = '';
  var escondido = null;
  var cacheCards = {};
  var timers = {};

  function postar(url, corpo) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); });
  }

  function destacarPlantas(mid) {
    document.querySelectorAll('.cena').forEach(function (c) { c.classList.toggle('holofote-ativo', !!mid); });
    document.querySelectorAll('.canteiro-item').forEach(function (it) {
      it.classList.toggle('holofote', !!mid && it.dataset.memberId === String(mid));
    });
    document.body.classList.toggle('holofote-escuro', !!mid);
  }

  function quemEdita(j) {
    if (j.modo === 'celular' && j.eu && j.eu === j.member_id) return 'proprio';
    if (j.modo === 'scrum' && j.pode_scrum) return 'scrum';
    return '';
  }

  function salvarCampo(j, campo, valor, tipoEdicao) {
    var corpo = { data: j.data, tipo: j.tipo, campo: campo, valor: valor };
    if (tipoEdicao === 'scrum') { corpo.member_id = j.member_id; return postar('/api/ata/salvar', corpo); }
    return postar('/api/ata/minha-fala', corpo);
  }

  function textoTemCard(valor, iid) { return new RegExp('#' + iid + '(\\D|$)').test(valor || ''); }

  function montarChips(cont, cards, ta, aoMudar, editavel) {
    cont.innerHTML = '';
    if (!cards || !cards.length) { cont.hidden = true; return; }
    var rot = document.createElement('span');
    rot.className = 'gl-chips-rot';
    rot.textContent = editavel ? 'Cards sugeridos (toque para acrescentar):' : 'Cards sugeridos:';
    cont.appendChild(rot);
    cards.forEach(function (c) {
      if (!editavel) {                       // so leitura: o Scrum pode ler os cards em voz alta
        var s = document.createElement('span');
        s.className = 'gl-chip gl-chip-leitura'; s.textContent = c.citacao;
        cont.appendChild(s);
        return;
      }
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'gl-chip'; b.textContent = c.citacao;
      b.addEventListener('click', function () {
        if (textoTemCard(ta.value, c.iid)) { ta.focus(); return; }
        var sep = ta.value.trim() ? (ta.value.replace(/\s+$/, '') + '\n') : '';
        ta.value = sep + c.citacao;
        ta.dataset.sujo = '1';
        aoMudar();
      });
      cont.appendChild(b);
    });
    cont.hidden = false;
  }

  function carregarCards(j, tipoEdicao) {
    var mid = j.member_id;
    function pintar(res) {
      if (!res || !res.ok || !pop) return;
      campos(j).forEach(function (c) {
        var ta = pop.querySelector('textarea[data-campo="' + c[0] + '"]');
        var cont = pop.querySelector('.hf-chips[data-campo="' + c[0] + '"]');
        if (ta && cont) montarChips(cont, cardsDe(res, c[2]), ta, function () { agendar(j, c[0], ta, tipoEdicao); }, !!tipoEdicao);
      });
    }
    if (cacheCards[mid]) { pintar(cacheCards[mid]); return; }
    fetch('/api/gitlab/cards?member_id=' + encodeURIComponent(mid))
      .then(function (r) { return r.json(); })
      .then(function (res) { cacheCards[mid] = res; pintar(res); })
      .catch(function () {});
  }

  function agendar(j, campo, ta, tipoEdicao) {
    clearTimeout(timers[campo]);
    timers[campo] = setTimeout(function () {
      var v = ta.value;
      salvarCampo(j, campo, v, tipoEdicao).then(function (res) {
        if (res && res.ok && ta.value === v) delete ta.dataset.sujo;
        if (res && res.ok && res.j && res.j.jogo_resposta && window.aplicarJogoNaTela) aplicarJogoNaTela(res.j.jogo_resposta, j.nome);
      }).catch(function () {});
    }, 700);
  }

  function fechar() {
    if (pop) { pop.remove(); pop = null; }
    chave = '';
  }

  function montar(j, tipoEdicao) {
    fechar();
    pop = document.createElement('div');
    pop.className = 'hf-pop';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'Rodada de fala (' + (j.tipo === 'fechamento' ? 'Day Closing' : 'Daily') + '): vez de ' + j.nome);
    var rotulo = tipoEdicao === 'proprio' ? 'Sua vez! Preencha aqui e todos veem o que você escrever.'
      : tipoEdicao === 'scrum' ? 'O Scrum está preenchendo por ' + j.nome + '.'
      : j.nome + ' está preenchendo no celular.';
    var html = '<div class="hf-topo"><div><p class="hf-vez">Vez de</p><h2 class="hf-nome"></h2></div>' +
      '<div class="hf-acoes"><button type="button" class="btn btn-ghost hf-fechar">Fechar</button></div></div>' +
      (j.pode_scrum ? '<div class="hf-alterna" role="group" aria-label="Quem preenche">' +
        '<button type="button" class="chip-modo hf-quem" data-modo="celular"></button>' +
        '<button type="button" class="chip-modo hf-quem" data-modo="scrum">Eu preencho por <span class="hf-quem-nome"></span></button></div>' : '') +
      (j.pode_scrum ? '<div class="hf-status" role="group" aria-label="Situação de ' + j.nome + '">' +
        '<button type="button" class="ata-st st-presente" data-hst="presente">Presente</button>' +
        '<button type="button" class="ata-st st-aviso" data-hst="justificada">Avisou</button>' +
        '<button type="button" class="ata-st st-faltou" data-hst="faltou">Faltou</button></div>' : '') +
      '<p class="hf-modo"></p>';
    campos(j).forEach(function (c) {
      html += '<div class="hf-campo"><label>' + c[1] + (c[0] === 'review' ? ' <small>(não conta semente)</small>' : '') + '</label>' +
        '<textarea rows="2" data-campo="' + c[0] + '"' + (tipoEdicao ? '' : ' readonly') + '></textarea>' +
        '<div class="gl-chips hf-chips" data-campo="' + c[0] + '" hidden></div></div>';
    });
    if (j.pode_scrum) {
      html += '<div class="hf-rodape"><button type="button" class="btn btn-ghost hf-encerrar">Encerrar rodada</button>' +
        '<button type="button" class="btn btn-primary hf-prox">Próxima pessoa</button></div>';
    }
    pop.innerHTML = html;
    pop.querySelector('.hf-nome').textContent = j.nome;
    pop.querySelector('.hf-modo').textContent = rotulo;
    pop.querySelector('.hf-fechar').addEventListener('click', function () { escondido = chave; fechar(); chave = escondido; destacarPlantas(null); });
    pop.querySelectorAll('.hf-quem').forEach(function (b) {
      if (b.dataset.modo === 'celular') b.textContent = j.nome + ' preenche no celular';
      var nome = b.querySelector('.hf-quem-nome'); if (nome) nome.textContent = j.nome;
      b.setAttribute('aria-pressed', b.dataset.modo === j.modo ? 'true' : 'false');
      b.addEventListener('click', function () {
        if (b.dataset.modo === j.modo) return;
        postar('/api/holofote', { member_id: j.member_id, modo: b.dataset.modo, tipo: j.tipo }).then(function () {
          document.dispatchEvent(new CustomEvent('holofote:modo', { detail: { modo: b.dataset.modo } }));
          buscar();
        });
      });
    });
    pop.querySelectorAll('[data-hst]').forEach(function (b) {
      b.setAttribute('aria-pressed', j.status === b.dataset.hst ? 'true' : 'false');
      b.addEventListener('click', function () {
        var novo = b.getAttribute('aria-pressed') === 'true' ? '' : b.dataset.hst;
        // marca na hora (sem esperar o servidor) para o toque ser visivel
        pop.querySelectorAll('[data-hst]').forEach(function (x) { x.setAttribute('aria-pressed', x.dataset.hst === novo ? 'true' : 'false'); });
        postar('/api/ata/salvar', { data: j.data, tipo: j.tipo, campo: 'status', member_id: j.member_id, valor: novo }).then(function (res) {
          if (!res.ok) { if (window.mostrarToast) mostrarToast((res.j && res.j.erro) || 'Não salvou.', 'info'); buscar(); return; }
          if (res.j.jogo_resposta && window.aplicarJogoNaTela) aplicarJogoNaTela(res.j.jogo_resposta, j.nome);
          // quem avisou ou faltou nao vai falar: a rodada (se estiver nesta tela) passa para a proxima pessoa
          if (novo === 'justificada' || novo === 'faltou') setTimeout(function () { document.dispatchEvent(new CustomEvent('holofote:avancar', { detail: { id: j.member_id } })); }, 450);
          else buscar();
        });
      });
    });
    var enc = pop.querySelector('.hf-encerrar');
    if (enc) {
      enc.addEventListener('click', function () {
        var b = document.getElementById('rodada-fim');
        if (b) b.click(); else postar('/api/holofote', { member_id: null }).then(buscar);
      });
    }
    var prox = pop.querySelector('.hf-prox');
    if (prox) {
      prox.addEventListener('click', function () {
        var b = document.getElementById('rodada-prox');
        if (b) b.click(); else postar('/api/holofote', { member_id: null }).then(buscar);
      });
    }
    if (tipoEdicao) {
      pop.querySelectorAll('textarea').forEach(function (ta) {
        ta.addEventListener('input', function () { ta.dataset.sujo = '1'; agendar(j, ta.dataset.campo, ta, tipoEdicao); });
      });
    }
    carregarCards(j, tipoEdicao);          // os cards aparecem para todos; so quem edita pode tocar neles
    document.body.appendChild(pop);
  }

  function aplicar(j) {
    if (!j || !j.ok || !j.member_id) { escondido = null; destacarPlantas(null); fechar(); return; }
    var tipoEdicao = quemEdita(j);
    var nova = [j.member_id, j.tipo, j.modo, tipoEdicao].join('|');
    if (escondido === nova) { destacarPlantas(null); return; }   // fechou o painel: some tambem o escurecido e o destaque (so para quem fechou)
    destacarPlantas(j.member_id);
    if (nova !== chave || !pop) { montar(j, tipoEdicao); chave = nova; }
    // atualiza o texto sem atropelar quem esta digitando
    pop.querySelectorAll('textarea').forEach(function (ta) {
      var novoValor = (j.falas && j.falas[ta.dataset.campo]) || '';
      if (document.activeElement === ta || ta.dataset.sujo) return;
      if (ta.value !== novoValor) ta.value = novoValor;
    });
  }

  function buscar() {
    return fetch('/api/holofote').then(function (r) { return r.json(); }).then(aplicar).catch(function () {});
  }

  document.addEventListener('holofote:refresh', buscar);     // a rodada avisa quando acende outra pessoa
  buscar();
  setInterval(buscar, 3000);
})();
