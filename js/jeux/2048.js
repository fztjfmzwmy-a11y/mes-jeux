// 2048 : fusionne les tuiles identiques pour atteindre 2048.
App.enregistrer({
  id: '2048',
  nom: '2048',
  icone: '🔢',
  desc: 'Fusionne les tuiles',
  lancer(scene) {
    const { el, record, glissement, touches } = App.outils;
    const COULEURS = {
      2: '#eee4da', 4: '#ede0c8', 8: '#f2b179', 16: '#f59563', 32: '#f67c5f', 64: '#f65e3b',
      128: '#edcf72', 256: '#edcc61', 512: '#edc850', 1024: '#edc53f', 2048: '#edc22e',
    };
    let grille, score, gagne, fini;

    const scores = el('div', { className: 'scores' });
    const statut = el('div', { className: 'statut' });
    const plateau = el('div', { className: 'g2048' });
    const tuiles = [];
    for (let i = 0; i < 16; i++) {
      const t = el('div', { className: 'tuile2048' });
      tuiles.push(t);
      plateau.append(t);
    }
    const rejouer = el('button', { className: 'btn principal', textContent: 'Nouvelle partie', onclick: nouvellePartie });
    const aide = el('p', { className: 'aide', textContent: 'Flèches / ZQSD ou glisser le doigt.' });
    scene.append(scores, statut, plateau, rejouer, aide);

    const clavier = e => {
      const d = touches[e.key] || touches[e.key.toLowerCase()];
      if (d) { e.preventDefault(); bouger(d); }
    };
    document.addEventListener('keydown', clavier);
    glissement(plateau, bouger);

    function ajouterTuile() {
      const vides = grille.map((v, i) => v ? -1 : i).filter(i => i >= 0);
      if (!vides.length) return;
      grille[vides[Math.floor(Math.random() * vides.length)]] = Math.random() < 0.9 ? 2 : 4;
    }

    // Fait glisser une ligne vers la gauche et renvoie [nouvelle ligne, points gagnés].
    function glisserLigne(ligne) {
      const pleins = ligne.filter(Boolean);
      const res = [];
      let points = 0;
      for (let i = 0; i < pleins.length; i++) {
        if (pleins[i] === pleins[i + 1]) {
          res.push(pleins[i] * 2);
          points += pleins[i] * 2;
          i++;
        } else res.push(pleins[i]);
      }
      while (res.length < 4) res.push(0);
      return [res, points];
    }

    // Indices des 4 lignes, chacune ordonnée dans le sens du mouvement.
    function lignes(d) {
      const out = [];
      for (let a = 0; a < 4; a++) {
        const l = [];
        for (let b = 0; b < 4; b++) {
          if (d === 'gauche') l.push(a * 4 + b);
          if (d === 'droite') l.push(a * 4 + (3 - b));
          if (d === 'haut') l.push(b * 4 + a);
          if (d === 'bas') l.push((3 - b) * 4 + a);
        }
        out.push(l);
      }
      return out;
    }

    function bouger(d) {
      if (fini) return;
      let change = false;
      for (const idx of lignes(d)) {
        const [res, pts] = glisserLigne(idx.map(i => grille[i]));
        idx.forEach((i, k) => { if (grille[i] !== res[k]) change = true; grille[i] = res[k]; });
        score += pts;
      }
      if (!change) return;
      ajouterTuile();
      if (!gagne && grille.includes(2048)) {
        gagne = true;
        statut.textContent = 'Tu as atteint 2048 ! 🏆 Continue si tu veux.';
      }
      if (!mouvementPossible()) {
        fini = true;
        statut.textContent = 'Plus aucun mouvement possible 😵';
      }
      record('2048', score);
      afficher();
    }

    function mouvementPossible() {
      if (grille.includes(0)) return true;
      for (let i = 0; i < 16; i++) {
        if (i % 4 < 3 && grille[i] === grille[i + 1]) return true;
        if (i < 12 && grille[i] === grille[i + 4]) return true;
      }
      return false;
    }

    function afficher() {
      grille.forEach((v, i) => {
        const t = tuiles[i];
        t.textContent = v || '';
        t.style.background = v ? (COULEURS[v] || '#3c3a32') : '';
        t.style.color = v > 4 ? '#fff' : '#555';
        t.style.fontSize = v >= 1024 ? 'clamp(.9rem, 5vw, 1.5rem)' : '';
      });
      scores.innerHTML = `
        <div class="score"><small>Score</small><b>${score}</b></div>
        <div class="score"><small>Record</small><b>${record('2048')}</b></div>`;
    }

    function nouvellePartie() {
      grille = Array(16).fill(0);
      score = 0;
      gagne = false;
      fini = false;
      statut.textContent = 'Atteins la tuile 2048 !';
      ajouterTuile();
      ajouterTuile();
      afficher();
    }

    nouvellePartie();
    return () => document.removeEventListener('keydown', clavier);
  },
});
