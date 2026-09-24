// Pierre-Feuille-Ciseaux contre l'ordinateur.
App.enregistrer({
  id: 'pfc',
  nom: 'Pierre Feuille Ciseaux',
  icone: '✊',
  desc: 'Bats l\'ordinateur',
  lancer(scene) {
    const { el } = App.outils;
    const COUPS = { pierre: '✊', feuille: '✋', ciseaux: '✌️' };
    const BAT = { pierre: 'ciseaux', feuille: 'pierre', ciseaux: 'feuille' };
    const scores = { toi: 0, nul: 0, ordi: 0 };

    const tableau = el('div', { className: 'scores' });
    const arene = el('div', { className: 'pfc-arene' });
    const statut = el('div', { className: 'statut', textContent: 'Choisis ton coup !' });
    const choix = el('div', { className: 'pfc-choix' });
    for (const [nom, emoji] of Object.entries(COUPS)) {
      const b = el('button', { textContent: emoji, title: nom, onclick: () => jouer(nom) });
      b.setAttribute('aria-label', nom);
      choix.append(b);
    }
    const remise = el('button', { className: 'btn', textContent: 'Remettre à zéro', onclick: () => {
      scores.toi = scores.nul = scores.ordi = 0;
      arene.innerHTML = '';
      statut.textContent = 'Choisis ton coup !';
      afficherScores();
    } });
    scene.append(tableau, arene, statut, choix, remise);

    function jouer(toi) {
      const noms = Object.keys(COUPS);
      const ordi = noms[Math.floor(Math.random() * noms.length)];
      arene.innerHTML = `<span>${COUPS[toi]}</span><span class="vs">contre</span><span>${COUPS[ordi]}</span>`;
      if (toi === ordi) { scores.nul++; statut.textContent = 'Égalité 🤝'; }
      else if (BAT[toi] === ordi) { scores.toi++; statut.textContent = `Gagné ! ${toi} bat ${ordi} 🎉`; }
      else { scores.ordi++; statut.textContent = `Perdu… ${ordi} bat ${toi} 😢`; }
      afficherScores();
    }

    function afficherScores() {
      tableau.innerHTML = `
        <div class="score"><small>Toi</small><b>${scores.toi}</b></div>
        <div class="score"><small>Égalités</small><b>${scores.nul}</b></div>
        <div class="score"><small>Ordinateur</small><b>${scores.ordi}</b></div>`;
    }

    afficherScores();
  },
});
