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
| 4 | Portfolio Agent | ✅ |
| 5 | Market Agent | ✅ |
| 6 | Quant Agent | ✅ |
| 7 | Macro Agent | ✅ |
| 8 | News Agent | ✅ |
| 9 | Risk Manager | à venir |

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

## Agents

- `agents/base.py` : `AgentContext` n'expose que les sources permises par le rôle ;
  `run_agent()` transforme toute panne d'agent en rapport `UNAVAILABLE` (jamais une opinion),
  mais laisse remonter toute violation de sécurité.
- `agents/portfolio_agent.py` + `portfolio/analytics.py` : valorisation, poids, performance
  latente, expositions (secteur, zone, devise, type), concentration (HHI), doublons d'ETF,
  corrélations, volatilité et drawdown reconstitués, variations anormales, actifs hors règles.
  Prix manquant ⇒ valeur totale INCONNUE et `DONNÉES INSUFFISANTES` ; le PRU n'est jamais
  utilisé comme prix de marché.
- `agents/market_agent.py` : dernier prix, performances 1M/3M/6M/1A, MM50/MM200, tendance,
  momentum, volatilité et drawdown 1 an, comparaison à un indice et à une référence
  sectorielle, valorisation si disponible. FACTS / INTERPRETATIONS / HYPOTHESES séparés ;
  règles de lecture affichées ; « JE NE SAIS PAS » si moins de 200 cours.
- `data/validation.py` : prix aberrants (pic, saut, dernier cours non confirmé, prix éloigné
  du dernier cours), trous, doublons, dates futures, devises mélangées. Rien n'est corrigé en
  silence : tout est signalé et abaisse la qualité des données.
- `quant/indicators.py` : rendements, moyenne mobile, volatilité, drawdown, performance
  sur période (sans extrapolation).
- `agents/quant_agent.py` + `quant/` : rendement, CAGR, volatilité, drawdown, Sharpe, bêta,
  corrélations, moyennes mobiles, variations, Monte Carlo (bootstrap, graine fixe →
  reproductible, fourchette P5–P95) et backtests Buy & Hold vs filtre MM (sans biais
  d'anticipation, frais inclus). « PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE » partout.
- `agents/macro_agent.py` + `macro/analysis.py` : inflation, taux directeur, taux 10 ans,
  croissance, chômage → signaux (règles affichées) et TOUJOURS trois scénarios (central,
  favorable, défavorable), sans probabilité. Ne vote jamais BUY. Données via CSV
  (`data/samples/macro_example.csv`, valeurs fictives) ; API officielles (BCE, Eurostat)
  branchables plus tard sur la même interface.
- `agents/news_agent.py` + `news/analysis.py` : source, date, sujet, résumé (extrait),
  catégorie, impact potentiel (heuristique affichée), fiabilité (source + recoupement).
  Seules les informations HIGH sont citées comme faits, toujours attribuées (« Selon… ») ;
  le reste est « NON VÉRIFIÉ ». Ne vote jamais BUY/SELL ; REVIEW_REQUIRED sur événement
  fiable et significatif. Import JSON (fiabilité USER_PROVIDED, jamais auto-déclarée).
- `security/sanitizer.py` : nettoyage du texte externe, détection d'injection de prompt,
  URL sûres, encadrement des données non fiables.
- `data/providers/csv_prices.py` : historiques de prix depuis un CSV (`symbol, day, close,
  currency`).

Voir [docs/SECURITY.md](docs/SECURITY.md) pour le modèle de sécurité.
