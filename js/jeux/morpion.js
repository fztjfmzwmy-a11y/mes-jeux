// Morpion : 2 joueurs ou contre l'ordinateur (minimax, imbattable en mode difficile).
App.enregistrer({
  id: 'morpion',
  nom: 'Morpion',
  icone: '❌',
  desc: 'Aligne 3 symboles',
  lancer(scene) {
    const { el } = App.outils;
    const LIGNES = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
    let grille, tour, fini, mode = 'ia-facile', minuteur = null;
    const scores = { X: 0, O: 0, nul: 0 };

    const statut = el('div', { className: 'statut' });
    const plateau = el('div', { className: 'morpion' });
    const tableau = el('div', { className: 'scores' });
    const modes = el('div', { className: 'barre' });
    const cases = [];

    for (const [val, label] of [['2j', '2 joueurs'], ['ia-facile', 'IA facile'], ['ia-difficile', 'IA difficile']]) {
      const b = el('button', { className: 'btn', textContent: label });
      b.dataset.mode = val;
      b.onclick = () => { mode = val; majModes(); nouvellePartie(); };
      modes.append(b);
    }
    for (let i = 0; i < 9; i++) {
      const c = el('button');
      c.onclick = () => jouer(i);
      cases.push(c);
      plateau.append(c);
    }
    const rejouer = el('button', { className: 'btn principal', textContent: 'Nouvelle partie', onclick: nouvellePartie });
    scene.append(modes, statut, plateau, tableau, rejouer);

    function majModes() {
      for (const b of modes.children) b.classList.toggle('actif', b.dataset.mode === mode);
    }

    function gagnant(g) {
      for (const l of LIGNES) {
        const [a, b, c] = l;
        if (g[a] && g[a] === g[b] && g[a] === g[c]) return { joueur: g[a], ligne: l };
      }
      return g.every(Boolean) ? { joueur: 'nul' } : null;
    }

    function minimax(g, joueur) {
      const r = gagnant(g);
      if (r) return { score: r.joueur === 'O' ? 10 : r.joueur === 'X' ? -10 : 0 };
      let meilleur = { score: joueur === 'O' ? -Infinity : Infinity };
      for (let i = 0; i < 9; i++) {
        if (g[i]) continue;
        g[i] = joueur;
        const { score } = minimax(g, joueur === 'O' ? 'X' : 'O');
        g[i] = null;
        if (joueur === 'O' ? score > meilleur.score : score < meilleur.score) meilleur = { score, coup: i };
      }
      return meilleur;
    }

    function coupIA() {
      const libres = grille.map((v, i) => v ? null : i).filter(i => i !== null);
      if (mode === 'ia-facile' && Math.random() < 0.6) {
        return libres[Math.floor(Math.random() * libres.length)];
      }
      return minimax([...grille], 'O').coup;
    }

    function jouer(i) {
      if (fini || grille[i]) return;
      if (mode !== '2j' && tour === 'O') return;
      poser(i);
      if (!fini && mode !== '2j') minuteur = setTimeout(() => poser(coupIA()), 350);
    }

    function poser(i) {
      if (fini) return;
      grille[i] = tour;
      tour = tour === 'X' ? 'O' : 'X';
      const r = gagnant(grille);
      if (r) {
        fini = true;
        scores[r.joueur]++;
        if (r.ligne) r.ligne.forEach(k => cases[k].classList.add('gagne'));
      }
      afficher(r);
    }

    function afficher(r) {
      cases.forEach((c, i) => {
        c.textContent = grille[i] || '';
        c.classList.toggle('x', grille[i] === 'X');
        c.classList.toggle('o', grille[i] === 'O');
      });
      const nomO = mode === '2j' ? 'O' : 'Ordinateur';
      if (!r) statut.textContent = `Au tour de ${tour === 'X' ? 'X' : nomO}`;
      else if (r.joueur === 'nul') statut.textContent = 'Match nul 🤝';
      else statut.textContent = `${r.joueur === 'X' ? 'X' : nomO} gagne ! 🎉`;
      tableau.innerHTML = `
        <div class="score"><small>X</small><b>${scores.X}</b></div>
        <div class="score"><small>Nuls</small><b>${scores.nul}</b></div>
        <div class="score"><small>${nomO}</small><b>${scores.O}</b></div>`;
    }

    function nouvellePartie() {
      clearTimeout(minuteur);
      grille = Array(9).fill(null);
      tour = 'X';
      fini = false;
      cases.forEach(c => c.classList.remove('gagne'));
      afficher(null);
    }

    majModes();
    nouvellePartie();
    return () => clearTimeout(minuteur);
  },
});
