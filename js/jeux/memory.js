// Memory : retrouver toutes les paires en un minimum de coups.
App.enregistrer({
  id: 'memory',
  nom: 'Memory',
  icone: '🧠',
  desc: 'Trouve les paires',
  lancer(scene) {
    const { el, melanger, record } = App.outils;
    const EMOJIS = ['🐶', '🐱', '🦊', '🐼', '🐸', '🦁', '🐵', '🐙'];
    let cartes, ouvertes, coups, trouvees, bloque, minuteur = null;

    const statut = el('div', { className: 'statut' });
    const plateau = el('div', { className: 'memory' });
    const rejouer = el('button', { className: 'btn principal', textContent: 'Nouvelle partie', onclick: nouvellePartie });
    scene.append(statut, plateau, rejouer);

    function nouvellePartie() {
      clearTimeout(minuteur);
      cartes = melanger([...EMOJIS, ...EMOJIS]);
      ouvertes = [];
      coups = 0;
      trouvees = 0;
      bloque = false;
      plateau.innerHTML = '';
      cartes.forEach((emoji, i) => {
        const b = el('button', { className: 'carte' });
        b.innerHTML = `<span class="dos">❓</span><span class="face">${emoji}</span>`;
        b.onclick = () => retourner(i, b);
        plateau.append(b);
      });
      majStatut();
    }

    function majStatut(fin) {
      const meilleur = record('memory');
      const txtRecord = meilleur ? ` · Record : ${meilleur} coups` : '';
      statut.textContent = fin ? `Bravo ! Terminé en ${coups} coups 🎉${txtRecord}` : `Coups : ${coups}${txtRecord}`;
    }

    function retourner(i, b) {
      if (bloque || b.classList.contains('retournee')) return;
      b.classList.add('retournee');
      ouvertes.push({ i, b });
      if (ouvertes.length < 2) return;

      coups++;
      const [a, c] = ouvertes;
      if (cartes[a.i] === cartes[c.i]) {
        a.b.classList.add('trouvee');
        c.b.classList.add('trouvee');
        ouvertes = [];
        trouvees++;
        if (trouvees === EMOJIS.length) {
          record('memory', coups, true);
          return majStatut(true);
        }
      } else {
        bloque = true;
        minuteur = setTimeout(() => {
          a.b.classList.remove('retournee');
          c.b.classList.remove('retournee');
          ouvertes = [];
          bloque = false;
        }, 800);
      }
      majStatut();
    }

    nouvellePartie();
    return () => clearTimeout(minuteur);
  },
});
