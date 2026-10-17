var CORES_CONFETE = ['#c6f24e', '#6db9ff', '#ff9ec4', '#ffd35c', '#4fdb9b', '#ff8d76'];

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
  return n + (n === 1 ? ' dia' : ' dias');
}

function confete(memberId) {
  var item = document.querySelector('.canteiro-item[data-member-id="' + memberId + '"]');
  if (!item) return;
  var caixa = document.createElement('div');
  caixa.className = 'confete';
  caixa.setAttribute('aria-hidden', 'true');
  for (var i = 0; i < 18; i++) {
    var p = document.createElement('i');
    var ang = (Math.PI * 2 * i) / 18 + Math.random() * 0.4;
    var dist = 46 + Math.random() * 54;
    p.style.setProperty('--dx', Math.cos(ang) * dist + 'px');
    p.style.setProperty('--dy', Math.sin(ang) * dist - 30 + 'px');
    p.style.background = CORES_CONFETE[i % CORES_CONFETE.length];
    caixa.appendChild(p);
  }
  item.appendChild(caixa);
  setTimeout(function () { caixa.remove(); }, 1100);
}

function aplicarEstagio(jogo) {
  var anterior = 0;
  document.querySelectorAll('.planta[data-member-id="' + jogo.id + '"]').forEach(function (svg) {
    anterior = parseInt(svg.dataset.stage, 10) || 0;
    svg.dataset.stage = jogo.estagio;
    svg.dataset.vigor = jogo.vigor;
    svg.dataset.frutos = jogo.frutos;
    svg.dataset.floresceu = jogo.floresceu ? 'true' : 'false';
    svg.querySelectorAll('[data-min]').forEach(function (g) {
      var min = parseInt(g.dataset.min, 10);
      var max = g.dataset.max ? parseInt(g.dataset.max, 10) : 99;
      g.classList.toggle('on', jogo.estagio >= min && jogo.estagio <= max);
    });
    svg.querySelectorAll('[data-fruto]').forEach(function (f) {
      f.classList.toggle('on', (jogo.frutos || 0) >= parseInt(f.dataset.fruto, 10));
    });
  });
  return anterior;
}

function atualizarTextos(jogo) {
  document.querySelectorAll('[data-streak-for="' + jogo.id + '"]').forEach(function (el) {
    el.textContent = rotuloDias(jogo.streak);
  });
  document.querySelectorAll('[data-estagio-for="' + jogo.id + '"]').forEach(function (el) {
    el.textContent = jogo.estagio_nome;
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

          if (data.jogo) {
            var j = data.jogo;
            var anterior = aplicarEstagio(j);
            atualizarTextos(j);
            if (j.estagio > anterior) {
              confete(j.id);
              var nome = '';
              var linha = wrapper.closest('[data-member-row]');
              if (linha) {
                var el = linha.querySelector('.linha-nome');
                if (el) nome = el.textContent.trim() + ' chegou ao estágio ';
              }
              mostrarToast((nome || 'Chegou ao estágio ') + j.estagio + ': ' + j.estagio_nome, 'sucesso');
            }
          }
        })
        .catch(function () {
          alert('Não foi possível salvar. Verifique se o servidor ainda está rodando.');
        });
    });
  });
});
