/* Retro da sprint: Defesa do Canteiro (tower defense cooperativo).
   Um aparelho e o TELAO: roda o jogo (este arquivo em modo 'telao') e grava o estado no servidor
   a cada ~1 s, recebendo de volta as acoes das pessoas. Os demais aparelhos (modo 'jogador')
   desenham o mesmo tabuleiro a partir do estado e mandam as acoes de quem esta logado.
   Regras do Jardim: sem ranking, sem sorte, ninguem e punido; problemas sao anonimos. */
(function () {
  'use strict';
  var CFG = window.RETRO || {};
  var cv = document.getElementById('retro-canvas');
  if (!cv) return;
  var g = cv.getContext('2d');
  var W = 1600, H = 900;
  var TELAO = CFG.modo === 'telao';
  var EU = CFG.eu == null ? null : Number(CFG.eu);
  var BASE = CFG.img || '/static/retro/';
  var reduz = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---------------------------------------------------------------- pessoas
  var MEMB = {};
  (CFG.membros || []).forEach(function (m) { MEMB[m.id] = m; });
  function ini(id) { return MEMB[id] ? MEMB[id].ini : '?'; }
  function nome(id) { return MEMB[id] ? MEMB[id].nome : 'Alguém'; }
  function esp(id) { return MEMB[id] ? MEMB[id].especie : 'muda'; }
  function quem(id) { return id === EU ? 'você' : ini(id); }

  // ---------------------------------------------------------------- imagens
  var NOMES_IMG = ['praga-lagarta', 'praga-caracol', 'praga-pulgao', 'praga-rainha', 'polinizador-abelha', 'composteira',
    'muda', 'girassol', 'cacto', 'cogumelo', 'carnivora', 'lavanda', 'cerejeira', 'bambu', 'bonsai', 'jabuticabeira', 'ipe', 'baoba'];
  var im = {};
  NOMES_IMG.forEach(function (n) {
    var i = new Image();
    i.src = BASE + n + (n.indexOf('praga') === 0 || n === 'polinizador-abelha' || n === 'composteira' ? '.svg' : '.png');
    im[n] = i;
  });

  // ---------------------------------------------------------------- tabuleiro
  var COMUM = [[900, 560], [690, 560], [690, 330], [440, 330], [440, 600], [250, 600]];
  var ROTAS = {
    daily: { nome: 'DAILY', cor: '#ffd35c', pts: [[1640, 300], [1260, 300], [1260, 440], [900, 440], [900, 560]] },
    dev: { nome: 'DESENVOLVIMENTO', cor: '#6db9ff', pts: [[1640, 560], [900, 560]] },
    enc: { nome: 'ENCERRAMENTO', cor: '#c4b0ff', pts: [[1640, 810], [1260, 810], [1260, 680], [900, 680], [900, 560]] }
  };
  Object.keys(ROTAS).forEach(function (k) {
    var r = ROTAS[k]; r.pts = r.pts.concat(COMUM.slice(1)); var L = 0; r.seg = [];
    for (var i = 1; i < r.pts.length; i++) { var a = r.pts[i - 1], b = r.pts[i], d = Math.hypot(b[0] - a[0], b[1] - a[1]); r.seg.push({ a: a, b: b, d: d, L: L }); L += d; }
    r.L = L;
  });
  function noCaminho(r, s) {
    for (var i = 0; i < r.seg.length; i++) { var q = r.seg[i]; if (s <= q.L + q.d) { var t = (s - q.L) / q.d; return [q.a[0] + (q.b[0] - q.a[0]) * t, q.a[1] + (q.b[1] - q.a[1]) * t, q.b[0] - q.a[0]]; } }
    var z = r.pts[r.pts.length - 1]; return [z[0], z[1], -1];
  }
  var LOTES = [[1100, 355], [1430, 400], [1000, 230], [1180, 230], [1430, 660], [1100, 760], [1100, 862], [790, 450], [790, 670], [790, 785],
    [560, 450], [560, 565], [800, 300], [300, 330], [320, 480], [560, 690], [320, 720]].map(function (p, i) { return { x: p[0], y: p[1], i: i }; });
  var TIPOS = {
    cacto: { nome: 'Cacto', papel: 'um acordo', curto: 'acordo', efeito: 'segura a praga e espeta', alc: 125, cad: 1.7 },
    lavanda: { nome: 'Lavanda', papel: 'um ritual', curto: 'ritual', efeito: 'empurra a praga de volta', alc: 165, cad: 2.4 },
    cogumelo: { nome: 'Cogumelo', papel: 'pedir ajuda', curto: 'ajuda', efeito: 'esporos de longe', alc: 190, cad: 2.2 },
    bambu: { nome: 'Bambu', papel: 'uma tarefa', curto: 'tarefa', efeito: 'tiro de semente', alc: 240, cad: 1.3 }
  };
  var ZONA = { daily: 'Daily', dev: 'Desenvolvimento', enc: 'Encerramento' };
  var AREAS = [['daily', 'Daily'], ['dev', 'Desenvolvimento'], ['enc', 'Encerramento']];
  var PRAZOS = ['amanhã', 'sexta', 'a próxima daily', 'o fim da sprint'];
  var CLIMAS = [['sol', 'Sol: cheguei bem'], ['nuvem', 'Nuvem: mais ou menos'], ['chuva', 'Chuva: cheguei cansado']];
  var SUG = {
    problema: ['Daily passa dos 15 min', 'Gente chega atrasada', 'Fala sem preparar', 'Card parado e ninguém sabe por quê', 'Merge na última hora', 'Review demora dias', 'Esquecemos o fechamento', 'Quadro desatualizado no fim do dia'],
    bom: ['Rodada com holofote ficou ágil', 'Todo mundo trouxe a fala pronta', 'Pair programming no card difícil', 'Reviews no mesmo dia', 'Fechamento pelo celular funcionou', 'Quadro ficou em dia'],
    porque: ['Ninguém combinou isso antes', 'Cada um entendeu de um jeito', 'Faltou tempo no fim do dia', 'Ninguém se sentiu dono', 'A gente só percebeu tarde', 'Não sabíamos a quem pedir'],
    ideia: ['Quebrar o card em 3', 'Atualizar o quadro às 17h', 'Timer de 1 min por fala', 'Fala pronta até 8h50', 'Combinado: card só fecha com review', 'Pedir ajuda ao monitor'],
    obrigado: ['valeu pela ajuda no card difícil', 'obrigado por segurar o fechamento', 'valeu pela paciência no review', 'obrigado por puxar a daily']
  };
  // ritmo do jogo
  var RODADA = 40, TCONV = 180, MAXR_PADRAO = 7, APO = 2, MAXPQ = 4, SPC = 1, GROW = 2, ESCK = 1, CADK = 0.45, AUTO_TOQUE = 1.2;
  var semente = 7;
  function rnd() { semente = (semente * 16807) % 2147483647; return semente / 2147483647; }

  // ---------------------------------------------------------------- estado (o telao manda; os outros so leem)
  var S = novoEstado();
  var pragas = [], spawns = [], tiros = [], efeitos = [], tIntervalo = 2, snapEm = 0;
  function novoEstado() {
    return {
      v: 1, fase: 'abertura', climas: {}, probs: [], bons: [], euDe: {}, ordem: [], rodadas: 0, maxr: MAXR_PADRAO,
      hist: [], plantas: {}, atual: null, reforco: 0, obrigados: [], roti: {}, ultimaAcao: 0, presentes: [], aviso: ''
    };
  }
  function presente(m) { if (m != null && S.presentes.indexOf(m) < 0) S.presentes.push(m); }
  function nPres() { return Math.max(1, S.presentes.length); }
  function mutirao() { return Math.max(2, Math.ceil(nPres() * 0.6)); }

  // ---------------------------------------------------------------- regras (so o telao roda)
  function probPor(id) { for (var i = 0; i < S.probs.length; i++) if (S.probs[i].id === id) return S.probs[i]; return null; }
  function euCount(pid) { var n = 0; Object.keys(S.euDe).forEach(function (m) { if ((S.euDe[m] || []).indexOf(pid) >= 0) n++; }); return n; }
  function tipoPraga(rota) { return rota === 'daily' ? 'praga-lagarta' : rota === 'dev' ? 'praga-caracol' : 'praga-pulgao'; }
  function participantes(A) {
    var s = {};
    (A.pq || []).forEach(function (x) { s[x.dono] = 1; });
    (A.ideias || []).forEach(function (d) { s[d.dono] = 1; d.apoios.forEach(function (q) { s[q] = 1; }); Object.keys(d.por).forEach(function (k) { s[d.por[k]] = 1; }); });
    return Object.keys(s).map(Number);
  }
  function forca(d) { return 1 + d.apoios.length + (d.quem ? 1 : 0) + (d.prazo ? 1 : 0) + (d.raiz >= 0 ? 1 : 0); }
  function ordenadas(A) { return A.ideias.slice().sort(function (a, b) { return forca(b) - forca(a) || a.id - b.id; }); }

  function aplicar(a) {
    var m = a.m, d = a.d || {}, A = S.atual;
    if (a.id && a.id <= S.ultimaAcao) return;
    if (a.id) S.ultimaAcao = a.id;
    if (!MEMB[m]) return;
    presente(m);
    switch (a.tipo) {
      case 'clima': S.climas[m] = d.v; break;
      case 'problema':
        if (S.fase !== 'problemas' && S.fase !== 'abertura') return;
        S.probs.push({ id: S.probs.length + 1, rota: d.area, txt: d.txt });
        efeitos.push({ k: 'balao', t: 'Problema: ' + d.txt, rota: d.area, vida: 3 });
        break;
      case 'bom':
        if (S.fase !== 'bons' && S.fase !== 'problemas') return;
        S.bons.push({ id: S.bons.length + 1, zona: d.area, txt: d.txt, usada: false });
        efeitos.push({ k: 'balaoBom', t: 'Foi bom: ' + d.txt, zona: d.area, vida: 3 });
        break;
      case 'eu':
        if (S.fase !== 'eu') return;
        S.euDe[m] = d.ids.filter(function (x) { return !!probPor(x); }).slice(0, 3);
        d.ids.forEach(function (x) { if (probPor(x)) efeitos.push({ k: 'pop', pid: x, vida: 0.8 }); });
        break;
      case 'porque':
        if (!A || A.fase !== 'conversa') return;
        if (A.pq.some(function (x) { return x.dono === m; })) return;
        A.pq.push({ dono: m, txt: d.txt });
        if (A.pq.length <= MAXPQ && A.vida > 1) { A.vida--; }
        break;
      case 'ideia':
        if (!A || A.fase !== 'conversa') return;
        if (A.ideias.some(function (x) { return x.dono === m; })) return;
        A.ideias.push({ id: A.ideias.length, dono: m, t: d.t, txt: d.txt, apoios: [], quem: '', prazo: '', por: {}, raiz: d.raiz >= 0 && d.raiz < A.pq.length ? d.raiz : -1 });
        break;
      case 'apoio':
        if (!A || A.fase !== 'conversa') return;
        var ia = A.ideias[d.ideia];
        if (!ia || ia.dono === m || ia.apoios.indexOf(m) >= 0) return;
        if (A.ideias.filter(function (x) { return x.apoios.indexOf(m) >= 0; }).length >= APO) return;
        ia.apoios.push(m);
        break;
      case 'completar':
        if (!A || A.fase !== 'conversa') return;
        var ic = A.ideias[d.ideia];
        if (!ic) return;
        if (d.campo === 'raiz') { if (ic.raiz >= 0 || !(d.valor >= 0 && d.valor < A.pq.length)) return; ic.raiz = d.valor; ic.por.raiz = m; }
        else if (d.campo === 'quem') { if (ic.quem) return; var q = d.valor === 'TIME' ? 'TIME' : Number(d.valor); if (q !== 'TIME' && !MEMB[q]) return; ic.quem = q; ic.por.quem = m; }
        else if (d.campo === 'prazo') { if (ic.prazo || PRAZOS.indexOf(d.valor) < 0) return; ic.prazo = d.valor; ic.por.prazo = m; }
        break;
      case 'topo':
        if (!A || A.fase !== 'topo') return;
        if (A.topos.indexOf(m) < 0) A.topos.push(m);
        break;
      case 'naotopo':
        if (!A || A.fase !== 'topo') return;
        A.fase = 'conversa'; A.topos = []; A.esc = null;
        S.aviso = ini(m) + ' pediu para conversar mais. O plano voltou para o mural.';
        efeitos.push({ k: 'faixa', t: 'Ainda não: de volta à conversa', sub: ini(m) + ' quer conversar mais antes de plantar', vida: 3 });
        break;
      case 'toque':
        var lp = S.plantas[d.lote];
        if (lp && lp.pronta > 0 && lp.mun > 0) lp.clique = true;
        break;
      case 'obrigado':
        if (S.fase !== 'fecho') return;
        if (!MEMB[d.para] || d.para === m) return;
        if (S.obrigados.some(function (o) { return o.de === m && o.para === d.para; })) return;
        S.obrigados.push({ de: m, para: d.para, txt: d.txt || '' });
        polen(m, d.para);
        break;
      case 'roti':
        if (S.fase !== 'fecho') return;
        S.roti[m] = d.v;
        break;
    }
  }

  function irPara(fase) {
    S.fase = fase; S.aviso = '';
    var tit = { problemas: 'Momento 1: o que atrapalhou', bons: 'Momento 2: o que foi bom', eu: 'Momento 3: eu também', euRes: 'O que o time mais sentiu', fecho: 'Encerramento: agradecer e avaliar' }[fase];
    var sub = { problemas: 'cada problema vira uma praga esperando no portão da sua área', bons: 'cada coisa boa vira uma abelha na colmeia da sua área', eu: 'cada pessoa tem 3 toques; cada toque deixa a praga mais forte', euRes: 'a ordem das conversas sai daqui', fecho: 'cada obrigado faz uma planta florescer' }[fase];
    if (tit) efeitos.push({ k: 'faixa', t: tit, sub: sub, vida: 3 });
  }

  function montarFila() {
    var lista = S.probs.map(function (p) { return { id: p.id, eu: euCount(p.id) }; });
    lista.sort(function (a, b) { return b.eu - a.eu || a.id - b.id; });
    S.ordem = lista.map(function (x) { return x.id; });
  }

  function entra() {
    var restantes = S.ordem.filter(function (id) { return !S.hist.some(function (h) { return h.pid === id; }); });
    if (!restantes.length || S.rodadas >= S.maxr) { fimDasRodadas(); return; }
    var p = probPor(restantes[0]);
    S.rodadas++;
    var eu = euCount(p.id);
    var vida = Math.min(14, 3 + 2 * eu) + Math.round(GROW * (S.rodadas - 1)) + S.reforco;
    var ref = S.reforco; S.reforco = 0;
    S.atual = {
      pid: p.id, txt: p.txt, rota: p.rota, eu: eu, vida: vida, max: vida, ref: ref,
      tipo: S.rodadas === 1 ? 'praga-rainha' : tipoPraga(p.rota), fase: 'conversa', tc: 0, pq: [], ideias: [], topos: [], esc: null, raiz: false
    };
    Object.keys(S.plantas).forEach(function (k) { var P = S.plantas[k]; P.mun = P.max; P.flor = 0; });
    pragaDoAtual(110);
    efeitos.push({ k: 'faixa', t: 'Praga ' + S.rodadas + ': ' + p.txt, sub: ZONA[p.rota] + ' · ' + eu + ' pessoa' + (eu === 1 ? '' : 's') + ' sentiram isso · vida ' + vida + ' · ela espera vocês conversarem', vida: 3.2 });
  }
  function pragaDoAtual(s) {
    var A = S.atual;
    var r = ROTAS[A.rota];
    pragas = [{ principal: true, rota: A.rota, s: s, v: r.L / RODADA, hit: 0, lento: 0, id: Math.random(), espera: 0, tipo: A.tipo }];
  }
  function propoeTopo() {
    var A = S.atual; if (!A || A.fase !== 'conversa') return;
    A.fase = 'topo'; A.esc = ordenadas(A).slice(0, 3).map(function (d) { return d.id; }); A.topos = [];
    efeitos.push({ k: 'faixa', t: 'Todo mundo topa?', sub: 'cada pessoa confirma o plano no próprio aparelho', vida: 2.5 });
  }
  function lotePara(rota, s, ad) {
    var fr = noCaminho(ROTAS[rota], Math.min(ROTAS[rota].L, s + ad)); var best = null, bd = 1e9;
    LOTES.forEach(function (l) { if (S.plantas[l.i]) return; var d = Math.hypot(fr[0] - l.x, fr[1] - l.y); if (d < bd) { bd = d; best = l; } });
    return bd < 260 ? best : null;
  }
  function combinar() {
    var A = S.atual; if (!A || (A.fase !== 'conversa' && A.fase !== 'topo')) return;
    var esc = (A.esc || ordenadas(A).slice(0, 3).map(function (d) { return d.id; })).map(function (i) { return A.ideias[i]; }).filter(Boolean);
    var raiz = A.fase === 'topo' && A.topos.length >= nPres();
    var mut = participantes(A).length >= mutirao();
    A.fase = 'defesa'; A.raiz = raiz; A.mut = mut; A.plantadas = [];
    esc.forEach(function (d, k) {
      var ac = d.txt;
      var qtxt = d.quem === 'TIME' ? 'o time todo' : d.quem ? ini(d.quem) : '';
      if (qtxt || d.prazo) ac += ' (' + [qtxt, d.prazo ? 'até ' + d.prazo : ''].filter(Boolean).join(', ') + ')';
      var f = forca(d) + (mut ? 1 : 0) + (raiz ? 1 : 0);
      var ab = null;
      for (var i = 0; i < S.bons.length; i++) if (S.bons[i].zona === A.rota && !S.bons[i].usada) { ab = S.bons[i]; break; }
      if (ab) { ab.usada = true; f += 1; }
      var l = lotePara(A.rota, 110, [260, 520, 780][k]) || lotePara(A.rota, 110, 400);
      if (l) {
        S.plantas[l.i] = { t: d.t, dono: d.dono, max: f, mun: f, acao: ac, raiz: raiz, rod: S.rodadas, abelha: !!ab, pid: A.pid, apoios: d.apoios.slice(), txtPraga: A.txt, ataca: d.raiz >= 0 && A.pq[d.raiz] ? A.pq[d.raiz].txt : '' };
        A.plantadas.push(l.i);
        if (ab) efeitos.push({ k: 'voo', x0: 1280, y0: 300, tx: l.x, ty: l.y - 90, vida: 1.6, t0: 1.6 });
      } else {
        var alvo = null;
        Object.keys(S.plantas).forEach(function (k2) { var P = S.plantas[k2]; if (P.dono === d.dono && !alvo) alvo = k2; });
        if (!alvo) Object.keys(S.plantas).forEach(function (k2) { if (!alvo || S.plantas[k2].max < S.plantas[alvo].max) alvo = k2; });
        if (alvo != null) { var P = S.plantas[alvo]; P.max += f; P.mun += f; P.acao = ac; A.plantadas.push(Number(alvo)); }
      }
    });
    var nEsc = Math.round((S.rodadas - 1) * S.rodadas / 2 * ESCK);
    var vs = 4 + Math.floor(S.rodadas / 3);
    for (var i = 0; i < nEsc; i++) spawns.push({ t: 0.3 + i * SPC, rota: ['daily', 'dev', 'enc'][(i + S.rodadas) % 3], vida: vs });
    if (pragas[0]) pragas[0].espera = Math.min(nEsc * SPC * 0.6, 9);
    A.nEsc = nEsc;
    efeitos.push({ k: 'faixa', t: esc.length ? 'Combinado: ' + esc.map(function (d) { return ini(d.dono); }).join(' + ') + (mut ? ' · mutirão +1' : '') + (raiz ? ' · raiz do time +1' : '') : 'Ninguém propôs nada',
      sub: (nEsc ? 'vêm junto ' + nEsc + ' sintoma' + (nEsc > 1 ? 's' : '') + ' de vida ' + vs : 'a praga vem sozinha') + ' · toquem nas plantas quando o anel piscar', vida: 3 });
  }
  function resolve(ok) {
    var A = S.atual;
    var melhor = null;
    (A.plantadas || []).forEach(function (i) { var P = S.plantas[i]; if (P && (!melhor || P.max > melhor.max)) melhor = P; });
    S.hist.push({ pid: A.pid, txt: A.txt, rota: A.rota, ok: ok, acao: melhor ? melhor.acao : '', dono: melhor ? melhor.dono : null });
    efeitos.push(ok && melhor ? { k: 'faixa', t: 'Compromisso da sprint', sub: melhor.acao + ' · ' + ini(melhor.dono), vida: 2.8 }
      : { k: 'faixa', t: 'Assunto em aberto', sub: 'foi para a composteira e volta na próxima retro', vida: 2.8 });
    S.atual = null; tIntervalo = 3.5;
  }
  function fimDasRodadas() {
    S.ordem.forEach(function (id) {
      if (!S.hist.some(function (h) { return h.pid === id; }) && !(S.atual && S.atual.pid === id)) {
        var p = probPor(id); S.hist.push({ pid: id, txt: p.txt, rota: p.rota, ok: false, acao: '', dono: null, motivo: 'não deu tempo, vai para a composteira' });
      }
    });
    S.atual = null; pragas = []; spawns = [];
    irPara('fecho');
  }
  function polen(de, para) {
    var ks = Object.keys(S.plantas);
    var alvo = ks.filter(function (k) { return S.plantas[k].dono === para && !S.plantas[k].florFinal; })[0] || ks.filter(function (k) { return !S.plantas[k].florFinal; })[0] || ks[0];
    if (alvo != null) { S.plantas[alvo].florFinal = true; var l = LOTES[alvo]; efeitos.push({ k: 'voo', x0: 120, y0: 640, tx: l.x, ty: l.y - 110, vida: 1.4, t0: 1.4 }); }
    efeitos.push({ k: 'txt', x: W / 2 + 260, y: 210 + (S.obrigados.length % 5) * 40, t: ini(de) + ' agradeceu ' + ini(para), vida: 2.2, cor: '#fff3dc' });
  }
  function dano(p, d, x, y) {
    if (p.morta) return; p.vida -= d; p.hit = 0.12;
    if (p.principal && S.atual) S.atual.vida = Math.max(0, p.vida);
    if (p.vida <= 0) { p.vida = 0; p.morta = true; p.mt = 0.6; efeitos.push({ k: 'puff', x: x, y: y - 20, vida: 0.6, t0: 0.6 }); if (p.principal && S.atual) resolve(true); }
  }

  function passo(dt) {
    efeitos.forEach(function (e) { e.vida -= dt; if (e.k === 'onda') e.r += (e.max - e.r) * dt * 5; if (e.k === 'txt') e.y -= 24 * dt; });
    efeitos = efeitos.filter(function (e) { return e.vida > 0; });
    if (S.fase !== 'rodada') return;
    var A = S.atual;
    if (!A) { tIntervalo -= dt; if (tIntervalo <= 0 && !pragas.length && !spawns.length) entra(); }
    if (A && A.fase === 'conversa') A.tc += dt;
    if (A && A.fase === 'topo' && A.topos.length >= nPres()) combinar();
    spawns.forEach(function (sp) {
      sp.t -= dt;
      if (sp.t <= 0) { var r = ROTAS[sp.rota]; pragas.push({ rota: sp.rota, mini: true, vida: sp.vida, max: sp.vida, s: 0, v: r.L / (RODADA * 0.75), hit: 0, lento: 0, id: Math.random(), espera: 0, tipo: tipoPraga(sp.rota) }); }
    });
    spawns = spawns.filter(function (sp) { return sp.t > 0; });
    var emDefesa = A && A.fase === 'defesa';
    pragas.forEach(function (p) {
      if (p.morta) return;
      if (p.principal && !emDefesa) return;
      if (p.espera > 0) { p.espera -= dt; return; }
      var r = ROTAS[p.rota], v = p.v, P0 = noCaminho(r, p.s);
      LOTES.forEach(function (l) { var Pl = S.plantas[l.i]; if (Pl && Pl.t === 'cacto' && Pl.mun > 0 && Math.hypot(P0[0] - l.x, P0[1] - l.y) < TIPOS.cacto.alc) { v *= 0.45; p.lento = 0.25; } });
      p.s += v * dt; p.hit = Math.max(0, p.hit - dt); p.lento = Math.max(0, p.lento - dt);
      if (p.s >= r.L) {
        p.fim = true;
        if (p.mini) { S.reforco = Math.min(3, S.reforco + 1); efeitos.push({ k: 'txt', x: 150, y: 440, t: 'sintoma passou: +1 na próxima praga', vida: 1.8, cor: '#fff3dc' }); }
        else if (S.atual) { efeitos.push({ k: 'txt', x: 130, y: 440, t: '+1 na composteira', vida: 1.6, cor: '#fff3dc' }); resolve(false); }
      }
    });
    LOTES.forEach(function (l) {
      var Pl = S.plantas[l.i]; if (!Pl) return;
      Pl.bob = (Pl.bob || 0) + dt; Pl.mira = Math.max(0, (Pl.mira || 0) - dt); Pl.cd = (Pl.cd == null ? 0.8 : Pl.cd) - dt;
      if (Pl.mun <= 0) { Pl.pronta = 0; return; }
      if (Pl.cd > 0) return;
      var T = TIPOS[Pl.t], p = null, q = null;
      pragas.forEach(function (c) {
        if (c.morta || c.fim || (c.principal && !emDefesa)) return;
        var cq = noCaminho(ROTAS[c.rota], c.s); if (Math.hypot(cq[0] - l.x, cq[1] - l.y) > T.alc) return;
        if (!p || c.s / ROTAS[c.rota].L > p.s / ROTAS[p.rota].L) { p = c; q = cq; }
      });
      if (!p) { Pl.pronta = 0; Pl.clique = false; return; }
      Pl.pronta = (Pl.pronta || 0) + dt;
      if (!Pl.clique && Pl.pronta < AUTO_TOQUE) return;
      if (Pl.clique) efeitos.push({ k: 'txt', x: l.x, y: l.y - 150, t: 'toque!', vida: 0.6, cor: '#ffd35c' });
      Pl.clique = false; Pl.pronta = 0; Pl.cd = T.cad * CADK; Pl.mira = 0.5; Pl.miraId = p.id;
      if (Pl.t === 'bambu') { tiros.push({ x: l.x + 10, y: l.y - 70, alvo: p }); Pl.rec = 0.15; }
      if (Pl.t === 'lavanda') { efeitos.push({ k: 'onda', x: l.x, y: l.y - 30, r: 20, max: T.alc, vida: 0.9 }); p.s = Math.max(0, p.s - 45); dano(p, 1, q[0], q[1]); }
      if (Pl.t === 'cogumelo') { for (var k = 0; k < 18; k++) efeitos.push({ k: 'esporo', x: l.x, y: l.y - 40, tx: q[0] + (Math.random() - 0.5) * 60, ty: q[1] - 30 + (Math.random() - 0.5) * 40, vida: 1.1, t0: 1.1 }); dano(p, 1, q[0], q[1]); }
      if (Pl.t === 'cacto') { dano(p, 1, q[0], q[1]); efeitos.push({ k: 'espinho', x: l.x, y: l.y - 40, tx: q[0], ty: q[1] - 30, vida: 0.35, t0: 0.35 }); }
      Pl.mun--;
    });
    tiros.forEach(function (t) {
      if (t.alvo.morta || t.alvo.fim) { t.fim = true; return; }
      var q = noCaminho(ROTAS[t.alvo.rota], t.alvo.s), tx = q[0], ty = q[1] - 35, dx = tx - t.x, dy = ty - t.y, d = Math.hypot(dx, dy), sp = 560 * dt;
      if (d < sp + 6) { t.fim = true; dano(t.alvo, 1, tx, ty); efeitos.push({ k: 'imp', x: tx, y: ty, vida: 0.3, t0: 0.3 }); }
      else { t.x += dx / d * sp; t.y += dy / d * sp; t.ang = Math.atan2(dy, dx); }
    });
    tiros = tiros.filter(function (t) { return !t.fim; });
    pragas = pragas.filter(function (p) { if (p.morta) p.mt -= dt; return !p.fim && !(p.morta && p.mt < 0); });
  }

  // ---------------------------------------------------------------- desenho
  var fundo = document.createElement('canvas'); fundo.width = W; fundo.height = H;
  function rr(c, x, y, w, h, r) { c.beginPath(); if (c.roundRect) c.roundRect(x, y, w, h, r); else c.rect(x, y, w, h); }
  function pintaFundo() {
    var f = fundo.getContext('2d');
    var ceu = f.createLinearGradient(0, 0, 0, 200); ceu.addColorStop(0, '#4cb4f2'); ceu.addColorStop(1, '#bfe8fb'); f.fillStyle = ceu; f.fillRect(0, 0, W, 200);
    f.fillStyle = '#5cc08a'; f.beginPath(); f.moveTo(0, 190); f.quadraticCurveTo(400, 120, 800, 170); f.quadraticCurveTo(1200, 215, 1600, 150); f.lineTo(1600, H); f.lineTo(0, H); f.fill();
    for (var y = 190; y < H; y += 60) for (var x = 0; x < W; x += 60) { f.fillStyle = ((x / 60 + Math.floor((y - 190) / 60)) % 2) ? '#5ccb6b' : '#52bf62'; f.fillRect(x, y, 60, 60); }
    var s = 7; var r2 = function () { s = (s * 16807) % 2147483647; return s / 2147483647; };
    for (var k = 0; k < 220; k++) { var gx = r2() * W, gy = 200 + r2() * (H - 200); f.strokeStyle = 'rgba(47,154,93,.55)'; f.lineWidth = 2; f.beginPath(); f.moveTo(gx, gy); f.lineTo(gx - 4, gy - 9); f.moveTo(gx, gy); f.lineTo(gx, gy - 11); f.moveTo(gx, gy); f.lineTo(gx + 4, gy - 9); f.stroke(); }
    var tra = function (cor, w) { f.strokeStyle = cor; f.lineWidth = w; f.lineJoin = 'round'; f.lineCap = 'round'; Object.keys(ROTAS).forEach(function (k2) { var p = ROTAS[k2].pts; f.beginPath(); f.moveTo(p[0][0], p[0][1]); p.forEach(function (q) { f.lineTo(q[0], q[1]); }); f.stroke(); }); };
    tra('#a3825a', 84); tra('#d6b385', 70); tra('#e2c49a', 40);
    for (var i = 0; i < 14; i++) { f.fillStyle = i % 2 ? '#267f4b' : '#2f9a5d'; f.beginPath(); f.arc(1590 + (i % 2) * 20, 200 + i * 52, 58, 0, 7); f.fill(); }
    f.fillStyle = '#54402f'; rr(f, 20, 470, 215, 260, 22); f.fill(); f.fillStyle = '#6a523d'; rr(f, 20, 470, 215, 20, 10); f.fill();
  }
  function img(n, cx, base, w, h, flip) {
    var i = im[n]; if (!i || !i.complete || !i.naturalWidth) return 0;
    var ar = i.naturalWidth / i.naturalHeight, ww = w, hh = w / ar; if (h && hh > h) { hh = h; ww = h * ar; }
    g.save(); g.translate(cx, base - hh / 2); if (flip) g.scale(-1, 1); g.drawImage(i, -ww / 2, -hh / 2, ww, hh); g.restore(); return hh;
  }
  function texto(t, x, y, tam, cor, peso, al) { g.font = (peso || 800) + ' ' + tam + 'px "Bricolage Grotesque", system-ui, sans-serif'; g.fillStyle = cor; g.textAlign = al || 'center'; g.textBaseline = 'middle'; g.fillText(t, x, y); }
  function quebra(t, max, tam) {
    g.font = '700 ' + tam + 'px "Bricolage Grotesque", system-ui, sans-serif'; var ws = String(t).split(' '), ls = [], l = '';
    ws.forEach(function (w) { var n = l ? l + ' ' + w : w; if (g.measureText(n).width > max && l) { ls.push(l); l = w; } else l = n; }); ls.push(l); return ls;
  }
  function balao(t, x, y, cor) {
    x = Math.min(Math.max(x, 110), W - 110); var ls = quebra(t, 170, 14); g.font = '700 14px "Bricolage Grotesque", system-ui, sans-serif';
    var w = Math.min(190, Math.max.apply(null, ls.map(function (l) { return g.measureText(l).width; })) + 22), h = ls.length * 18 + 12;
    g.fillStyle = 'rgba(0,0,0,.18)'; rr(g, x - w / 2 + 2, y - h + 3, w, h, 10); g.fill(); g.fillStyle = cor; rr(g, x - w / 2, y - h, w, h, 10); g.fill();
    g.beginPath(); g.moveTo(x - 7, y - 1); g.lineTo(x, y + 8); g.lineTo(x + 7, y - 1); g.fill();
    ls.forEach(function (l, i) { texto(l, x, y - h + 15 + i * 18, 14, '#2a1f16', 700); });
  }
  function folhas(x, y, v, mx) {
    var n = Math.min(16, Math.ceil(mx));
    for (var i = 0; i < n; i++) { var on = i < v - 0.01; g.save(); g.translate(x + (i - (n - 1) / 2) * 15 - 6, y); g.globalAlpha = on ? 1 : 0.3; g.fillStyle = on ? '#2f9a5d' : '#33261c'; g.beginPath(); g.moveTo(0, 8); g.bezierCurveTo(0, 2, 5, -2, 12, -2); g.bezierCurveTo(12, 5, 7, 9, 0, 8); g.fill(); g.restore(); }
  }
  function nuvens() {
    var nu = 0, ch = 0; Object.keys(S.climas).forEach(function (k) { if (S.climas[k] === 'nuvem') nu++; if (S.climas[k] === 'chuva') ch++; });
    var tt = performance.now() / 1000;
    for (var i = 0; i < Math.min(8, nu + ch); i++) {
      var x = 950 + ((i * 97 + tt * 6) % 280), y = 48 + (i % 3) * 30, chu = i >= nu;
      g.fillStyle = chu ? 'rgba(176,190,204,.95)' : 'rgba(255,255,255,.92)';
      [[0, 0, 20], [22, -8, 24], [46, 0, 19]].forEach(function (c) { g.beginPath(); g.arc(x + c[0], y + c[1], c[2], 0, 7); g.fill(); });
      if (chu && !reduz) { g.strokeStyle = 'rgba(90,150,220,.7)'; g.lineWidth = 2; for (var k = 0; k < 5; k++) { var yy = y + 18 + ((tt * 80 + k * 13) % 40); g.beginPath(); g.moveTo(x + 4 + k * 9, yy); g.lineTo(x + 1 + k * 9, yy + 7); g.stroke(); } }
    }
  }
  function canteiro() {
    var ids = (CFG.membros || []).filter(function (m) { return m.equipe; }).slice(0, 8);
    ids.forEach(function (m, i) { var cx = 52 + (i % 4) * 50, by = i < 4 ? 580 : 690; img(m.especie, cx, by, 46, 70); texto(m.ini, cx, by + 16, 13, m.id === EU ? '#ffd35c' : '#fff3dc'); });
    g.fillStyle = '#a86a43'; rr(g, 36, 740, 184, 40, 12); g.fill(); texto('Canteiro do time', 128, 760, 19, '#fff3dc');
    img('composteira', 70, 860, 70); texto('Composteira: ' + S.hist.filter(function (h) { return !h.ok; }).length, 110, 840, 17, '#12200a', 800, 'left');
  }
  function placas() {
    Object.keys(ROTAS).forEach(function (k) {
      var r = ROTAS[k], y = r.pts[0][1] - 62, w = k === 'dev' ? 262 : k === 'daily' ? 150 : 228, x = 1590 - w;
      g.fillStyle = '#7a4a2c'; g.fillRect(x + 18, y - 8, 9, 30); g.fillRect(x + w - 27, y - 8, 9, 30);
      g.fillStyle = 'rgba(0,0,0,.22)'; rr(g, x + 3, y - 56, w, 50, 12); g.fill(); g.fillStyle = '#a86a43'; rr(g, x, y - 60, w, 50, 12); g.fill(); g.fillStyle = '#f1e2c4'; rr(g, x + 5, y - 55, w - 10, 40, 9); g.fill();
      g.fillStyle = r.cor; g.beginPath(); g.arc(x + 30, y - 35, 12, 0, 7); g.fill(); g.strokeStyle = '#2a1f16'; g.lineWidth = 2; g.stroke(); texto(r.nome, x + 50, y - 34, 20, '#2a1f16', 800, 'left');
    });
  }
  function colmeias(t) {
    var pos = { daily: [1290, 150], dev: [1265, 410], enc: [1300, 650] };
    Object.keys(pos).forEach(function (z) {
      var x = pos[z][0], y = pos[z][1];
      S.bons.filter(function (b) { return b.zona === z; }).slice(0, 6).forEach(function (b, i) {
        if (b.usada) return;
        img('polinizador-abelha', x - i * 44 + (reduz ? 0 : Math.sin(t / 500 + i) * 6), y + (reduz ? 0 : Math.cos(t / 450 + i) * 5), 40);
      });
    });
  }
  function filaPortao() {
    if (S.fase === 'rodada' || S.fase === 'fecho' || S.fase === 'fim') {
      if (S.fase !== 'rodada') return;
    }
    var base = { daily: [1500, 300], dev: [1500, 560], enc: [1500, 810] }, n = { daily: 0, dev: 0, enc: 0 };
    var feitos = {}; S.hist.forEach(function (h) { feitos[h.pid] = 1; }); if (S.atual) feitos[S.atual.pid] = 1;
    S.probs.forEach(function (p) {
      if (feitos[p.id] || n[p.rota] > 6) return;
      var b = base[p.rota], k = n[p.rota]++, eu = euCount(p.id), w = 30 + Math.min(14, 3 + 2 * eu) * 3;
      img(tipoPraga(p.rota), b[0] - k * 46, b[1] + 18, w, null, true);
      var pop = efeitos.filter(function (e) { return e.k === 'pop' && e.pid === p.id; })[0];
      if (pop) texto('+2', b[0] - k * 46, b[1] - 30 - (1 - pop.vida) * 20, 16, '#c6f24e');
    });
  }
  function desenhaPlanta(l, P, t) {
    var T = TIPOS[P.t];
    if (P.mira > 0) { var alvo = pragas.filter(function (p) { return p.id === P.miraId; })[0]; if (alvo) { var q = noCaminho(ROTAS[alvo.rota], alvo.s); g.strokeStyle = 'rgba(255,211,92,.55)'; g.lineWidth = 2; g.setLineDash([5, 7]); g.beginPath(); g.moveTo(l.x, l.y - 40); g.lineTo(q[0], q[1] - 30); g.stroke(); g.setLineDash([]); } }
    if (P.pronta > 0 && P.mun > 0) {
      var pu = reduz ? 0.5 : (Math.sin(performance.now() / 160) + 1) / 2;
      g.strokeStyle = 'rgba(255,211,92,' + (0.5 + pu * 0.5) + ')'; g.lineWidth = 4 + pu * 3; g.beginPath(); g.ellipse(l.x, l.y - 4, 56 + pu * 6, 24 + pu * 3, 0, 0, 7); g.stroke();
      if (P.dono === EU || TELAO) { g.fillStyle = '#ffd35c'; rr(g, l.x - 38, l.y - 176, 76, 26, 9); g.fill(); texto('toque!', l.x, l.y - 163, 15, '#2a1f16'); }
    }
    var sw = reduz ? 0 : Math.sin((P.bob || t / 1000) * 2) * 0.03;
    g.save(); g.translate(l.x, l.y); g.rotate(sw); img(esp(P.dono), 0, 0, esp(P.dono) === 'muda' ? 80 : 100, 118); g.restore();
    var rot = ini(P.dono) + ' · ' + T.curto; g.font = '800 14px "Bricolage Grotesque", system-ui'; var tw = g.measureText(rot).width, nb = Math.min(P.max, 12), w = tw + 22 + nb * 11, x0 = l.x - w / 2;
    g.fillStyle = P.mun > 0 ? '#ffd35c' : '#c6f24e'; rr(g, x0, l.y + 10, w, 22, 7); g.fill(); g.strokeStyle = P.dono === EU ? '#fff' : '#2a1f16'; g.lineWidth = 2; g.stroke();
    texto(rot, x0 + 8 + tw / 2, l.y + 21.5, 14, '#2a1f16');
    for (var i = 0; i < nb; i++) { g.fillStyle = i < P.mun ? '#7a4a2c' : 'rgba(122,74,44,.25)'; g.beginPath(); g.ellipse(x0 + tw + 18 + i * 11, l.y + 21.5, 4, 3, 0, 0, 7); g.fill(); }
    if (P.mun <= 0 || P.florFinal) { for (var f = 0; f < 5; f++) { g.fillStyle = '#ff9ec4'; g.beginPath(); g.arc(l.x + Math.cos(f * 1.26) * 9, l.y - 120 + Math.sin(f * 1.26) * 9, 6, 0, 7); g.fill(); } g.fillStyle = '#ffd35c'; g.beginPath(); g.arc(l.x, l.y - 120, 6, 0, 7); g.fill(); }
  }
  function desenhaPraga(p, q, t) {
    var big = p.tipo === 'praga-rainha', w = (big ? 150 : p.tipo === 'praga-caracol' ? 96 : 90) * (p.mini ? 0.58 : 1);
    var bob = reduz ? 0 : Math.abs(Math.sin(t / 1000 * 6 + p.id * 9)) * (big ? 3 : 4);
    g.save(); if (p.morta) g.globalAlpha = Math.max(0, p.mt * 2); if (p.hit > 0) g.filter = 'brightness(1.8)';
    img(p.tipo, q[0], q[1] + 18 - bob, w, null, q[2] < 0); g.filter = 'none'; g.restore();
    if (p.lento > 0) texto('devagar', q[0], q[1] + 34, 13, '#3a0f06');
    if (!p.morta) { folhas(q[0], q[1] - w * 0.62 + 4, p.vida, p.max); if (!p.mini && S.atual) balao(S.atual.txt, q[0], q[1] - w * 0.62 - 8, big ? '#ffd35c' : '#ffffff'); }
  }
  function desenhaEfeitos() {
    efeitos.forEach(function (e) {
      var a = e.t0 ? e.vida / e.t0 : 1, k;
      if (e.k === 'onda') { g.strokeStyle = 'rgba(169,140,255,' + e.vida + ')'; g.lineWidth = 6; g.beginPath(); g.ellipse(e.x, e.y, e.r, e.r * 0.6, 0, 0, 7); g.stroke(); }
      if (e.k === 'esporo') { k = 1 - a; g.fillStyle = 'rgba(255,208,224,' + a + ')'; g.beginPath(); g.arc(e.x + (e.tx - e.x) * k, e.y + (e.ty - e.y) * k, 5 + 3 * k, 0, 7); g.fill(); }
      if (e.k === 'espinho') { k = 1 - a; g.strokeStyle = '#fff4c9'; g.lineWidth = 3; var x = e.x + (e.tx - e.x) * k, y = e.y + (e.ty - e.y) * k; g.beginPath(); g.moveTo(x, y); g.lineTo(x - (e.tx - e.x) * 0.08, y - (e.ty - e.y) * 0.08); g.stroke(); }
      if (e.k === 'imp') { g.strokeStyle = 'rgba(255,211,92,' + a + ')'; g.lineWidth = 4; for (var i = 0; i < 8; i++) { var an = i * Math.PI / 4, r1 = 8 + (1 - a) * 14; g.beginPath(); g.moveTo(e.x + Math.cos(an) * r1, e.y + Math.sin(an) * r1); g.lineTo(e.x + Math.cos(an) * (r1 + 9), e.y + Math.sin(an) * (r1 + 9)); g.stroke(); } }
      if (e.k === 'puff') { for (var j = 0; j < 7; j++) { var an2 = j * 0.9, r2 = (1 - a) * 40; g.fillStyle = 'rgba(122,74,44,' + a + ')'; g.beginPath(); g.arc(e.x + Math.cos(an2) * r2, e.y + Math.sin(an2) * r2 * 0.6, 7 * a + 3, 0, 7); g.fill(); } }
      if (e.k === 'voo') { k = 1 - e.vida / e.t0; img('polinizador-abelha', e.x0 + (e.tx - e.x0) * k, e.y0 + (e.ty - e.y0) * k - Math.sin(k * 3.14) * 60, 46); }
      if (e.k === 'txt') { g.globalAlpha = Math.min(1, e.vida); g.fillStyle = 'rgba(0,0,0,.55)'; g.font = '800 18px "Bricolage Grotesque", system-ui'; var w = g.measureText(e.t).width + 20; rr(g, e.x - w / 2, e.y - 15, w, 30, 10); g.fill(); texto(e.t, e.x, e.y, 18, e.cor); g.globalAlpha = 1; }
      if (e.k === 'balao' && ROTAS[e.rota]) { balao(e.t, 1400, ROTAS[e.rota].pts[0][1] - 30, '#ffffff'); }
      if (e.k === 'balaoBom') { var pz = { daily: [1250, 130], dev: [1225, 390], enc: [1260, 630] }[e.zona]; if (pz) balao(e.t, pz[0], pz[1], '#fff3dc'); }
    });
    efeitos.forEach(function (e) {
      if (e.k !== 'faixa') return;
      var lado = TELAO && painelAberto(), cx = lado ? W / 2 + 250 : W / 2, fw = lado ? 640 : 780;
      g.globalAlpha = Math.min(1, e.vida); g.fillStyle = 'rgba(11,21,17,.86)'; rr(g, cx - fw / 2, 360, fw, 110, 20); g.fill();
      var lt = quebra(e.t, fw - 40, 30); texto(lt.length > 1 ? e.t.slice(0, 60) : e.t, cx, 400, lt.length > 1 ? 22 : 30, '#c6f24e'); if (e.sub) texto(e.sub.slice(0, 90), cx, 440, lado ? 15 : 18, '#fff3dc', 700); g.globalAlpha = 1;
    });
  }
  function hud() {
    g.fillStyle = 'rgba(11,21,17,.9)'; rr(g, 16, 16, 560, 96, 18); g.fill();
    var A = S.atual, tit = '', sub = '';
    var NOME_FASE = { abertura: 'Abertura', problemas: 'Momento 1 · problemas', bons: 'Momento 2 · o que foi bom', eu: 'Momento 3 · eu também', euRes: 'O que o time mais sentiu', fecho: 'Encerramento', fim: 'Retro encerrada' };
    if (S.fase === 'rodada') {
      tit = A ? 'Rodada ' + S.rodadas + ' · ' + (A.fase === 'conversa' ? 'conversa' : A.fase === 'topo' ? 'todo mundo topa?' : 'defesa') : 'Rodada ' + S.rodadas + ' · próxima praga chegando';
      sub = A && A.fase === 'conversa' ? A.pq.length + ' porquês · ' + A.ideias.length + ' ideias no mural' : A && A.fase === 'topo' ? A.topos.length + ' de ' + nPres() + ' toparam' : '';
    } else {
      tit = NOME_FASE[S.fase] || '';
      if (S.fase === 'abertura') sub = Object.keys(S.climas).length + ' marcaram como chegam';
      if (S.fase === 'problemas') sub = S.probs.length + ' problemas no portão';
      if (S.fase === 'bons') sub = S.bons.length + ' coisas boas na colmeia';
      if (S.fase === 'eu') sub = Object.keys(S.euDe).length + ' pessoas já marcaram';
      if (S.fase === 'fecho') sub = S.obrigados.length + ' agradecimentos';
    }
    texto(tit, 36, 48, 22, '#c6f24e', 800, 'left'); if (sub) texto(sub, 36, 84, 16, '#cfe0d4', 700, 'left');
    g.fillStyle = 'rgba(11,21,17,.9)'; rr(g, 1240, 16, 344, 96, 18); g.fill();
    var res = S.hist.filter(function (h) { return h.ok; }).length;
    texto(res + ' resolvidas · ' + (S.hist.length - res) + ' em aberto', 1262, 46, 21, '#c6f24e', 800, 'left');
    texto(S.fase === 'rodada' ? 'Rodada ' + S.rodadas + ' de ' + Math.min(S.maxr, S.ordem.length) : S.probs.length + ' problemas · ' + S.bons.length + ' coisas boas', 1262, 82, 16, '#cfe0d4', 700, 'left');
    if (S.fase === 'fim') {
      g.fillStyle = 'rgba(11,21,17,.9)'; rr(g, W / 2 - 420, 150, 840, 170 + S.hist.length * 34, 24); g.fill(); texto('Compromissos da sprint', W / 2, 195, 30, '#c6f24e');
      S.hist.forEach(function (h, k) {
        var y = 242 + k * 34;
        texto((h.ok ? 'Resolvida: ' : 'Em aberto: ') + h.txt.slice(0, 40), W / 2 - 400, y, 17, h.ok ? '#fff3dc' : '#a9bfb0', 700, 'left');
        texto(h.ok && h.acao ? (h.acao.slice(0, 44) + ' · ' + ini(h.dono)) : (h.motivo || 'composteira'), W / 2 + 400, y, 15, h.ok ? '#ffd35c' : '#a9bfb0', 700, 'right');
      });
      var rv = Object.keys(S.roti).map(function (k) { return S.roti[k]; });
      texto(S.obrigados.length + ' agradecimentos' + (rv.length ? ' · a retro valeu ' + (rv.reduce(function (a, b) { return a + b; }, 0) / rv.length).toFixed(1) + ' de 4' : ''), W / 2, 242 + S.hist.length * 34 + 24, 18, '#c6f24e', 700);
    }
  }
  function desenha(t) {
    g.drawImage(fundo, 0, 0); nuvens(); canteiro();
    LOTES.forEach(function (l) {
      var P = S.plantas[l.i];
      g.fillStyle = 'rgba(0,0,0,.18)'; g.beginPath(); g.ellipse(l.x, l.y + 4, 50, 20, 0, 0, 7); g.fill();
      g.fillStyle = P ? '#5c3a22' : '#7a4a2c'; g.beginPath(); g.ellipse(l.x, l.y, 48, 19, 0, 0, 7); g.fill();
      if (!P) { g.strokeStyle = 'rgba(255,243,220,.6)'; g.lineWidth = 3; g.setLineDash([7, 6]); g.beginPath(); g.ellipse(l.x, l.y, 52, 22, 0, 0, 7); g.stroke(); g.setLineDash([]); }
    });
    var ents = [];
    LOTES.forEach(function (l) { var P = S.plantas[l.i]; if (P) ents.push({ y: l.y, f: function () { desenhaPlanta(l, P, t); } }); });
    pragas.forEach(function (p) { var q = noCaminho(ROTAS[p.rota], p.sDraw == null ? p.s : p.sDraw); ents.push({ y: q[1], f: function () { desenhaPraga(p, q, t); } }); });
    ents.sort(function (a, b) { return a.y - b.y; }).forEach(function (e) { e.f(); });
    tiros.forEach(function (tr) { g.save(); g.translate(tr.x, tr.y); g.rotate(tr.ang || Math.PI); g.fillStyle = '#a86a43'; g.beginPath(); g.ellipse(0, 0, 11, 7, 0, 0, 7); g.fill(); g.restore(); });
    placas(); colmeias(t); filaPortao(); desenhaEfeitos(); hud(); dica();
  }

  // ---------------------------------------------------------------- dica ao passar o mouse e toques
  var mouse = null;
  function pos(ev) { var r = cv.getBoundingClientRect(); return [(ev.clientX - r.left) * W / r.width, (ev.clientY - r.top) * H / r.height]; }
  function alvoEm(x, y) {
    for (var i = pragas.length - 1; i >= 0; i--) { var p = pragas[i]; if (p.morta) continue; var q = noCaminho(ROTAS[p.rota], p.sDraw == null ? p.s : p.sDraw); if (Math.hypot(q[0] - x, q[1] - 20 - y) < (p.mini ? 34 : 58)) return { k: 'praga', p: p }; }
    for (var j = 0; j < LOTES.length; j++) { var l = LOTES[j]; if (S.plantas[l.i] && Math.hypot(l.x - x, l.y - 55 - y) < 62) return { k: 'planta', l: l, P: S.plantas[l.i] }; }
    return null;
  }
  function dica() {
    if (!mouse || S.fase === 'fim') return; var a = alvoEm(mouse[0], mouse[1]); cv.style.cursor = a ? 'pointer' : 'default'; if (!a) return;
    var tit, ls = [];
    if (a.k === 'praga') {
      var p = a.p;
      if (p.mini) { tit = 'Sintoma'; ls = ['Da ' + ZONA[p.rota] + '. Chega antes da causa.', 'Vida ' + p.vida + ' de ' + p.max + '.', 'Se passar, a próxima praga vem +1 mais forte.']; }
      else if (S.atual) { var A = S.atual; tit = A.txt; ls = [ZONA[A.rota] + ' · ' + A.eu + ' pessoa' + (A.eu === 1 ? '' : 's') + ' sentiram isso', 'Vida ' + p.vida + ' de ' + p.max]; A.pq.slice(0, 3).forEach(function (x) { ls.push('Por quê: ' + x.txt); }); }
      else return;
    } else {
      var P = a.P, T = TIPOS[P.t]; tit = P.acao;
      ls = [(P.dono === EU ? 'Sua ideia' : 'Ideia de ' + nome(P.dono)) + ' · ' + T.papel + ' (' + T.efeito + ')', 'Força ' + P.mun + ' de ' + P.max + (P.abelha ? ' · tem abelha' : '') + (P.raiz ? ' · raiz do time' : '') + ' · recarrega toda rodada'];
      if (P.apoios && P.apoios.length) ls.push('Apoiada por ' + P.apoios.map(quem).join(', '));
      if (P.ataca) ls.push('Ataca: ' + P.ataca);
      if (P.txtPraga) ls.push('Nasceu na conversa sobre: ' + P.txtPraga);
      if (P.pronta > 0 && P.mun > 0) ls.push('Toque agora para atacar.');
    }
    var tl = quebra(tit, 330, 17), lls = []; ls.forEach(function (l) { lls = lls.concat(quebra(l, 352, 14)); });
    var w = 0; g.font = '600 14px "Bricolage Grotesque", system-ui'; lls.forEach(function (l) { w = Math.max(w, g.measureText(l).width); }); g.font = '800 17px "Bricolage Grotesque", system-ui'; tl.forEach(function (l) { w = Math.max(w, g.measureText(l).width); }); w = Math.min(380, w) + 28;
    var h = 16 + tl.length * 22 + lls.length * 19 + 10, x = mouse[0] + 18, y = mouse[1] + 18; if (x + w > W - 8) x = mouse[0] - w - 18; if (y + h > H - 8) y = mouse[1] - h - 12;
    g.fillStyle = '#fff3dc'; rr(g, x, y, w, h, 14); g.fill(); g.strokeStyle = '#a86a43'; g.lineWidth = 3; g.stroke();
    tl.forEach(function (l, i) { texto(l, x + 14, y + 20 + i * 22, 17, '#2a1f16', 800, 'left'); });
    lls.forEach(function (l, i) { texto(l, x + 14, y + 16 + tl.length * 22 + 8 + i * 19, 14, '#5b4a3a', 600, 'left'); });
  }
  cv.addEventListener('mousemove', function (ev) { mouse = pos(ev); });
  cv.addEventListener('mouseleave', function () { mouse = null; });
  cv.addEventListener('click', function (ev) {
    var p = pos(ev), a = alvoEm(p[0], p[1]);
    mouse = p;
    if (!a || a.k !== 'planta') return;
    if (!(a.P.pronta > 0 && a.P.mun > 0)) { aviso(a.P.mun <= 0 ? 'Esta planta gastou a força nesta rodada. Recarrega na próxima.' : 'Nenhuma praga no alcance desta planta agora. Quando o anel amarelo piscar, toque.'); return; }
    if (TELAO) { a.P.clique = true; return; }
    acao('toque', { lote: a.l.i });
    efeitos.push({ k: 'txt', x: a.l.x, y: a.l.y - 150, t: 'toque enviado', vida: 0.8, cor: '#ffd35c' });
  });

  // ---------------------------------------------------------------- rede
  function postar(url, corpo) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' }, body: JSON.stringify(corpo || {}) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, j: j }; }); });
  }
  function aviso(msg, tipo) { if (window.mostrarToast) mostrarToast(msg, tipo || 'info'); }
  var pendentes = [];
  function acao(tipo, dados) {
    if (EU == null) { aviso('Entre no Meu jardim para jogar.', 'erro'); return Promise.resolve(false); }
    return postar('/api/retro/acao', { tipo: tipo, dados: dados }).then(function (r) {
      if (!r.ok) { aviso((r.j && r.j.erro) || 'Não deu para enviar.', 'erro'); return false; }
      return true;
    }).catch(function () { aviso('Sem conexão. Tente de novo.', 'erro'); return false; });
  }

  function snapshot() {
    var copia = JSON.parse(JSON.stringify(S));
    Object.keys(copia.plantas).forEach(function (k) { var P = copia.plantas[k]; P.pronta = P.pronta > 0 ? 1 : 0; delete P.clique; delete P.bob; delete P.cd; delete P.mira; delete P.miraId; });
    copia.pragas = pragas.map(function (p) { return { rota: p.rota, s: Math.round(p.s), v: p.v, vida: p.vida, max: p.max || (S.atual ? S.atual.max : p.vida), tipo: p.tipo, mini: !!p.mini, principal: !!p.principal, espera: p.espera > 0 ? +p.espera.toFixed(1) : 0, morta: !!p.morta, lento: p.lento > 0 ? 1 : 0, id: p.id }; });
    copia.t = Date.now();
    return copia;
  }
  var hostEnviando = false, hostParado = false;
  function cicloHost() {
    if (hostEnviando || hostParado) return;
    hostEnviando = true;
    postar('/api/retro/host', { estado: snapshot(), desde: S.ultimaAcao }).then(function (r) {
      hostEnviando = false;
      if (r.status === 409) { hostParado = true; aviso('Outro aparelho assumiu o telão. Esta tela agora só mostra.', 'erro'); setTimeout(function () { location.href = '/retro'; }, 1500); return; }
      if (r.ok && r.j.acoes) { r.j.acoes.forEach(aplicar); if (r.j.acoes.length) renderPainel(); }
    }).catch(function () { hostEnviando = false; });
  }

  // jogador: aplica o estado que chega
  var rev = null;
  function aplicarSnapshot(e) {
    var antigas = {}; pragas.forEach(function (p) { antigas[p.id] = p; });
    var plAnt = S.plantas || {};
    S = e;
    pragas = (e.pragas || []).map(function (p) { var o = antigas[p.id]; if (o && p.vida < o.vida) p.hit = 0.15; p.base = p.s; p.sDraw = o && o.sDraw != null ? o.sDraw : p.s; return p; });
    Object.keys(S.plantas).forEach(function (k) { var P = S.plantas[k], o = plAnt[k]; if (o && P.mun < o.mun) P.mira = 0.4; });
    snapEm = performance.now();
    if (S.fase === 'rodada' && S.atual) { var pr = pragas.filter(function (p) { return p.principal; })[0]; if (pr) S.atual.vida = pr.vida; }
  }
  function interpolar(dt) {
    var el = (performance.now() - snapEm) / 1000;
    pragas.forEach(function (p) {
      p.hit = Math.max(0, (p.hit || 0) - dt);
      if (p.morta) { p.mt = (p.mt == null ? 0.6 : p.mt) - dt; return; }
      var andando = S.fase === 'rodada' && S.atual && (S.atual.fase === 'defesa' || p.mini) && !(p.principal && S.atual.fase !== 'defesa');
      var alvoS = andando ? Math.min(ROTAS[p.rota].L, p.base + Math.max(0, el - (p.espera || 0)) * p.v * (p.lento ? 0.45 : 1)) : p.base;
      if (el > 3) alvoS = p.base;
      p.sDraw = p.sDraw + (alvoS - p.sDraw) * Math.min(1, dt * 8);
    });
    efeitos.forEach(function (e) { e.vida -= dt; if (e.k === 'txt') e.y -= 24 * dt; });
    efeitos = efeitos.filter(function (e) { return e.vida > 0; });
  }
  var ultimaFaseVista = '';
  function cicloJogador() {
    if (document.hidden) return;
    fetch('/api/retro/estado' + (rev != null ? '?rev=' + rev : '')).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.ativa) return;
      if (j.estado) {
        var faseAntes = ultimaFaseVista;
        aplicarSnapshot(j.estado); rev = j.rev;
        var chaveFase = S.fase + ':' + (S.atual ? S.atual.pid + ':' + S.atual.fase : '');
        if (chaveFase !== faseAntes) { ultimaFaseVista = chaveFase; anunciar(); }
        renderPainel();
      }
      var bA = document.getElementById('retro-assumir'); if (bA) bA.hidden = !j.host_parado;
    }).catch(function () {});
  }
  function anunciar() {
    var A = S.atual;
    var t = { problemas: 'Momento 1: o que atrapalhou', bons: 'Momento 2: o que foi bom', eu: 'Momento 3: eu também', euRes: 'O que o time mais sentiu', fecho: 'Encerramento' }[S.fase];
    if (S.fase === 'rodada' && A) t = A.fase === 'conversa' ? 'Praga ' + S.rodadas + ': ' + A.txt : A.fase === 'topo' ? 'Todo mundo topa?' : 'Defesa: toquem nas plantas';
    if (t) efeitos.push({ k: 'faixa', t: t, sub: '', vida: 2.4 });
    if (window.Som && Som.tocar) { try { Som.tocar('rodadaFim'); } catch (e) {} }
  }

  // ---------------------------------------------------------------- painel (fichas)
  var painel = document.getElementById('retro-ficha');
  var meu = { probs: 0, bons: 0, eu: null, pq: {}, ideia: {} };
  function esc(t) { return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function chips(nomeG, ops, sel) { return '<div class="chips" role="radiogroup">' + ops.map(function (o) { return '<label><input type="radio" name="' + nomeG + '" value="' + esc(o[0]) + '"' + (String(o[0]) === String(sel) ? ' checked' : '') + '><span>' + esc(o[1]) + '</span></label>'; }).join('') + '</div>'; }
  function sug(alvo, lista) { return '<div class="sug"><button type="button" class="lnk" data-sg="' + alvo + '">Ver sugestões</button><div class="sgl" hidden>' + lista.map(function (t) { return '<button type="button" class="sgc" data-al="' + alvo + '">' + esc(t) + '</button>'; }).join('') + '</div></div>'; }
  function ligaSug() {
    painel.querySelectorAll('[data-sg]').forEach(function (b) { b.onclick = function () { var l = b.nextElementSibling; l.hidden = !l.hidden; b.textContent = l.hidden ? 'Ver sugestões' : 'Esconder sugestões'; }; });
    painel.querySelectorAll('.sgc').forEach(function (b) { b.onclick = function () { var t = document.getElementById(b.dataset.al); if (t) { t.value = b.textContent; t.dispatchEvent(new Event('input')); } }; });
  }
  function val(nomeG) { var x = painel.querySelector('input[name="' + nomeG + '"]:checked'); return x ? x.value : null; }
  function painelAberto() { return painel && !painel.hidden; }
  function roda(lista, titulo) {
    var ativos = {}; lista.forEach(function (m) { ativos[m] = 1; });
    var gente = (CFG.membros || []).filter(function (m) { return m.equipe || ativos[m.id]; });
    return '<div class="roda" aria-label="' + esc(titulo) + '"><span class="rt">' + esc(titulo) + '</span>' + gente.map(function (m) {
      return '<span class="vz' + (ativos[m.id] ? ' on' : '') + '"><img src="' + BASE + m.especie + '.png" alt="">' + esc(m.id === EU ? 'você' : m.ini) + '</span>';
    }).join('') + '</div>';
  }
  var chavePainel = '';
  function renderPainel() {
    if (!painel) return;
    var A = S.atual, ch = S.fase + '|' + (A ? A.pid + A.fase : '') + '|' + (TELAO ? 't' : 'j');
    var foco = document.activeElement && painel.contains(document.activeElement) && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (ch === chavePainel) { atualizarVivo(); return; }
    if (foco && ch.split('|')[0] === chavePainel.split('|')[0] && ch.split('|')[1] === chavePainel.split('|')[1]) { atualizarVivo(); return; }
    chavePainel = ch;
    painel.innerHTML = TELAO ? htmlTelao() : htmlJogador();
    painel.hidden = !painel.innerHTML;
    ligar(); ligaSug(); atualizarVivo();
  }
  // partes que mudam sem refazer o formulario (listas, contadores)
  function atualizarVivo() {
    var A = S.atual;
    var el = document.getElementById('vivo');
    if (el) { var hv = htmlVivo(); if (hv !== el.dataset.h) { el.innerHTML = hv; el.dataset.h = hv; ligarVivo(); } }
    var cont = document.getElementById('hostCont'); if (cont) cont.textContent = contagemHost();
    if (A && A.fase === 'conversa') { var tm = document.getElementById('tempo'); if (tm) { var r = Math.max(0, TCONV - A.tc); tm.textContent = r > 0 ? 'Tempo sugerido: ' + Math.ceil(r / 60) + ' min. A praga espera.' : 'O tempo sugerido acabou. Combinem quando estiverem prontos.'; } }
  }
  function contagemHost() {
    var A = S.atual;
    if (S.fase === 'abertura') return Object.keys(S.climas).length + ' pessoas marcaram o clima.';
    if (S.fase === 'problemas') return S.probs.length + ' problemas até agora.';
    if (S.fase === 'bons') return S.bons.length + ' coisas boas até agora.';
    if (S.fase === 'eu') return Object.keys(S.euDe).length + ' pessoas marcaram o eu também.';
    if (S.fase === 'rodada' && A && A.fase === 'topo') return A.topos.length + ' de ' + nPres() + ' toparam.';
    if (S.fase === 'fecho') return S.obrigados.length + ' agradecimentos · ' + Object.keys(S.roti).length + ' avaliaram a retro.';
    return '';
  }
  function htmlGrafico() {
    var ord = S.probs.map(function (p) { return { p: p, n: euCount(p.id) }; }).sort(function (a, b) { return b.n - a.n || a.p.id - b.p.id; });
    var mx = Math.max.apply(null, [1].concat(ord.map(function (o) { return o.n; })));
    var tot = ord.reduce(function (a, o) { return a + o.n; }, 0), top3 = ord.slice(0, 3).reduce(function (a, o) { return a + o.n; }, 0), metade = Math.ceil(nPres() / 2);
    var meus = EU != null ? (S.euDe[EU] || []) : [];
    return '<div class="barras">' + ord.map(function (o) {
      return '<div class="br' + (o.n >= metade && o.n > 0 ? ' forte' : '') + '"><span class="bt">' + esc(o.p.txt) + (meus.indexOf(o.p.id) >= 0 ? ' <em>você</em>' : '') + '</span><span class="bb"><i style="width:' + Math.max(4, o.n / mx * 100) + '%"></i></span><b>' + o.n + '</b></div>';
    }).join('') + '</div><p class="sint"><b>Sintonia do time: ' + (tot ? Math.round(top3 / tot * 100) : 0) + '%</b> dos toques caíram nos 3 primeiros problemas. Em vermelho, o que metade do time ou mais sentiu.</p>';
  }
  function htmlVivo() {
    var A = S.atual;
    if (S.fase === 'rodada' && A && (A.fase === 'conversa')) {
      var jaApoiei = EU != null ? A.ideias.filter(function (d) { return d.apoios.indexOf(EU) >= 0; }).length >= APO : true;
      var top = ordenadas(A).slice(0, 3).map(function (d) { return d.id; });
      var pq = A.pq.length ? A.pq.map(function (x, i) { return '<p class="pqi"><b>' + esc(quem(x.dono)) + '</b> ' + esc(x.txt) + (i < MAXPQ ? ' <span>-1 vida</span>' : '') + '</p>'; }).join('') : '<p class="aj">Ninguém disse um porquê ainda.</p>';
      var n = participantes(A).length, mut = mutirao();
      var ideias = ordenadas(A).map(function (d) {
        var meuCartao = d.dono === EU, podeComp = !TELAO && EU != null;
        var opQuem = '<option value="">+ quem faz</option><option value="TIME">o time todo</option>' + (CFG.membros || []).map(function (m) { return '<option value="' + m.id + '">' + esc(m.id === EU ? 'eu' : m.ini) + '</option>'; }).join('');
        var linhaRaiz = d.raiz >= 0 && A.pq[d.raiz] ? '<p class="rz">ataca: ' + esc(A.pq[d.raiz].txt) + '</p>' : '';
        var cp = '';
        if (d.raiz < 0 && A.pq.length && podeComp) cp += '<select data-c="raiz" data-i="' + d.id + '" aria-label="Ligar a um porquê"><option value="">+ ataca qual porquê</option>' + A.pq.map(function (x, j) { return '<option value="' + j + '">' + esc(x.txt) + '</option>'; }).join('') + '</select>';
        cp += d.quem ? '<span class="ok">quem: ' + esc(d.quem === 'TIME' ? 'o time todo' : quem(d.quem)) + '</span>' : podeComp ? '<select data-c="quem" data-i="' + d.id + '" aria-label="Completar quem">' + opQuem + '</select>' : '';
        cp += d.prazo ? '<span class="ok">até ' + esc(d.prazo) + '</span>' : podeComp ? '<select data-c="prazo" data-i="' + d.id + '" aria-label="Completar prazo"><option value="">+ até quando</option>' + PRAZOS.map(function (q) { return '<option>' + q + '</option>'; }).join('') + '</select>' : '';
        var btn = (!TELAO && !meuCartao && EU != null) ? '<button type="button" class="sec mini" data-ap="' + d.id + '"' + (jaApoiei || d.apoios.indexOf(EU) >= 0 ? ' disabled' : '') + '>' + (d.apoios.indexOf(EU) >= 0 ? 'Apoiada' : 'Apoiar') + '</button>' : '';
        return '<article class="id' + (top.indexOf(d.id) >= 0 ? ' top' : '') + '"><img src="' + BASE + esp(d.dono) + '.png" alt=""><div><p class="q"><b>' + esc(d.dono === EU ? 'Você' : ini(d.dono)) + '</b> · ' + TIPOS[d.t].papel + (top.indexOf(d.id) >= 0 ? ' · vai virar planta' : '') + '</p><p class="tx">' + esc(d.txt) + '</p>' + linhaRaiz +
          '<p class="cp">' + cp + '</p><p class="ap">' + (d.apoios.length ? 'Apoiam: ' + d.apoios.map(quem).join(', ') : 'Ninguém apoiou ainda') + '</p></div><div class="lado"><span class="f">' + forca(d) + '</span><small>força</small>' + btn + '</div></article>';
      }).join('') || '<p class="aj">O mural está vazio. Quem tiver uma ideia, põe aqui; o resto apoia ou completa.</p>';
      return roda(participantes(A), 'Quem já falou nesta rodada:') + '<section class="pq"><p class="rot">1. Por que isso acontece?</p>' + pq + '<p class="aj">Vida da praga agora: ' + A.vida + '</p></section>' +
        '<p class="mut' + (n >= mut ? ' on' : '') + '">Mutirão: ' + n + ' de ' + mut + ' pessoas participaram' + (n >= mut ? ', cada planta desta rodada ganha +1.' : '. Com ' + mut + ', cada planta ganha +1.') + '</p>' +
        '<p class="rot">2. O que a gente faz?</p><div class="mural">' + ideias + '</div>';
    }
    if (S.fase === 'rodada' && A && A.fase === 'topo') return roda(A.topos, 'Já toparam:');
    if (S.fase === 'abertura') return roda(Object.keys(S.climas).map(Number), 'Já marcaram:');
    if (S.fase === 'eu') return roda(Object.keys(S.euDe).map(Number), 'Já marcaram:');
    if (S.fase === 'euRes') return htmlGrafico();
    if (S.fase === 'fecho') return roda(S.obrigados.map(function (o) { return o.de; }), 'Já agradeceram:');
    return '';
  }
  function htmlPlano() {
    var A = S.atual;
    return '<div class="mural">' + (A.esc || []).map(function (i) {
      var d = A.ideias[i]; if (!d) return '';
      return '<article class="id top"><img src="' + BASE + esp(d.dono) + '.png" alt=""><div><p class="q"><b>' + esc(d.dono === EU ? 'Você' : ini(d.dono)) + '</b> · ' + TIPOS[d.t].papel + '</p><p class="tx">' + esc(d.txt) + '</p><p class="ap">' + (d.quem ? 'quem: ' + esc(d.quem === 'TIME' ? 'o time todo' : quem(d.quem)) : 'sem dono ainda') + (d.prazo ? ' · até ' + esc(d.prazo) : '') + '</p></div><div class="lado"><span class="f">' + forca(d) + '</span><small>força</small></div></article>';
    }).join('') + '</div>';
  }
  function htmlJogador() {
    var A = S.atual, h = '';
    if (EU == null) return '<p class="passo">Retro da sprint</p><h2>Entre no Meu jardim para jogar</h2><p class="aj">Você está vendo o tabuleiro. Para mandar problemas, ideias e apoios, entre com seu PIN.</p><div class="acoes"><a class="btn btn-primary" href="/eu">Entrar no Meu jardim</a></div>';
    if (S.fase === 'abertura') {
      h = '<p class="passo">Abertura</p><h2>Antes de começar</h2><blockquote class="dp">"Independentemente do que descobrirmos, entendemos e acreditamos de verdade que todos fizeram o melhor trabalho que podiam, dado o que sabiam na época, suas habilidades, os recursos disponíveis e a situação."<small>Diretiva Primária das retrospectivas, de Norm Kerth. Leiam juntos em voz alta.</small></blockquote>' +
        '<p class="rot">Como você chega nesta retro?</p><p class="aj">Ninguém vê o que você marcou. O céu do jardim mostra a mistura do time.</p>' + chips('clima', CLIMAS, S.climas[EU] || 'sol') +
        '<div class="acoes"><button type="button" class="pri" id="bClima">' + (S.climas[EU] ? 'Trocar' : 'Marcar') + '</button></div><div id="vivo"></div>';
    } else if (S.fase === 'problemas' || S.fase === 'bons') {
      var pb = S.fase === 'problemas';
      h = '<p class="passo">' + (pb ? 'Momento 1 de 3' : 'Momento 2 de 3') + '</p><h2>' + (pb ? 'O que atrapalhou nesta sprint?' : 'O que foi bom nesta sprint?') + '</h2><p class="aj">' + (pb ? 'Um problema por vez, quantos quiser. Ninguém vê quem escreveu.' : 'Cada coisa boa vira uma abelha que ajuda as soluções da mesma área.') + '</p>' +
        '<label class="campo">Em poucas palavras<textarea id="fTxt" rows="2" maxlength="80"></textarea></label>' + sug('fTxt', pb ? SUG.problema : SUG.bom) +
        '<p class="rot">Em que parte do dia?</p>' + chips('area', AREAS, 'dev') + '<p class="aj" id="fMsg">' + ((pb ? meu.probs : meu.bons) ? 'Você já mandou ' + (pb ? meu.probs : meu.bons) + '.' : '') + '</p>' +
        '<div class="acoes"><button type="button" class="pri" id="bEnviar">' + (pb ? 'Soltar praga' : 'Soltar abelha') + '</button></div>';
    } else if (S.fase === 'eu') {
      var sel = meu.eu || (S.euDe[EU] || []).slice();
      meu.eu = sel;
      h = '<p class="passo">Momento 3 de 3</p><h2>Eu também</h2><p class="aj">Você tem 3 toques. Toque nos problemas que você também sentiu.</p><div class="lista">' + S.probs.map(function (p) {
        var on = sel.indexOf(p.id) >= 0;
        return '<button type="button" class="it' + (on ? ' on' : '') + '" data-p="' + p.id + '" aria-pressed="' + on + '"><span>' + esc(p.txt) + '</span><small>' + ZONA[p.rota] + '</small></button>';
      }).join('') + '</div><p class="aj" id="euRest">' + (3 - sel.length) + ' toque(s) restantes</p><div class="acoes"><button type="button" class="pri" id="bEu">' + (S.euDe[EU] ? 'Atualizar' : 'Confirmar') + '</button></div><div id="vivo"></div>';
    } else if (S.fase === 'euRes') {
      h = '<p class="passo">Momento 3 · resultado</p><h2>O que o time mais sentiu</h2><p class="aj">A ordem das conversas sai daqui.</p><div id="vivo"></div>';
    } else if (S.fase === 'rodada' && A && A.fase === 'conversa') {
      var jaIdeia = A.ideias.some(function (d) { return d.dono === EU; }), jaPq = A.pq.some(function (x) { return x.dono === EU; });
      h = '<p class="passo">Rodada ' + S.rodadas + ' · conversa do time</p><h2>' + esc(A.txt) + '</h2><p class="aj" id="tempo"></p>' +
        (jaPq ? '' : '<div class="linha"><input id="pTxt" maxlength="60" placeholder="Por que isso acontece?" aria-label="Seu porquê"><button type="button" class="sec mini" id="bPq">Pôr</button></div>' + sug('pTxt', SUG.porque)) +
        '<div id="vivo"></div>' +
        (jaIdeia ? '' : '<details id="mNova"' + (A.ideias.length ? '' : ' open') + '><summary>Pôr a minha ideia no mural</summary><div class="tipos" role="radiogroup" aria-label="Tipo de solução">' + Object.keys(TIPOS).map(function (t) {
          return '<label class="tp"><input type="radio" name="tipo" value="' + t + '"' + (t === 'bambu' ? ' checked' : '') + '><span><img src="' + BASE + t + '.png" alt=""><b>' + TIPOS[t].papel + '</b><small>' + TIPOS[t].efeito + '</small></span></label>';
        }).join('') + '</div><label class="campo">Ideia<input id="fTxt" maxlength="60" placeholder="Ex.: quebrar o card em 3"></label>' + sug('fTxt', SUG.ideia) +
          '<label class="campo">Ataca qual porquê? (+1 de força; dá para ligar depois)<select id="fRaiz"><option value="-1">nenhum em especial</option>' + A.pq.map(function (x, i) { return '<option value="' + i + '">' + esc(x.txt) + '</option>'; }).join('') + '</select></label>' +
          '<div class="acoes"><button type="button" class="pri" id="bIdeia">Pôr no mural</button></div></details>');
    } else if (S.fase === 'rodada' && A && A.fase === 'topo') {
      var topei = A.topos.indexOf(EU) >= 0;
      h = '<p class="passo">Rodada ' + S.rodadas + ' · combinar</p><h2>Todo mundo topa este plano?</h2><p class="aj">Se todos toparem, as plantas ganham a raiz do time (+1 de força cada). "Ainda não" leva todo mundo de volta à conversa.</p>' + htmlPlano() +
        '<div id="vivo"></div><div class="acoes"><button type="button" class="sec" id="bNao">Ainda não</button><button type="button" class="pri" id="bTopo"' + (topei ? ' disabled' : '') + '>' + (topei ? 'Você topou' : 'Eu topo') + '</button></div>';
    } else if (S.fase === 'rodada') {
      var minhas = Object.keys(S.plantas).filter(function (k) { return S.plantas[k].dono === EU; }).length;
      h = '<p class="passo">Rodada ' + S.rodadas + ' · defesa</p><h2>' + (A ? esc(A.txt) : 'Próxima praga chegando') + '</h2><p class="aj">Quando o anel amarelo piscar numa planta, toque nela no tabuleiro para atacar. Qualquer pessoa pode tocar em qualquer planta.' + (minhas ? ' Você tem ' + minhas + ' planta(s) no jardim, com a sua etiqueta.' : '') + '</p>';
    } else if (S.fase === 'fecho') {
      var feitos = S.obrigados.filter(function (o) { return o.de === EU; }).map(function (o) { return o.para; });
      var faltam = (CFG.membros || []).filter(function (m) { return m.id !== EU && feitos.indexOf(m.id) < 0; });
      h = '<p class="passo">Encerramento</p><h2>A quem você quer agradecer?</h2><p class="aj">Quantos quiser, um obrigado por pessoa. Cada um faz uma planta florescer.</p>' +
        (feitos.length ? '<p class="aj"><b>Você já agradeceu:</b> ' + feitos.map(ini).join(', ') + '</p>' : '') +
        (faltam.length ? chips('para', faltam.map(function (m) { return [m.id, m.ini]; }), faltam[0].id) + '<label class="campo">Pelo quê (opcional)<input id="fTxt" maxlength="60"></label>' + sug('fTxt', SUG.obrigado) + '<div class="acoes"><button type="button" class="pri" id="bObr">Mandar obrigado</button></div>' : '<p class="aj">Você agradeceu todo mundo.</p>') +
        '<p class="rot">Quanto esta retro valeu o tempo?</p>' + chips('roti', [[0, '0'], [1, '1'], [2, '2'], [3, '3'], [4, '4']], S.roti[EU] != null ? S.roti[EU] : 3) + '<p class="aj">0 = perdemos tempo, 4 = valeu muito.</p><div class="acoes"><button type="button" class="sec" id="bRoti">' + (S.roti[EU] != null ? 'Trocar nota' : 'Dar nota') + '</button></div><div id="vivo"></div>';
    } else if (S.fase === 'fim') {
      h = '<p class="passo">Retro encerrada</p><h2>Compromissos da sprint</h2><ul class="comp">' + S.hist.map(function (x) { return '<li class="' + (x.ok ? 'ok' : '') + '"><b>' + esc(x.txt) + '</b><span>' + (x.ok && x.acao ? esc(x.acao) + ' · ' + esc(ini(x.dono)) : esc(x.motivo || 'em aberto, volta na próxima retro')) + '</span></li>'; }).join('') + '</ul>';
    }
    return h;
  }
  function htmlTelao() {
    if (S.fase === 'fim') return '';            // o resumo dos compromissos ocupa o tabuleiro
    var A = S.atual, h = '<p class="passo">Telão · quem conduz</p>', prox = '';
    if (S.fase === 'abertura') { h += '<h2>Abertura</h2><blockquote class="dp">"Independentemente do que descobrirmos, entendemos e acreditamos de verdade que todos fizeram o melhor trabalho que podiam, dado o que sabiam na época, suas habilidades, os recursos disponíveis e a situação."<small>Leiam juntos. Cada pessoa abre a retro no próprio aparelho (Hoje, botão Retro) e marca como chega.</small></blockquote>'; prox = 'Próximo: problemas'; }
    else if (S.fase === 'problemas') { h += '<h2>O que atrapalhou?</h2><p class="aj">Cada pessoa escreve no próprio aparelho. Os problemas chegam no portão, sem nome.</p>'; prox = 'Próximo: o que foi bom'; }
    else if (S.fase === 'bons') { h += '<h2>O que foi bom?</h2><p class="aj">Cada coisa boa vira uma abelha na colmeia da área.</p>'; prox = 'Próximo: eu também'; }
    else if (S.fase === 'eu') { h += '<h2>Eu também</h2><p class="aj">Cada pessoa toca em até 3 problemas que também sentiu.</p>'; prox = 'Ver o resultado'; }
    else if (S.fase === 'euRes') { h += '<h2>O que o time mais sentiu</h2>'; prox = 'Começar as conversas'; }
    else if (S.fase === 'rodada' && A && A.fase === 'conversa') { h += '<h2>' + esc(A.txt) + '</h2><p class="aj" id="tempo"></p>'; prox = 'Combinar e plantar'; }
    else if (S.fase === 'rodada' && A && A.fase === 'topo') { h += '<h2>Todo mundo topa?</h2>' + htmlPlano(); prox = 'Plantar sem esperar todos'; }
    else if (S.fase === 'rodada') { h += '<h2>Defesa</h2><p class="aj">Toque nas plantas com anel amarelo. Elas também atacam sozinhas depois de um instante.</p>'; prox = ''; }
    else if (S.fase === 'fecho') { h += '<h2>Encerramento</h2><p class="aj">Cada pessoa agradece colegas e dá a nota da retro no próprio aparelho.</p>'; prox = 'Fechar a retro'; }
    else if (S.fase === 'fim') { h += '<h2>Retro encerrada</h2><p class="aj">Os compromissos estão no tabuleiro. Esta tela pode ser fechada.</p>'; }
    h += '<p class="mut on" id="hostCont"></p><div id="vivo"></div>';
    if (prox) h += '<div class="acoes"><button type="button" class="pri" id="bProx">' + prox + '</button></div>';
    if (S.fase === 'rodada') h += '<div class="acoes"><button type="button" class="sec mini" id="bEncerrar">Encerrar as rodadas</button></div>';
    return h;
  }
  function ligar() {
    var $ = function (id) { return document.getElementById(id); };
    if (TELAO) {
      if ($('bProx')) $('bProx').onclick = function () {
        if (S.fase === 'abertura') irPara('problemas');
        else if (S.fase === 'problemas') irPara('bons');
        else if (S.fase === 'bons') irPara('eu');
        else if (S.fase === 'eu') irPara('euRes');
        else if (S.fase === 'euRes') { if (!S.probs.length) { aviso('Ninguém escreveu problema. Voltem ao momento 1.', 'erro'); return; } montarFila(); S.fase = 'rodada'; tIntervalo = 0.5; }
        else if (S.fase === 'rodada' && S.atual && S.atual.fase === 'conversa') { if (!S.atual.ideias.length && !confirm('Ninguém pôs ideia no mural. Plantar mesmo assim (a praga passa sem defesa nova)?')) return; propoeTopo(); }
        else if (S.fase === 'rodada' && S.atual && S.atual.fase === 'topo') combinar();
        else if (S.fase === 'fecho') { S.fase = 'fim'; }
        renderPainel(); cicloHost();
      };
      if ($('bEncerrar')) $('bEncerrar').onclick = function () { if (confirm('Encerrar as rodadas agora? Os problemas que faltam vão para a composteira.')) { fimDasRodadas(); renderPainel(); cicloHost(); } };
      return;
    }
    if ($('bClima')) $('bClima').onclick = function () { acao('clima', { v: val('clima') }).then(function (ok) { if (ok) aviso('Marcado.', 'sucesso'); }); };
    if ($('bEnviar')) $('bEnviar').onclick = function () {
      var t = $('fTxt').value.trim(); if (!t) { $('fMsg').textContent = 'Escreva algo antes.'; return; }
      var pb = S.fase === 'problemas';
      acao(pb ? 'problema' : 'bom', { txt: t, area: val('area') }).then(function (ok) {
        if (!ok) return; if (pb) meu.probs++; else meu.bons++; $('fTxt').value = ''; $('fMsg').textContent = 'Você já mandou ' + (pb ? meu.probs : meu.bons) + '. Pode mandar mais.';
      });
    };
    painel.querySelectorAll('.it[data-p]').forEach(function (b) {
      b.onclick = function () {
        var id = Number(b.dataset.p), i = meu.eu.indexOf(id);
        if (i >= 0) meu.eu.splice(i, 1); else if (meu.eu.length < 3) meu.eu.push(id); else { aviso('Você já usou os 3 toques. Desmarque um.', 'info'); return; }
        b.classList.toggle('on', meu.eu.indexOf(id) >= 0); b.setAttribute('aria-pressed', meu.eu.indexOf(id) >= 0);
        $('euRest').textContent = (3 - meu.eu.length) + ' toque(s) restantes';
      };
    });
    if ($('bEu')) $('bEu').onclick = function () { acao('eu', { ids: meu.eu }).then(function (ok) { if (ok) aviso('Eu também enviado.', 'sucesso'); }); };
    if ($('bPq')) $('bPq').onclick = function () { var v = $('pTxt').value.trim(); if (!v) return; acao('porque', { txt: v, rodada: S.rodadas }).then(function (ok) { if (ok) { var l = $('pTxt').closest('.linha'); if (l) l.remove(); var sg = painel.querySelector('[data-sg="pTxt"]'); if (sg) sg.parentNode.remove(); } }); };
    if ($('bIdeia')) $('bIdeia').onclick = function () {
      var v = $('fTxt').value.trim(); if (!v) { aviso('Escreva a ideia.', 'info'); return; }
      acao('ideia', { t: val('tipo'), txt: v, raiz: Number($('fRaiz').value), rodada: S.rodadas }).then(function (ok) { if (ok) { var d = $('mNova'); if (d) d.remove(); aviso('Ideia no mural.', 'sucesso'); } });
    };
    if ($('bTopo')) $('bTopo').onclick = function () { acao('topo', { rodada: S.rodadas }).then(function (ok) { if (ok) { $('bTopo').disabled = true; $('bTopo').textContent = 'Você topou'; } }); };
    if ($('bNao')) $('bNao').onclick = function () { acao('naotopo', { rodada: S.rodadas }); };
    if ($('bObr')) $('bObr').onclick = function () { var para = Number(val('para')); acao('obrigado', { para: para, txt: $('fTxt').value.trim() }).then(function (ok) { if (ok) { aviso('Obrigado enviado.', 'sucesso'); chavePainel = ''; } }); };
    if ($('bRoti')) $('bRoti').onclick = function () { acao('roti', { v: Number(val('roti')) }).then(function (ok) { if (ok) aviso('Nota registrada.', 'sucesso'); }); };
  }
  function ligarVivo() {
    if (TELAO) return;
    painel.querySelectorAll('[data-ap]').forEach(function (b) { b.onclick = function () { b.disabled = true; acao('apoio', { ideia: Number(b.dataset.ap), rodada: S.rodadas }); }; });
    painel.querySelectorAll('select[data-c]').forEach(function (sl) {
      sl.onchange = function () { if (!sl.value) return; sl.disabled = true; acao('completar', { ideia: Number(sl.dataset.i), campo: sl.dataset.c, valor: sl.dataset.c === 'raiz' ? Number(sl.value) : sl.value, rodada: S.rodadas }); };
    });
    var fr = document.getElementById('fRaiz');
    if (fr && S.atual && fr.options.length !== S.atual.pq.length + 1) {
      var v = fr.value; fr.innerHTML = '<option value="-1">nenhum em especial</option>' + S.atual.pq.map(function (x, i) { return '<option value="' + i + '">' + esc(x.txt) + '</option>'; }).join(''); fr.value = v;
    }
  }
  // a lista viva nao pode sumir com o select aberto
  function vivoOcupado() { var a = document.activeElement; return a && a.tagName === 'SELECT' && painel.contains(a); }
  var _atualizarVivo = atualizarVivo;
  atualizarVivo = function () { if (vivoOcupado()) return; _atualizarVivo(); };

  // ---------------------------------------------------------------- partida
  var bAss = document.getElementById('retro-assumir');
  if (bAss) bAss.onclick = function () { postar('/api/retro/assumir', {}).then(function (r) { if (r.ok) location.href = r.j.url; else aviso((r.j && r.j.erro) || 'Não deu.', 'erro'); }); };

  function retomar(e) {
    if (!e || !e.v) return;
    S = e; delete S.pragas; delete S.t;
    Object.keys(S.plantas).forEach(function (k) { S.plantas[k].pronta = 0; });
    if (S.fase === 'rodada' && S.atual) {
      if (S.atual.fase === 'defesa') { S.atual.fase = 'conversa'; S.atual.esc = null; S.atual.topos = []; S.atual.plantadas = []; }
      pragaDoAtual(110); pragas[0].vida = S.atual.vida; pragas[0].max = S.atual.max;
    }
  }
  pintaFundo();
  var ult = performance.now(), acum = 0;
  function laco(t) {
    var dt = Math.min(0.05, (t - ult) / 1000); ult = t;
    if (TELAO) {
      passo(dt);
      pragas.forEach(function (p) { if (p.principal && S.atual) { p.vida = S.atual.vida; p.max = S.atual.max; } });
      acum += dt; if (acum > 0.25) { acum = 0; atualizarVivo(); }
    } else interpolar(dt);
    desenha(t); requestAnimationFrame(laco);
  }
  function iniciar() {
    if (TELAO) {
      fetch('/api/retro/estado').then(function (r) { return r.json(); }).then(function (j) {
        if (j.estado) retomar(j.estado);
        if (!S.presentes) S.presentes = [];
        renderPainel(); cicloHost(); setInterval(cicloHost, 1000);
      }).catch(function () { renderPainel(); setInterval(cicloHost, 1000); });
    } else {
      cicloJogador(); setInterval(cicloJogador, 1000);
      document.addEventListener('visibilitychange', function () { if (!document.hidden) cicloJogador(); });
    }
    requestAnimationFrame(laco);
  }
  (document.fonts && document.fonts.load ? document.fonts.load('800 20px "Bricolage Grotesque"') : Promise.resolve()).catch(function () {}).then(function () { pintaFundo(); iniciar(); });
})();
