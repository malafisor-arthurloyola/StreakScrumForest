/* Sons do jardim: efeitos e musica ambiente, todos gerados na hora com Web Audio.
   Nao ha arquivo de audio: nada a baixar, nada de licenca, e o servidor nao gasta nada.
   Tom: caixinha de musica, madeira e agua. Nenhum som de erro ou de perda: Faltou e Avisou
   tem o mesmo toque neutro, e o que da errado fica so no aviso escrito (nunca punir).
   Escolhas lembradas no navegador: efeitos ligados por padrao, musica desligada ate a pessoa ligar.
   Uso: Som.tocar('holofote'), Som.semSom(fn) para atualizacoes que vem de outro aparelho. */
(function () {
  var CHAVE_EF = 'jardim.som.efeitos', CHAVE_MU = 'jardim.som.musica';
  var VOL_EF = 0.55, VOL_MU = 0.16;
  function ler(k, padrao) { try { var v = localStorage.getItem(k); return v === null ? padrao : v === '1'; } catch (e) { return padrao; } }
  function gravar(k, v) { try { localStorage.setItem(k, v ? '1' : '0'); } catch (e) {} }

  var efeitos = ler(CHAVE_EF, true);
  var musica = ler(CHAVE_MU, false);
  var ctx = null, saida = null, busEf = null, busMu = null, eco = null;
  var calado = 0;               // > 0 enquanto aplica algo que veio de outro aparelho

  function hz(midi) { return 440 * Math.pow(2, (midi - 69) / 12); }

  function iniciar() {
    if (ctx) return ctx;
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    saida = ctx.createDynamicsCompressor();
    saida.threshold.value = -14; saida.ratio.value = 4;
    saida.connect(ctx.destination);
    busEf = ctx.createGain(); busEf.gain.value = efeitos ? VOL_EF : 0; busEf.connect(saida);
    busMu = ctx.createGain(); busMu.gain.value = 0; busMu.connect(saida);
    // um eco curto de sala (reverb feito de ruido que se apaga), dividido entre efeitos e musica
    eco = ctx.createConvolver();
    var dur = 1.8, n = Math.floor(ctx.sampleRate * dur), ir = ctx.createBuffer(2, n, ctx.sampleRate);
    for (var c = 0; c < 2; c++) {
      var d = ir.getChannelData(c);
      for (var i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 3);
    }
    eco.buffer = ir;
    var ecoVol = ctx.createGain(); ecoVol.gain.value = 0.32;
    eco.connect(ecoVol); ecoVol.connect(saida);
    return ctx;
  }
  function pronto() {
    if (!iniciar()) return false;
    if (ctx.state === 'suspended') ctx.resume();
    return ctx.state !== 'closed';
  }

  // ---- pecas basicas
  function envelope(g, t, ataque, dur, vol) {
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + ataque);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  }
  function ligar(no, bus, molhado) {
    no.connect(bus);
    if (molhado) { var s = ctx.createGain(); s.gain.value = molhado; no.connect(s); s.connect(eco); }
  }
  // nota de caixinha de musica (kalimba): seno com um brilho agudo que some rapido
  function sino(midi, t, o) {
    o = o || {};
    var bus = o.bus || busEf, vol = o.vol || 0.3, dur = o.dur || 1.2, f = hz(midi);
    var g = ctx.createGain(); envelope(g, t, 0.004, dur, vol);
    var a = ctx.createOscillator(); a.type = 'sine'; a.frequency.value = f; a.connect(g);
    var g2 = ctx.createGain(); envelope(g2, t, 0.002, dur * 0.25, vol * 0.35);
    var b = ctx.createOscillator(); b.type = 'sine'; b.frequency.value = f * 4.2; b.connect(g2); g2.connect(g);
    ligar(g, bus, o.eco === undefined ? 0.5 : o.eco);
    a.start(t); b.start(t); a.stop(t + dur + 0.05); b.stop(t + dur + 0.05);
  }
  // tom simples com deslize de altura (gotas, bichos, cliques)
  function tom(f1, f2, t, dur, o) {
    o = o || {};
    var g = ctx.createGain(); envelope(g, t, o.ataque || 0.003, dur, o.vol || 0.2);
    var a = ctx.createOscillator(); a.type = o.tipo || 'sine';
    a.frequency.setValueAtTime(f1, t);
    a.frequency.exponentialRampToValueAtTime(f2, t + (o.deslize || dur * 0.7));
    a.connect(g); ligar(g, o.bus || busEf, o.eco || 0);
    a.start(t); a.stop(t + dur + 0.05);
  }
  var bufRuido = null;
  function ruido(t, dur, o) {
    o = o || {};
    if (!bufRuido) {
      bufRuido = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
      var d = bufRuido.getChannelData(0);
      for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
    var s = ctx.createBufferSource(); s.buffer = bufRuido; s.loop = true;
    var fl = ctx.createBiquadFilter(); fl.type = o.filtro || 'bandpass'; fl.Q.value = o.q || 1;
    fl.frequency.setValueAtTime(o.f1 || 1000, t);
    if (o.f2) fl.frequency.exponentialRampToValueAtTime(o.f2, t + dur);
    var g = ctx.createGain(); envelope(g, t, o.ataque || 0.005, dur, o.vol || 0.15);
    s.connect(fl); fl.connect(g); ligar(g, o.bus || busEf, o.eco || 0);
    s.start(t, Math.random() * 0.5); s.stop(t + dur + 0.05);
  }
  function arpejo(notas, t, passo, o) {
    notas.forEach(function (m, i) { sino(m, t + i * passo, o); });
  }

  // ---- catalogo de sons, por momento do jogo (notas em MIDI: 72 = do central agudo)
  var SONS = {
    // cliques: um toque de madeira bem curto e baixo
    clique: function (t) { tom(1400, 700, t, 0.045, { vol: 0.12, tipo: 'triangle' }); },
    // rodada de fala: o holofote acende (luz subindo + dois sinos)
    holofote: function (t) {
      ruido(t, 0.45, { f1: 300, f2: 3200, q: 2.5, vol: 0.07, ataque: 0.25, eco: 0.4 });
      sino(79, t + 0.32, { vol: 0.24, dur: 1.6 });
      sino(84, t + 0.32, { vol: 0.2, dur: 1.8 });
    },
    // no celular de quem vai falar: "sua vez", um ding-dong que sobe
    suaVez: function (t) { sino(76, t, { vol: 0.3 }); sino(81, t + 0.16, { vol: 0.3, dur: 1.5 }); },
    // sorteio da ordem: notas rapidas que desaceleram e param num acorde
    sorteio: function (t) {
      fimSorteio = t + 1.3;
      var esc = [72, 74, 76, 79, 81, 84, 86, 88], x = t, p = 0.05;
      for (var i = 0; i < 11; i++) { sino(esc[Math.floor(Math.random() * esc.length)], x, { vol: 0.13, dur: 0.4, eco: 0.2 }); x += p; p *= 1.18; }
      arpejo([72, 76, 79], x + 0.05, 0.02, { vol: 0.2, dur: 1.4 });
    },
    // rodada concluida: arpejo que desce e repousa
    rodadaFim: function (t) { arpejo([84, 79, 76, 72], t, 0.14, { vol: 0.2, dur: 1.6 }); },
    // Presente: a planta e regada (uma gota grande e uma pequena)
    gota: function (t) {
      tom(520, 1500, t, 0.09, { vol: 0.22, eco: 0.3 });
      tom(700, 1900, t + 0.11, 0.07, { vol: 0.12, eco: 0.3 });
    },
    // Avisou, Faltou, desmarcar: o mesmo toque neutro e macio (nada soa como perda)
    neutro: function (t) { sino(67, t, { vol: 0.14, dur: 0.5, eco: 0.2 }); },
    // ganhou sementes
    semente: function (t) { sino(88, t, { vol: 0.12, dur: 0.5, eco: 0.3 }); sino(91, t + 0.07, { vol: 0.1, dur: 0.6, eco: 0.3 }); },
    // planta subiu de estagio
    estagio: function (t) { arpejo([72, 76, 79, 84], t, 0.09, { vol: 0.22 }); ruido(t + 0.35, 0.5, { f1: 6000, filtro: 'highpass', vol: 0.03 }); },
    // floresceu: o mesmo arpejo, mais longo, com um acorde aberto no fim
    floresceu: function (t) {
      arpejo([72, 76, 79, 84, 88, 91], t, 0.08, { vol: 0.2 });
      [60, 67, 76].forEach(function (m) { sino(m, t + 0.5, { vol: 0.12, dur: 2.4 }); });
      ruido(t + 0.5, 0.9, { f1: 7000, filtro: 'highpass', vol: 0.035 });
    },
    // marco de sequencia: um sopro de chama e dois sinos
    chama: function (t) {
      ruido(t, 0.35, { f1: 400, f2: 1800, q: 0.8, vol: 0.08, ataque: 0.12 });
      sino(79, t + 0.2, { vol: 0.2 }); sino(86, t + 0.3, { vol: 0.18, dur: 1.4 });
    },
    // dia cheio: o maior momento, arpejo em duas oitavas sobre um acorde
    diaCheio: function (t) {
      [48, 55, 64].forEach(function (m) { sino(m, t, { vol: 0.12, dur: 3 }); });
      arpejo([72, 76, 79, 84, 88, 91, 96], t + 0.1, 0.07, { vol: 0.18, dur: 1.6 });
      ruido(t + 0.4, 1.2, { f1: 7500, filtro: 'highpass', vol: 0.04 });
    },
    // compra na loja: terra mexida e duas notas de semente
    compra: function (t) {
      ruido(t, 0.12, { f1: 260, filtro: 'lowpass', vol: 0.18 });
      sino(84, t + 0.1, { vol: 0.2 }); sino(91, t + 0.2, { vol: 0.18, dur: 1.2 });
    },
    // equipar ou trocar algo no canteiro
    equipar: function (t) { tom(900, 500, t, 0.05, { vol: 0.12, tipo: 'triangle' }); sino(79, t + 0.06, { vol: 0.15, dur: 0.7 }); },
    // minijogo concluido (fala pronta, fechar o dia, album)
    minijogo: function (t) { arpejo([76, 79, 84], t, 0.1, { vol: 0.22 }); },
    // cuidar da planta: cada gota do regador e cada grao do adubo
    gotinha: function (t) { var f = 900 + Math.random() * 600; tom(f, f * 1.6, t, 0.05, { vol: 0.06 }); },
    carinho: function (t) { sino(91 + Math.floor(Math.random() * 3) * 2, t, { vol: 0.05, dur: 0.4, eco: 0.3 }); },
    grao: function (t) { ruido(t, 0.03, { f1: 2500 + Math.random() * 1500, q: 3, vol: 0.06 }); },
    // bichos do mapa
    coelho: function (t) { tom(260, 620, t, 0.18, { vol: 0.16, deslize: 0.12 }); tom(320, 760, t + 0.2, 0.15, { vol: 0.12 }); },
    esquilo: function (t) { for (var i = 0; i < 3; i++) tom(2200, 3200, t + i * 0.07, 0.05, { vol: 0.07 }); },
    ourico: function (t) { ruido(t, 0.06, { f1: 1600, q: 2, vol: 0.12 }); ruido(t + 0.1, 0.06, { f1: 1800, q: 2, vol: 0.12 }); },
    coracao: function (t) { sino(84, t, { vol: 0.1, dur: 0.6 }); sino(88, t + 0.1, { vol: 0.1, dur: 0.8 }); },
  };

  var ultimo = {}, fimSorteio = 0;
  var INTERVALO_MIN = { gotinha: 0.07, grao: 0.07, carinho: 0.1, clique: 0.04, semente: 0.15 };
  function tocar(nome) {
    if (!efeitos || calado || !SONS[nome]) return;
    if (!pronto()) return;
    var t = ctx.currentTime + 0.01;
    if (ultimo[nome] && t - ultimo[nome] < (INTERVALO_MIN[nome] || 0.12)) return;   // nao empilha o mesmo som
    ultimo[nome] = t;
    if (nome === 'holofote' && fimSorteio > t) t = fimSorteio;     // a luz acende depois do sorteio parar
    try { SONS[nome](t); } catch (e) { if (window.console) console.warn('som ' + nome, e); }
  }
  function semSom(fn) { calado++; try { return fn(); } finally { calado--; } }

  // ---- musica ambiente: um fundo macio (acordes lentos) e notas soltas de caixinha de musica,
  // em escala pentatonica, sem repetir um loop. Para quando a aba fica escondida.
  var ACORDES = [[53, 60, 65, 69], [50, 57, 62, 65], [46, 53, 58, 62], [48, 55, 60, 64]];   // Fa, Re menor, Si bemol, Do
  var PENTA = [65, 67, 69, 72, 74, 77, 79, 81, 84];
  var tocando = false, timerMu = null, proxAcorde = 0, proxNota = 0, idxAcorde = 0, idxNota = 4, fundo = [];
  function acorde(notas, t, dur) {
    notas.forEach(function (m, i) {
      var g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(0.05, t + 2.5);
      g.gain.setValueAtTime(0.05, t + dur - 2.5);
      g.gain.linearRampToValueAtTime(0.0001, t + dur + 1.5);
      var fl = ctx.createBiquadFilter(); fl.type = 'lowpass'; fl.frequency.value = 900;
      var a = ctx.createOscillator(); a.type = 'triangle'; a.frequency.value = hz(m); a.detune.value = i % 2 ? 6 : -6;
      a.connect(fl); fl.connect(g); ligar(g, busMu, 0.4);
      a.start(t); a.stop(t + dur + 1.6);
      fundo.push(a);
    });
  }
  function laco() {
    if (!tocando) return;
    var agora = ctx.currentTime;
    if (proxAcorde < agora + 0.5) {
      proxAcorde = Math.max(proxAcorde, agora + 0.1);
      acorde(ACORDES[idxAcorde % ACORDES.length], proxAcorde, 8);
      idxAcorde++; proxAcorde += 8;
      fundo = fundo.slice(-16);
    }
    while (proxNota < agora + 0.6) {
      proxNota = Math.max(proxNota, agora + 0.1);
      if (Math.random() < 0.7) {
        idxNota = Math.max(0, Math.min(PENTA.length - 1, idxNota + [-2, -1, -1, 1, 1, 2][Math.floor(Math.random() * 6)]));
        sino(PENTA[idxNota], proxNota, { bus: busMu, vol: 0.13 + Math.random() * 0.06, dur: 2.2, eco: 0.7 });
      }
      proxNota += [0.6, 0.9, 1.2, 1.8][Math.floor(Math.random() * 4)];
    }
    timerMu = setTimeout(laco, 250);
  }
  function volMusica(alvo, seg) {
    if (!ctx) return;
    var g = busMu.gain, t = ctx.currentTime;
    g.cancelScheduledValues(t); g.setValueAtTime(g.value, t); g.linearRampToValueAtTime(alvo, t + (seg || 1.5));
  }
  var abafada = false;
  function iniciarMusica() {
    if (tocando || !musica || document.hidden || !pronto()) return;
    if (ctx.state !== 'running') return;       // espera o primeiro toque na pagina
    tocando = true; proxAcorde = 0; proxNota = ctx.currentTime + 1.5;
    volMusica(abafada ? VOL_MU * 0.3 : VOL_MU, 3);
    laco();
  }
  function pararMusica() {
    if (!tocando) return;
    tocando = false; clearTimeout(timerMu);
    volMusica(0, 0.8);
    var t = ctx.currentTime + 0.9;
    fundo.forEach(function (a) { try { a.stop(t); } catch (e) {} });
    fundo = [];
  }
  // durante a rodada de fala a musica fica bem baixinha, para nao competir com quem fala
  function abafar(sim) {
    if (abafada === !!sim) return;
    abafada = !!sim;
    if (tocando) volMusica(abafada ? VOL_MU * 0.3 : VOL_MU, 1.2);
  }

  function setEfeitos(v) {
    efeitos = !!v; gravar(CHAVE_EF, efeitos);
    if (ctx) busEf.gain.setTargetAtTime(efeitos ? VOL_EF : 0, ctx.currentTime, 0.05);
    if (efeitos) tocar('clique');
    pintar();
  }
  function setMusica(v) {
    musica = !!v; gravar(CHAVE_MU, musica);
    if (musica) iniciarMusica(); else pararMusica();
    pintar();
  }

  // ---- botao no topo: abre um painel com os dois interruptores
  var botao = null, painel = null;
  function pintar() {
    if (!botao) return;
    var algum = efeitos || musica;
    botao.classList.toggle('mudo', !algum);
    botao.setAttribute('aria-label', algum ? 'Som ligado. Abrir opções de som' : 'Som desligado. Abrir opções de som');
    painel.querySelectorAll('[data-som]').forEach(function (b) {
      var on = b.dataset.som === 'efeitos' ? efeitos : musica;
      b.setAttribute('aria-checked', on ? 'true' : 'false');
    });
  }
  function montarBotao() {
    var lugar = document.querySelector('.topbar-acoes');
    if (!lugar) return;
    var caixa = document.createElement('div');
    caixa.className = 'som-caixa';
    caixa.innerHTML =
      '<button type="button" class="som-botao" aria-expanded="false" aria-controls="som-painel" data-sem-clique>' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path class="som-alto" d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/>' +
        '<path class="som-ondas" d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>' +
        '<path class="som-x" d="M16 9.5l5 5M21 9.5l-5 5"/></svg>' +
      '</button>' +
      '<div class="som-painel" id="som-painel" hidden>' +
        '<button type="button" role="switch" class="som-chave" data-som="efeitos" data-sem-clique><span>Efeitos sonoros</span><i aria-hidden="true"></i></button>' +
        '<button type="button" role="switch" class="som-chave" data-som="musica" data-sem-clique><span>Música do jardim</span><i aria-hidden="true"></i></button>' +
      '</div>';
    lugar.insertBefore(caixa, lugar.firstChild);
    botao = caixa.querySelector('.som-botao');
    painel = caixa.querySelector('.som-painel');
    function abrir(sim) { painel.hidden = !sim; botao.setAttribute('aria-expanded', sim ? 'true' : 'false'); }
    botao.addEventListener('click', function () { pronto(); abrir(painel.hidden); });
    painel.querySelectorAll('[data-som]').forEach(function (b) {
      b.addEventListener('click', function () {
        pronto();
        if (b.dataset.som === 'efeitos') setEfeitos(!efeitos); else setMusica(!musica);
      });
    });
    document.addEventListener('click', function (e) { if (!caixa.contains(e.target)) abrir(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !painel.hidden) { abrir(false); botao.focus(); } });
    pintar();
  }

  // O navegador so deixa tocar depois de um toque na pagina: o primeiro toque destrava o audio
  // (e comeca a musica, se estiver ligada). Cada toque em botao ou link faz o clique de madeira.
  function destravar() { if (efeitos || musica) { pronto(); iniciarMusica(); } }
  document.addEventListener('pointerdown', destravar, true);
  document.addEventListener('keydown', destravar, true);
  document.addEventListener('click', function (e) {
    var alvo = e.target.closest && e.target.closest('button, a[href], .btn, [role="button"]');
    if (!alvo || alvo.closest('[data-sem-clique], .bicho') || alvo.disabled) return;
    tocar('clique');
  }, true);
  // Bichos do mapa: cada um tem a sua voz, e o coracao que solta tem um plim
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.mapa .bicho');
    if (!b) return;
    ['coelho', 'esquilo', 'ourico'].forEach(function (n) { if (b.classList.contains(n)) tocar(n); });
    setTimeout(function () { tocar('coracao'); }, 380);
  });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) pararMusica(); else iniciarMusica();
  });

  window.Som = { tocar: tocar, semSom: semSom, abafar: abafar, sons: Object.keys(SONS) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', montarBotao); else montarBotao();
  // se o navegador ja permitir (a pessoa acabou de tocar no site em outra pagina), a musica volta sozinha
  if (musica) { pronto(); setTimeout(iniciarMusica, 300); }
})();
