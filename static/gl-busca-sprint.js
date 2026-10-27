/* Busca de cards nos campos "O que fiz" e "Vou revisar" (Waiting review, Review e fechados da
   sprint atual). Funciona na ata, no Meu jardim e na tela de presenca: cada caixa de busca
   (.gl-sprint-busca, com data-para="feito" ou "review") escreve no campo certo da MESMA area
   (linha da ata, bloco do Meu jardim ou formulario da presenca). Tocar num resultado
   ACRESCENTA "#123 titulo" ao campo (nunca sobrescreve, nao duplica) e aciona o auto-salvar
   que cada tela ja tem. Se o GitLab nao sincronizou, simplesmente nao lista nada. */
(function () {
  function temCard(valor, iid) {
    return new RegExp('#' + iid + '(\\D|$)').test(valor || '');
  }
  document.querySelectorAll('.gl-sprint-busca').forEach(function (inp) {
    var para = inp.dataset.para;
    var res = inp.parentElement.querySelector('.gl-sprint-res');
    var escopo = inp.closest('.ata-linha, .eu-fala-bloco, #presenca-form');
    if (!res || !escopo) return;
    var t;
    function buscar() {
      fetch('/api/gitlab/buscar?q=' + encodeURIComponent(inp.value.trim()))
        .then(function (r) { return r.json(); })
        .then(function (j) {
          res.innerHTML = '';
          if (!j || !j.ok || !j.cards.length) { res.hidden = true; return; }
          j.cards.forEach(function (c) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'gl-chip';
            b.textContent = c.citacao;
            b.addEventListener('click', function () {
              var ta = escopo.querySelector('textarea[data-campo="' + para + '"]');
              if (!ta || ta.disabled) return;
              if (!temCard(ta.value, c.iid)) {
                var sep = ta.value.trim() ? (ta.value.replace(/\s+$/, '') + '\n') : '';
                ta.value = sep + c.citacao;
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('blur'));
              }
              ta.focus();
            });
            res.appendChild(b);
          });
          res.hidden = false;
        })
        .catch(function () {});
    }
    inp.addEventListener('input', function () { clearTimeout(t); t = setTimeout(buscar, 300); });
    inp.addEventListener('focus', buscar);
  });
})();
