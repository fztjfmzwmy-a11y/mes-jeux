# AI Investor

Système multi-agents d'aide à la décision d'investissement.

> **SIMULATION UNIQUEMENT — aucune transaction réelle.**
> Outil d'aide à la décision, pas un conseil en investissement.
> PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE.

L'application ne se connecte à aucun courtier, ne passe aucun ordre et ne demande
jamais d'identifiants (mot de passe, PIN, 2FA, cookies, tokens, IBAN).

## État d'avancement

| Étape | Contenu | État |
| --- | --- | --- |
| 0 | Architecture ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)) | ✅ validée |
| 1 | Squelette, configuration, permissions, interfaces, tests de sécurité | ✅ |
| 2 | Modèle de données, base SQLite, journal immuable chaîné | ✅ |
| 3 | Portefeuille simulé, import CSV/JSON/manuel | ✅ |
| 4 | Portfolio Agent | à venir |

## Installation et vérifications

```bash
cd ai-investor
make install     # crée .venv et installe les dépendances (uv)
make check       # ruff + mypy (strict) + pytest
make run         # http://127.0.0.1:8000
```

## Configuration

- `config/settings.default.yaml` : devise de base, horizon, hôte, etc.
- `config/risk_rules.default.yaml` : règles de risque (garde-fous techniques,
  **pas** des recommandations personnalisées).

Pour personnaliser, copier en `*.local.yaml` (non versionné). Toute valeur incohérente
ou dangereuse est refusée au démarrage ; `SIMULATION_ONLY` ne peut pas être désactivé.

## Modèle de données

- `core/models/` : actifs, positions, prix, actualités, macro, transactions simulées,
  rapports d'agents, propositions, verdicts de risque, décisions finales, journal.
  Modèles immuables ; champs inconnus, NaN, dates sans fuseau et incohérences refusés.
- `core/provenance.py` : chaque donnée porte source, date et fiabilité ; une valeur
  manquante exige une raison explicite.
- `db/` : schéma SQLite. `journal_entries` et `simulated_transactions` sont en ajout
  seul (triggers). Migrations : `create_all` tant que le schéma évolue ; Alembic sera
  ajouté quand il sera stabilisé (avant l'usage réel en paper trading).
- `journal/` : journal chaîné SHA-256. `verify()` détecte modification, suppression ou
  réordonnancement ; conserver le hash de `head()` à l'extérieur permet aussi de détecter
  la suppression des dernières entrées.

## Portefeuille simulé

- `portfolio/ledger.py` : comptabilité pure (achat, renforcement, réduction, vente,
  conservation, attente, apport, retrait virtuel, reprise de position). PRU frais inclus,
  plus-value réalisée, contrôles de liquidités et de quantités, historique non antidatable.
- `portfolio/simulator.py` : portefeuille virtuel persistant ; chaque opération est
  enregistrée (ajout seul) et `check_consistency()` recalcule l'état depuis l'historique.
  Les règles de risque ne sont pas appliquées ici : c'est le rôle du Risk Manager.
- `data/importers/positions.py` : import CSV/JSON (exemples dans `data/samples/`),
  tout ou rien, erreurs détaillées par ligne, refus de tout champ d'identifiant.
- V1 : une seule devise par portefeuille (pas de conversion inventée).

Voir [docs/SECURITY.md](docs/SECURITY.md) pour le modèle de sécurité.
