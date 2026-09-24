// Puissance 4 : 2 joueurs ou contre l'ordinateur.
App.enregistrer({
  id: 'puissance4',
  nom: 'Puissance 4',
  icone: '🔴',
  desc: 'Aligne 4 jetons',
  lancer(scene) {
    const { el, melanger } = App.outils;
    const COL = 7, LIG = 6;
    let grille, tour, fini, mode = 'ia';
    let minuteur = null;

    const modes = el('div', { className: 'barre' });
    const statut = el('div', { className: 'statut' });
    const plateau = el('div', { className: 'p4' });
    const cases = [];

    for (const [val, label] of [['2j', '2 joueurs'], ['ia', 'Contre l\'ordinateur']]) {
      const b = el('button', { className: 'btn', textContent: label });
      b.dataset.mode = val;
      b.onclick = () => { mode = val; majModes(); nouvellePartie(); };
      modes.append(b);
    }
    for (let l = 0; l < LIG; l++) {
      for (let c = 0; c < COL; c++) {
        const d = el('div', { className: 'case' });
        d.onclick = () => clic(c);
        cases.push(d);
        plateau.append(d);
      }
    }
    const rejouer = el('button', { className: 'btn principal', textContent: 'Nouvelle partie', onclick: nouvellePartie });
    scene.append(modes, statut, plateau, rejouer);

    function majModes() {
      for (const b of modes.children) b.classList.toggle('actif', b.dataset.mode === mode);
    }

    const idx = (l, c) => l * COL + c;

    function ligneLibre(g, c) {
      for (let l = LIG - 1; l >= 0; l--) if (!g[idx(l, c)]) return l;
      return -1;
    }

    // Renvoie la liste des cases gagnantes pour le joueur j, ou null.
    function victoire(g, j) {
      const dirs = [[0, 1], [1, 0], [1, 1], [1, -1]];
      for (let l = 0; l < LIG; l++) for (let c = 0; c < COL; c++) {
        for (const [dl, dc] of dirs) {
          const ligne = [];
          for (let k = 0; k < 4; k++) {
            const ll = l + dl * k, cc = c + dc * k;
            if (ll < 0 || ll >= LIG || cc < 0 || cc >= COL || g[idx(ll, cc)] !== j) break;
            ligne.push(idx(ll, cc));
          }
          if (ligne.length === 4) return ligne;
        }
      }
      return null;
    }

    // IA simple : gagner si possible, sinon bloquer, sinon éviter d'offrir la victoire, préférer le centre.
    function coupIA() {
      const libres = [...Array(COL).keys()].filter(c => ligneLibre(grille, c) >= 0);
      const tester = (c, j) => {
        const g = [...grille];
        g[idx(ligneLibre(g, c), c)] = j;
        return g;
      };
      for (const c of libres) if (victoire(tester(c, 2), 2)) return c;
      for (const c of libres) if (victoire(tester(c, 1), 1)) return c;
      const surs = libres.filter(c => {
        const g = tester(c, 2);
        const l = ligneLibre(g, c);
        if (l < 0) return true;
        g[idx(l, c)] = 1;
        return !victoire(g, 1);
      });
      // Mélange puis tri stable : préfère le centre, départage au hasard.
      const choix = melanger(surs.length ? surs : libres);
      choix.sort((a, b) => Math.abs(a - 3) - Math.abs(b - 3));
      return Math.random() < 0.3 ? choix[Math.min(1, choix.length - 1)] : choix[0];
    }

    function clic(c) {
      if (fini || (mode === 'ia' && tour === 2)) return;
      if (!poser(c)) return;
      if (!fini && mode === 'ia') minuteur = setTimeout(() => poser(coupIA()), 400);
    }

    function poser(c) {
      const l = ligneLibre(grille, c);
      if (l < 0) return false;
      grille[idx(l, c)] = tour;
      const ligne = victoire(grille, tour);
      if (ligne) {
        fini = true;
        ligne.forEach(i => cases[i].classList.add('gagne'));
        statut.textContent = `${nom(tour)} gagne ! 🎉`;
      } else if (grille.every(Boolean)) {
        fini = true;
        statut.textContent = 'Match nul 🤝';
      } else {
        tour = tour === 1 ? 2 : 1;
        statut.textContent = `Au tour de ${nom(tour)}`;
      }
      afficher();
      return true;
    }

    function nom(j) {
      if (j === 1) return mode === 'ia' ? 'Toi 🔴' : 'Rouge 🔴';
      return mode === 'ia' ? 'l\'ordinateur 🟡' : 'Jaune 🟡';
    }

    function afficher() {
      cases.forEach((d, i) => {
        d.classList.toggle('j1', grille[i] === 1);
        d.classList.toggle('j2', grille[i] === 2);
      });
    }

    function nouvellePartie() {
      clearTimeout(minuteur);
      grille = Array(COL * LIG).fill(0);
      tour = 1;
      fini = false;
      cases.forEach(d => d.classList.remove('gagne'));
      statut.textContent = `Au tour de ${nom(1)}`;
      afficher();
    }

    majModes();
    nouvellePartie();
    return () => clearTimeout(minuteur);
  },
});
