/* Holofote da rodada de fala da Daily.
   Quem conduz (o Scrum) acende a planta de quem esta falando. Em todas as telas abertas:
   - a planta ganha o destaque e o resto da tela escurece um pouco;
   - aparece um painel com os tres campos da daily e os cards sugeridos do GitLab.
   Quem preenche: por padrao a propria pessoa, no celular dela (e todos veem o texto aparecer);
   o Scrum pode assumir e preencher por ela (e ganha o bonus de relator, como na ata). */
(function () {
  var CAMPOS = [
    ['feito', 'O que eu fiz de ontem para hoje', 'fiz'],
    ['planejado', 'O que vou fazer hoje', 'fazer'],
    ['review', 'Cards aguardando revisão', 'revisar'],
  ];
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

  function montarChips(cont, cards, ta, aoMudar) {
    cont.innerHTML = '';
    if (!cards || !cards.length) { cont.hidden = true; return; }
    cards.forEach(function (c) {
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
      CAMPOS.forEach(function (c) {
        var ta = pop.querySelector('textarea[data-campo="' + c[0] + '"]');
        var cont = pop.querySelector('.hf-chips[data-campo="' + c[0] + '"]');
        if (ta && cont) montarChips(cont, res[c[2]] || [], ta, function () { agendar(j, c[0], ta, tipoEdicao); });
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
    pop.setAttribute('aria-label', 'Rodada de fala: vez de ' + j.nome);
    var rotulo = tipoEdicao === 'proprio' ? 'Sua vez! Preencha aqui e todos veem o que você escrever.'
      : tipoEdicao === 'scrum' ? 'O Scrum está preenchendo por ' + j.nome + '.'
      : j.nome + ' está preenchendo no celular.';
    var html = '<div class="hf-topo"><div><p class="hf-vez">Vez de</p><h2 class="hf-nome"></h2></div>' +
      '<div class="hf-acoes"><button type="button" class="btn btn-ghost hf-fechar">Fechar</button></div></div>' +
      '<p class="hf-modo"></p>';
    CAMPOS.forEach(function (c) {
      html += '<div class="hf-campo"><label>' + c[1] + (c[0] === 'review' ? ' <small>(não conta semente)</small>' : '') + '</label>' +
        '<textarea rows="2" data-campo="' + c[0] + '"' + (tipoEdicao ? '' : ' readonly') + '></textarea>' +
        '<div class="gl-chips hf-chips" data-campo="' + c[0] + '" hidden></div></div>';
    });
    if (j.pode_scrum) {
      html += '<div class="hf-rodape"><button type="button" class="btn btn-ghost hf-trocar"></button>' +
        '<button type="button" class="btn btn-primary hf-prox">Próxima pessoa</button></div>';
    }
    pop.innerHTML = html;
    pop.querySelector('.hf-nome').textContent = j.nome;
    pop.querySelector('.hf-modo').textContent = rotulo;
    pop.querySelector('.hf-fechar').addEventListener('click', function () { escondido = chave; fechar(); chave = escondido; });
    var trocar = pop.querySelector('.hf-trocar');
    if (trocar) {
      trocar.textContent = j.modo === 'scrum' ? 'Deixar ' + j.nome + ' preencher no celular' : 'Preencher por ' + j.nome;
      trocar.addEventListener('click', function () {
        postar('/api/holofote', { member_id: j.member_id, modo: j.modo === 'scrum' ? 'celular' : 'scrum' }).then(buscar);
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
      carregarCards(j, tipoEdicao);
    }
    document.body.appendChild(pop);
  }

  function aplicar(j) {
    if (!j || !j.ok || !j.member_id) { escondido = null; destacarPlantas(null); fechar(); return; }
    destacarPlantas(j.member_id);
    var tipoEdicao = quemEdita(j);
    var nova = [j.member_id, j.modo, tipoEdicao].join('|');
    if (escondido === nova) return;            // a pessoa fechou o painel desta vez
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

  buscar();
  setInterval(buscar, 3000);
})();
