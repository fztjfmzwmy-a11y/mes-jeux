# 🎮 Mes Jeux

Une petite application web de jeux, en HTML/CSS/JavaScript pur (aucune dépendance, aucune compilation).

## Jeux inclus

| Jeu | Description |
| --- | --- |
| ❌ Morpion | 2 joueurs, IA facile ou IA difficile (imbattable) |
| 🔴 Puissance 4 | 2 joueurs ou contre l'ordinateur |
| 🧠 Memory | Retrouve les 8 paires en un minimum de coups |
| 🐍 Snake | Mange les pommes, la vitesse augmente |
| 🔢 2048 | Fusionne les tuiles jusqu'à 2048 |
| ✊ Pierre Feuille Ciseaux | Contre l'ordinateur |

Les records (Snake, 2048, Memory) sont enregistrés dans le navigateur.

## Lancer l'application

Ouvre simplement `index.html` dans un navigateur, ou lance un petit serveur :

```bash
python3 -m http.server 8000
# puis ouvre http://localhost:8000
```

Commandes : flèches ou ZQSD au clavier, glissement du doigt sur mobile.

## Ajouter un jeu

Crée un fichier dans `js/jeux/`, ajoute-le dans `index.html`, et enregistre-le :

```js
App.enregistrer({
  id: 'mon-jeu',
  nom: 'Mon jeu',
  icone: '🎲',
  desc: 'Courte description',
  lancer(scene) {
    // construire le jeu dans l'élément « scene »
    return () => { /* nettoyage (minuteurs, écouteurs clavier…) */ };
  },
});
```
