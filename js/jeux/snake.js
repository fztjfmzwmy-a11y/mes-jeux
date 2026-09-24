// Snake : mange les pommes sans te mordre la queue.
App.enregistrer({
  id: 'snake',
  nom: 'Snake',
  icone: '🐍',
  desc: 'Mange les pommes',
  lancer(scene) {
    const { el, record, glissement, touches } = App.outils;
    const N = 20, TAILLE = 21;
    const DIRS = { haut: [0, -1], bas: [0, 1], gauche: [-1, 0], droite: [1, 0] };
    let serpent, dir, fileDirs, pomme, score, boucle = null, enCours = false;

    const scores = el('div', { className: 'scores' });
    const canvas = el('canvas', { className: 'plateau', width: N * TAILLE, height: N * TAILLE });
    const ctx = canvas.getContext('2d');
    const bouton = el('button', { className: 'btn principal', textContent: 'Jouer', onclick: demarrer });
    const pad = el('div', { className: 'pad' });
    for (const d of ['', 'haut', '', 'gauche', 'bas', 'droite']) {
      const b = el('button', { className: d ? '' : 'vide', textContent: { haut: '▲', bas: '▼', gauche: '◀', droite: '▶' }[d] || '' });
      if (d) b.onclick = () => changer(d);
      pad.append(b);
    }
    const aide = el('p', { className: 'aide', textContent: 'Flèches / ZQSD, glisser le doigt ou utiliser les boutons.' });
    scene.append(scores, canvas, bouton, pad, aide);

    const clavier = e => {
      const d = touches[e.key] || touches[e.key.toLowerCase()];
      if (d) { e.preventDefault(); changer(d); }
      else if (e.key === ' ' && !enCours) { e.preventDefault(); demarrer(); }
    };
    document.addEventListener('keydown', clavier);
    glissement(canvas, changer);

    function changer(d) {
      if (!enCours) return;
      // On empile les virages pour ne pas en perdre quand ils sont rapides.
      const derniere = fileDirs.length ? fileDirs[fileDirs.length - 1] : dir;
      const [dx, dy] = DIRS[d];
      if (dx === -derniere[0] && dy === -derniere[1]) return;
      if (dx === derniere[0] && dy === derniere[1]) return;
      if (fileDirs.length < 3) fileDirs.push([dx, dy]);
    }

    function placerPomme() {
      do {
        pomme = [Math.floor(Math.random() * N), Math.floor(Math.random() * N)];
      } while (serpent.some(([x, y]) => x === pomme[0] && y === pomme[1]));
    }

    function demarrer() {
      serpent = [[10, 10], [9, 10], [8, 10]];
      dir = [1, 0];
      fileDirs = [];
      score = 0;
      enCours = true;
      bouton.hidden = true;
      placerPomme();
      majScores();
      planifier();
    }

    function vitesse() { return Math.max(60, 140 - score * 3); }

    function planifier() {
      clearTimeout(boucle);
      boucle = setTimeout(() => { etape(); if (enCours) planifier(); }, vitesse());
    }

    function etape() {
      if (fileDirs.length) dir = fileDirs.shift();
      const tete = [serpent[0][0] + dir[0], serpent[0][1] + dir[1]];
      const mange = tete[0] === pomme[0] && tete[1] === pomme[1];
      const corps = mange ? serpent : serpent.slice(0, -1);
      const hors = tete[0] < 0 || tete[1] < 0 || tete[0] >= N || tete[1] >= N;
      if (hors || corps.some(([x, y]) => x === tete[0] && y === tete[1])) return perdu();
      serpent.unshift(tete);
      if (mange) { score++; majScores(); placerPomme(); } else serpent.pop();
      dessiner();
    }

    function perdu() {
      enCours = false;
      clearTimeout(boucle);
      record('snake', score);
      majScores();
      dessiner();
      ctx.fillStyle = 'rgba(0,0,0,.6)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'center';
      ctx.font = 'bold 36px system-ui';
      ctx.fillText('Perdu !', canvas.width / 2, canvas.height / 2 - 10);
      ctx.font = '20px system-ui';
      ctx.fillText(`Score : ${score}`, canvas.width / 2, canvas.height / 2 + 24);
      bouton.textContent = 'Rejouer';
      bouton.hidden = false;
    }

    function majScores() {
      scores.innerHTML = `
        <div class="score"><small>Score</small><b>${score || 0}</b></div>
        <div class="score"><small>Record</small><b>${record('snake')}</b></div>`;
    }

    function dessiner() {
      ctx.fillStyle = '#12152b';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#181c38';
      for (let x = 0; x < N; x++) for (let y = 0; y < N; y++) {
        if ((x + y) % 2) ctx.fillRect(x * TAILLE, y * TAILLE, TAILLE, TAILLE);
      }
      if (pomme) {
        ctx.font = `${TAILLE - 2}px system-ui`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('🍎', pomme[0] * TAILLE + TAILLE / 2, pomme[1] * TAILLE + TAILLE / 2 + 1);
      }
      (serpent || []).forEach(([x, y], i) => {
        ctx.fillStyle = i === 0 ? '#9bf5b5' : '#5ee08a';
        ctx.beginPath();
        ctx.roundRect(x * TAILLE + 1, y * TAILLE + 1, TAILLE - 2, TAILLE - 2, 5);
        ctx.fill();
      });
    }

    majScores();
    dessiner();
    return () => {
      clearTimeout(boucle);
      document.removeEventListener('keydown', clavier);
    };
  },
});
