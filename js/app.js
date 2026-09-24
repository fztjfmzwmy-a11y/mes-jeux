// Noyau de l'application : enregistrement des jeux, menu et navigation.
const App = (() => {
  const jeux = [];
  let jeuCourant = null;

  const $menu = () => document.getElementById('menu');
  const $scene = () => document.getElementById('scene');
  const $titre = () => document.getElementById('titre');
  const $retour = () => document.getElementById('retour');

  // Chaque jeu fournit { id, nom, icone, desc, lancer(scene) -> fonction de nettoyage }
  function enregistrer(jeu) {
    jeux.push(jeu);
  }

  function afficherMenu() {
    arreterJeu();
    const menu = $menu();
    menu.innerHTML = '';
    for (const jeu of jeux) {
      const tuile = document.createElement('button');
      tuile.className = 'tuile';
      tuile.innerHTML = `
        <span class="icone">${jeu.icone}</span>
        <span class="nom">${jeu.nom}</span>
        <span class="desc">${jeu.desc}</span>`;
      tuile.addEventListener('click', () => { location.hash = jeu.id; });
      menu.appendChild(tuile);
    }
    menu.hidden = false;
    $scene().hidden = true;
    $retour().hidden = true;
    $titre().textContent = '🎮 Mes Jeux';
  }

  function ouvrirJeu(jeu) {
    arreterJeu();
    const scene = $scene();
    scene.innerHTML = '';
    $menu().hidden = true;
    scene.hidden = false;
    $retour().hidden = false;
    $titre().textContent = `${jeu.icone} ${jeu.nom}`;
    jeuCourant = jeu.lancer(scene) || null;
  }

  function arreterJeu() {
    if (typeof jeuCourant === 'function') jeuCourant();
    jeuCourant = null;
  }

  function router() {
    const id = location.hash.slice(1);
    const jeu = jeux.find(j => j.id === id);
    if (jeu) ouvrirJeu(jeu); else afficherMenu();
  }

  function demarrer() {
    $retour().addEventListener('click', () => { location.hash = ''; });
    window.addEventListener('hashchange', router);
    router();
  }

  // Petits utilitaires partagés entre les jeux
  const outils = {
    el(tag, props = {}, enfants = []) {
      const e = document.createElement(tag);
      Object.assign(e, props);
      for (const c of [].concat(enfants)) e.append(c);
      return e;
    },
    // Lit le record d'un jeu et l'améliore si « valeur » est meilleure.
    // Avec plusPetit = true, le meilleur record est le plus bas (ex. nombre de coups).
    record(cle, valeur, plusPetit = false) {
      const k = `mes-jeux:${cle}`;
      let actuel = null;
      try { const v = localStorage.getItem(k); if (v !== null) actuel = Number(v); } catch (_) {}
      const meilleur = actuel === null || (plusPetit ? valeur < actuel : valeur > actuel);
      if (valeur !== undefined && meilleur) {
        try { localStorage.setItem(k, String(valeur)); } catch (_) {}
        return valeur;
      }
      return actuel || 0;
    },
    melanger(tab) {
      for (let i = tab.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [tab[i], tab[j]] = [tab[j], tab[i]];
      }
      return tab;
    },
    // Détecte un glissement du doigt sur un élément et renvoie la direction.
    glissement(element, rappel) {
      let x0 = 0, y0 = 0;
      const debut = e => { const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; };
      const fin = e => {
        const t = e.changedTouches[0];
        const dx = t.clientX - x0, dy = t.clientY - y0;
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 25) return;
        if (Math.abs(dx) > Math.abs(dy)) rappel(dx > 0 ? 'droite' : 'gauche');
        else rappel(dy > 0 ? 'bas' : 'haut');
      };
      element.addEventListener('touchstart', debut, { passive: true });
      element.addEventListener('touchend', fin);
    },
    touches: {
      ArrowUp: 'haut', ArrowDown: 'bas', ArrowLeft: 'gauche', ArrowRight: 'droite',
      z: 'haut', s: 'bas', q: 'gauche', d: 'droite',
      w: 'haut', a: 'gauche',
    },
  };

  return { enregistrer, demarrer, outils };
})();
