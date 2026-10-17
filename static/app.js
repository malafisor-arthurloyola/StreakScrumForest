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
  }, 3200);
}

function atualizarPlanta(memberid, jogo) {
  var svg = document.querySelector('.planta-svg[data-member-id="' + memberid + '"]');
  if (!svg) return;
  svg.dataset.stage = jogo.estagio;
  svg.dataset.vigor = jogo.vigor;
  svg.dataset.floresceu = jogo.floresceu ? 'true' : 'false';
}

function atualizarStreak(memberid, streak) {
  var el = document.querySelector('[data-streak-for="' + memberid + '"]');
  if (el) el.textContent = streak + 'd';
}

function atualizarEstagioLabel(memberid, nomeEstagio) {
  var el = document.querySelector('[data-estagio-for="' + memberid + '"]');
  if (el) el.textContent = nomeEstagio;
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
            atualizarPlanta(j.id, j);
            atualizarStreak(j.id, j.streak);
            atualizarEstagioLabel(j.id, j.estagio_nome);

            var estagioAnterior = parseInt(wrapper.closest('tr') &&
              wrapper.closest('tr').querySelector('[data-estagio-for]') &&
              wrapper.closest('tr').querySelector('[data-estagio-for]').dataset.estagioAnterior || '0', 10);

            if (j.estagio > estagioAnterior && novoStatus === 'presente') {
              mostrarToast(
                'Passou ao estagio ' + j.estagio + ': ' + j.estagio_nome + '!',
                'sucesso'
              );
              var el = wrapper.closest('tr').querySelector('[data-estagio-for]');
              if (el) el.dataset.estagioAnterior = j.estagio;
            }
          }
        })
        .catch(function () {
          alert('Nao foi possivel salvar. Verifique se o servidor ainda esta rodando.');
        });
    });
  });
});
