# AI Investor — Proposition d'architecture (Étape 0)

> Document de conception, **aucun code applicatif**.
> Statut : **en attente de validation** avant l'étape 1.
>
> AI Investor est un **outil d'aide à la décision en simulation**. Il ne prédit pas les marchés,
> n'exécute aucun ordre et ne constitue pas un conseil en investissement.

---

## 1. Analyse des exigences

### 1.1 Ce que le système doit faire

| Domaine | Exigences clés |
| --- | --- |
| Portefeuille | Import (CSV/JSON/saisie manuelle), valorisation, allocation, expositions (secteur, zone, devise), concentration, doublons ETF, drawdown, volatilité |
| Analyse | 7 agents spécialisés (Portfolio, Market, Macro, News, Quant, Risk, Devil's Advocate) + Strategist + Final Review, coordonnés par un Director |
| Décision | Actions `BUY / HOLD / REDUCE / SELL / WAIT`, toujours **simulées**, argumentées et datées |
| Sécurité | Risk Manager avec droit de veto (`BLOCKED`), priorité absolue sur le vote, aucune capacité d'exécution |
| Traçabilité | Journal **append-only**, non modifiable rétroactivement, résultat ultérieur ajouté séparément |
| Simulation | Portefeuille virtuel, frais, paper trading sur plusieurs mois, comparaison IA vs Buy & Hold vs indice |
| Qualité | Indicateurs `DATA QUALITY` et `DECISION QUALITY` (HIGH/MEDIUM/LOW), pas de « % de confiance » |
| Honnêteté | Réponses explicites : `JE NE SAIS PAS`, `DONNÉES INSUFFISANTES`, `ANALYSES CONTRADICTOIRES`, `RISQUE TROP ÉLEVÉ`, `REVIEW REQUIRED` |

### 1.2 Ce que le système ne doit **jamais** faire

- Envoyer un ordre réel, transférer ou retirer de l'argent, modifier un compte.
- Demander, stocker ou manipuler : mot de passe, PIN, 2FA, cookies, token de session, identifiants bancaires.
- Utiliser une API privée / non documentée de Trade Republic ou contourner ses protections.
- Traiter le contenu d'une actualité, d'un fichier ou d'une donnée externe comme une instruction.
- Inventer une donnée manquante ou présenter une hypothèse comme un fait.
- Laisser un vote majoritaire contourner une règle de risque.

### 1.3 Principes de conception retenus

1. **Le cœur décisionnel est déterministe.** Calculs, règles de risque, vote et statut final sont du code
   Python testé, pas du texte généré par un LLM. Un LLM (optionnel) ne sert qu'à *rédiger* des explications
   et à *résumer* des actualités, dans un cadre strict (voir §5.3).
2. **Sécurité par absence de capacité.** Il n'existe aucune fonction, aucune route, aucune dépendance capable
   de passer un ordre. On ne « bloque » pas l'exécution : elle n'existe pas dans le code.
3. **Chaque donnée porte sa provenance** : source, date d'obtention, date de la donnée, fiabilité.
   Une valeur absente vaut `None` + raison, jamais 0 ni une estimation silencieuse.
4. **Tout est typé et validé** (Pydantic) aux frontières : imports, fournisseurs, sorties d'agents.
5. **Modularité par interfaces** : chaque fournisseur de données est remplaçable.

---

## 2. Architecture technique

### 2.1 Vue d'ensemble

```
                          ┌──────────────────────────────┐
  Navigateur (local) ───► │ FRONTEND  (Jinja2 + HTMX)    │
                          └──────────────┬───────────────┘
                                         │ HTTP (localhost)
                          ┌──────────────▼───────────────┐
                          │ BACKEND  FastAPI             │
                          │  auth locale · routes · API  │
                          └──────────────┬───────────────┘
                                         │
      ┌──────────────────────────────────▼──────────────────────────────────┐
      │ AGENT ORCHESTRATOR — Director                                       │
      │                                                                     │
      │  1. Portfolio ─┐                                                    │
      │  2. Market ────┤                                                    │
      │  3. Macro ─────┼─► collecte ─► contradictions ? ─► 2e passe         │
      │  4. News ──────┤                                                    │
      │  5. Quant ─────┘                                                    │
      │                     │                                               │
      │                     ▼                                               │
      │            Strategist (proposition)                                 │
      │                     ▼                                               │
      │            Risk Manager  ──► BLOCKED ? ───────────────┐             │
      │                     ▼                                 │             │
      │            Devil's Advocate ──► REVIEW_REQUIRED ? ────┤             │
      │                     ▼                                 ▼             │
      │            Final Review  ◄──── Vote & règles de priorité            │
      │                     ▼                                               │
      │            DÉCISION SIMULÉE ──► Journal (append-only)               │
      └──────────┬─────────────────┬──────────────────┬─────────────────────┘
                 │                 │                  │
      ┌──────────▼──────┐ ┌────────▼────────┐ ┌───────▼────────┐
      │ PORTFOLIO LAYER │ │ MARKET DATA     │ │ RISK ENGINE    │
      │ positions, cash │ │ LAYER           │ │ règles config. │
      │ simulateur      │ │ providers + cache│ │ déterministe  │
      └──────────┬──────┘ └────────┬────────┘ └───────┬────────┘
                 └─────────────────┼──────────────────┘
                          ┌────────▼─────────┐
                          │ DATABASE SQLite  │  + LOGGING (JSON structuré)
                          └──────────────────┘
```

> Note : le prompt décrit l'ordre « Risk Manager puis Strategist ». Je propose
> **Strategist → Risk Manager → Devil's Advocate → Final Review** : le Risk Manager a besoin d'une
> proposition concrète (montant, actif) pour vérifier les limites. Le Risk Manager effectue aussi un
> **pré-contrôle** avant le Strategist (état du portefeuille, liquidités, actifs interdits) afin que le
> Strategist connaisse d'emblée les contraintes. Les deux passages sont journalisés.

### 2.2 Composants

| Composant | Rôle | Choix |
| --- | --- | --- |
| **BACKEND** | API REST + pages web, orchestration des requêtes | FastAPI (Python 3.12) |
| **DATABASE** | Portefeuilles, transactions simulées, snapshots de prix, journal, règles | SQLite (fichier local) via SQLAlchemy 2 ; migrations Alembic. PostgreSQL possible plus tard sans changer le code métier |
| **AGENT ORCHESTRATOR** | Director, pipeline, vote, secondes passes, traçabilité | Code Python maison (pas de framework multi-agents lourd) : graphe d'étapes explicite, testable, sans magie |
| **MARKET DATA LAYER** | Abstraction des fournisseurs, cache, contrôle de fraîcheur et de cohérence | Interfaces `MarketDataProvider`, `NewsDataProvider`, `MacroDataProvider` ; implémentations CSV / JSON / mock en V1 |
| **PORTFOLIO LAYER** | Positions, liquidités, frais, valorisation, simulateur d'ordres **virtuels** | `PortfolioDataProvider`, `BrokerDataProvider` (**lecture seule**) |
| **RISK ENGINE** | Règles configurables, veto, explications | Fonctions pures, une règle = une classe, résultat `PASS / WARN / BLOCK` + motif |
| **QUANT** | Rendements, volatilité, MDD, Sharpe, corrélations, bêta, MM, Monte Carlo, backtests | numpy + pandas (+ scipy si besoin) |
| **FRONTEND** | Tableau de bord, page Décision, journal, configuration | Jinja2 + HTMX + Chart.js — pas de build JS, léger à maintenir |
| **LOGGING** | Logs techniques + audit | `structlog` (JSON) ; journal des décisions séparé des logs techniques |
| **AUTHENTICATION** | Accès à l'application **elle-même** (pas au courtier) | Utilisateur local unique, mot de passe haché Argon2, session cookie HttpOnly, écoute sur `127.0.0.1` par défaut |
| **TESTS** | Unitaires, propriétés, sécurité, bout-en-bout | pytest, hypothesis, httpx (TestClient), ruff, mypy, bandit, pip-audit |

---

## 3. Technologies proposées (priorité au gratuit / open source)

| Besoin | Proposé | Coût | Alternatives |
| --- | --- | --- | --- |
| Langage | Python 3.12 | Gratuit | — (écosystème data/finance le plus riche) |
| Web | FastAPI + Uvicorn | Gratuit | Flask, Django |
| Validation | Pydantic v2 | Gratuit | — |
| ORM / DB | SQLAlchemy 2 + SQLite + Alembic | Gratuit | PostgreSQL (Docker) si multi-appareils |
| Calcul | numpy, pandas | Gratuit | polars |
| UI | Jinja2 + HTMX + Chart.js | Gratuit | Streamlit (plus rapide à prototyper, moins contrôlable), React/Vite (plus lourd) |
| Planification paper trading | APScheduler | Gratuit | cron système |
| Tests / qualité | pytest, hypothesis, ruff, mypy, bandit, pip-audit | Gratuit | — |
| Gestion deps | uv (ou pip + requirements verrouillés) | Gratuit | Poetry |
| Conteneur (optionnel) | Docker Compose | Gratuit | exécution locale directe |
| LLM (optionnel) | **Désactivé par défaut.** Au choix : modèle local via Ollama (gratuit) ou API Claude (payant à l'usage, clé stockée dans `.env`) | 0 € → quelques €/mois | Aucun LLM : explications générées par gabarits |

**Sources de données envisagées pour plus tard** (V1 = fichiers et données simulées uniquement) :

| Type | Sources officielles / gratuites | Remarque |
| --- | --- | --- |
| Macro | BCE Data Portal (taux, inflation zone euro), Eurostat, FRED (Fed St. Louis, clé gratuite), OCDE, INSEE | APIs publiques officielles, très fiables |
| Change | BCE (taux de référence quotidiens) | Officiel, gratuit |
| Prix | Stooq (CSV), Alpha Vantage / Financial Modeling Prep / Twelve Data (paliers gratuits), fichiers CSV exportés manuellement | Vérifier les CGU de chaque source ; `yfinance` repose sur une API non officielle de Yahoo → **non retenu par défaut** |
| Actualités | Flux RSS officiels (BCE, Fed, AMF, ESMA, communiqués d'émetteurs), GDELT | Toujours traitées comme **données non fiables** (voir §5.3) |

---

## 4. Arborescence proposée

Le projet est placé dans `ai-investor/` pour rester indépendant de l'application de jeux du dépôt
(un dépôt séparé serait encore plus propre — à valider).

```
ai-investor/
├── README.md
├── pyproject.toml                 # deps, ruff, mypy, pytest
├── .env.example                   # AUCUN secret de courtier — seulement config app
├── config/
│   ├── risk_rules.default.yaml    # valeurs par défaut NON personnalisées
│   └── settings.default.yaml      # BASE_CURRENCY, horizon, fournisseurs actifs…
├── data/
│   ├── samples/                   # portefeuille, prix, macro, news fictifs
│   └── imports/                   # dépôts CSV/JSON de l'utilisateur (gitignoré)
├── docs/
│   ├── ARCHITECTURE.md            # ce document
│   ├── SECURITY.md                # modèle de menace, permissions
│   └── DATA_SOURCES.md            # sources autorisées, import Trade Republic
├── src/ai_investor/
│   ├── main.py                    # création de l'app FastAPI
│   ├── config.py                  # chargement + validation des règles
│   ├── core/
│   │   ├── models/                # Pydantic : Asset, Position, Price, NewsItem,
│   │   │                          #   AgentReport, Proposal, RiskVerdict, Decision…
│   │   ├── enums.py               # Action, Status, QualityLevel, Permission
│   │   ├── provenance.py          # DataPoint(value, source, as_of, fetched_at, reliability)
│   │   ├── money.py               # Decimal + devise, conversions explicites
│   │   └── errors.py              # InsufficientData, StaleData, PermissionDenied…
│   ├── security/
│   │   ├── permissions.py         # capacités autorisées, refus explicite du reste
│   │   ├── sanitizer.py           # neutralisation du contenu externe
│   │   └── secrets_guard.py       # détection/refus de champs sensibles à l'import
│   ├── data/
│   │   ├── interfaces.py          # PortfolioDataProvider, MarketDataProvider,
│   │   │                          #   NewsDataProvider, MacroDataProvider, BrokerDataProvider
│   │   ├── providers/
│   │   │   ├── mock.py
│   │   │   ├── csv_provider.py
│   │   │   ├── json_provider.py
│   │   │   └── manual.py
│   │   ├── importers/
│   │   │   └── trade_republic_export.py   # parse un export fourni par l'utilisateur
│   │   ├── validation.py          # prix aberrants, trous, incohérences, fraîcheur
│   │   └── cache.py
│   ├── portfolio/
│   │   ├── valuation.py
│   │   ├── exposure.py            # secteur, zone, devise, chevauchement ETF
│   │   └── simulator.py           # transactions VIRTUELLES uniquement
│   ├── quant/
│   │   ├── returns.py  risk_metrics.py  correlation.py
│   │   ├── indicators.py          # moyennes mobiles, momentum
│   │   ├── monte_carlo.py
│   │   └── backtest.py            # sans biais d'anticipation
│   ├── risk/
│   │   ├── rules.py               # une classe par règle
│   │   └── engine.py
│   ├── agents/
│   │   ├── base.py                # Agent, AgentContext (lecture seule), AgentReport
│   │   ├── director.py
│   │   ├── portfolio_agent.py  market_agent.py  macro_agent.py  news_agent.py
│   │   ├── quant_agent.py  risk_manager.py  strategist.py
│   │   ├── devils_advocate.py  final_review.py
│   │   └── llm/                   # optionnel, isolé, désactivable
│   │       ├── client.py          # sans outils, sortie JSON validée
│   │       └── prompts/
│   ├── orchestration/
│   │   ├── pipeline.py            # ordre d'exécution, secondes passes, timeouts
│   │   ├── voting.py              # agrégation + priorités
│   │   └── quality.py             # DATA QUALITY / DECISION QUALITY
│   ├── journal/
│   │   ├── repository.py          # INSERT uniquement
│   │   └── hashchain.py           # chaînage SHA-256 anti-modification
│   ├── paper_trading/
│   │   ├── engine.py  scheduler.py  report.py
│   ├── db/
│   │   ├── tables.py  session.py
│   │   └── migrations/
│   └── web/
│       ├── auth.py
│       ├── routes/                # dashboard, decision, journal, portfolio, settings
│       ├── templates/
│       └── static/
└── tests/
    ├── unit/                      # quant, risk, portfolio, validation
    ├── agents/                    # chaque agent + contradictions + indisponibilité
    ├── security/                  # exécution réelle, identifiants, injection de prompt
    ├── integration/               # pipeline complet sur données fictives
    └── fixtures/
```

---

## 5. Sécurité

### 5.1 Modèle de permissions

```python
# Esquisse — sera implémentée à l'étape 1
class Permission(StrEnum):
    READ_PORTFOLIO = "READ_PORTFOLIO"
    READ_MARKET    = "READ_MARKET"
    READ_NEWS      = "READ_NEWS"
    RUN_ANALYSIS   = "RUN_ANALYSIS"
    RUN_SIMULATION = "RUN_SIMULATION"

FORBIDDEN = {"PLACE_ORDER", "TRANSFER_MONEY", "WITHDRAW_MONEY", "CHANGE_ACCOUNT_SETTINGS"}
```

- Les permissions interdites **ne font pas partie de l'énumération** : impossible de les accorder par config.
  Toute demande les mentionnant lève `PermissionDenied` et est journalisée.
- Chaque agent déclare ses permissions ; le `AgentContext` qu'il reçoit n'expose **que** les lectures
  correspondantes (objets en lecture seule).
- `BrokerDataProvider` ne définit que des méthodes de lecture (`get_positions`, `get_transactions`,
  `get_cash`). Un test vérifie par introspection qu'aucune méthode de type `place_order`, `buy`, `sell`,
  `transfer`, `withdraw` n'existe dans le code.
- `simulator.py` n'écrit que dans les tables du portefeuille **virtuel**.
- Aucune dépendance de trading/courtier (ex. clients d'API de broker, `pytr`) n'est autorisée ; un test
  vérifie la liste des dépendances.

### 5.2 Identifiants

- Aucun champ de formulaire, modèle ou table ne contient mot de passe courtier, PIN, 2FA, cookie ou token.
- `secrets_guard.py` rejette un import contenant des colonnes/clés suspectes (`password`, `pin`, `token`,
  `cookie`, `session`, `iban`…) et ne les enregistre pas.
- Les seuls secrets possibles sont ceux de l'application (mot de passe local haché, éventuelle clé d'API
  de données ou de LLM) dans `.env`, jamais commités.

### 5.3 Injection de prompt et contenu externe

- Actualités, fichiers importés, champs de données = **données**, jamais instructions.
- Les agents déterministes n'interprètent pas le texte : aucune injection ne peut modifier une règle ou un calcul.
- Si le LLM est activé :
  - il n'a **aucun outil** et aucun accès à l'orchestrateur ;
  - le contenu externe est encadré par des délimiteurs et étiqueté « donnée non fiable » ;
  - sa sortie doit respecter un schéma JSON strict ; sinon elle est rejetée (→ `DONNÉES INSUFFISANTES`) ;
  - il ne peut ni produire ni modifier un statut de risque ni une décision finale ;
  - des motifs d'injection détectés (« ignore les instructions », « exécute un ordre »…) signalent la
    source comme suspecte et abaissent sa fiabilité.

### 5.4 Intégrité du journal

- Table append-only (aucune route `UPDATE`/`DELETE`, trigger SQLite qui les refuse).
- Chaque entrée contient le hash de la précédente (chaîne SHA-256) → toute altération est détectable.
- Le « résultat ultérieur » est une **entrée d'évaluation séparée** liée à la décision, pas une modification.

### 5.5 Logique de décision finale (déterministe)

```
si une règle de sécurité ou de risque = BLOCK         → FINAL = BLOCKED
sinon si Devil's Advocate = REVIEW_REQUIRED           → FINAL = REVIEW_REQUIRED
sinon si DATA QUALITY = LOW                           → FINAL = DONNÉES INSUFFISANTES
sinon si contradiction majeure non résolue            → FINAL = ANALYSES CONTRADICTOIRES
sinon                                                 → FINAL = action proposée (SIMULATION)
```
Le vote des agents informe la qualité de décision et l'explication ; il ne peut jamais lever un blocage.

---

## 6. Risques techniques et de sécurité identifiés

| # | Risque | Conséquence | Mesure |
| --- | --- | --- | --- |
| 1 | Hallucination d'un LLM | Données ou raisonnements inventés | Cœur déterministe ; LLM optionnel, sans outils, sortie validée, jamais source de chiffres |
| 2 | Injection de prompt via news/fichiers | Détournement de l'analyse | §5.3 + tests dédiés |
| 3 | Données périmées | Décision sur un marché qui a changé | Horodatage systématique, seuil de fraîcheur configurable, dégradation de la qualité |
| 4 | Prix aberrants / erreurs de fichiers | Calculs faussés | Validation (écarts extrêmes, prix ≤ 0, dates manquantes, doublons), mise en quarantaine |
| 5 | Opérations sur titres (splits, dividendes) | Performance et PRU faux | Prix ajustés explicites ou table d'événements ; signalement si absent |
| 6 | Multi-devises | Expositions erronées | `Money` avec devise, conversion explicite datée (taux BCE) |
| 7 | Arrondis flottants | Écarts comptables | `Decimal` pour les montants, float seulement pour les statistiques |
| 8 | Biais de backtest (anticipation, survivants, sur-optimisation) | Résultats trompeurs | Données « point-in-time », frais inclus, avertissement `PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE` |
| 9 | Fausse précision | Excès de confiance | Pas de %, niveaux HIGH/MEDIUM/LOW, incertitude affichée |
| 10 | Fournisseur indisponible / quota | Analyse incomplète | Timeouts, cache, statut `DONNÉES INSUFFISANTES` plutôt que valeur par défaut |
| 11 | Agent en erreur | Pipeline bloqué ou partiel | Isolation par agent, rapport `UNAVAILABLE`, qualité dégradée |
| 12 | CGU des sources de données | Usage non autorisé | Sources officielles ou avec CGU compatibles, documentées dans `DATA_SOURCES.md` |
| 13 | Exposition réseau de l'app | Accès aux données du portefeuille | Écoute localhost, auth locale, CSRF, en-têtes de sécurité |
| 14 | Chaîne d'approvisionnement | Dépendance malveillante | Dépendances minimales et verrouillées, `pip-audit`, `bandit` |
| 15 | Données personnelles (RGPD) | Fuite d'informations financières | Stockage local, `data/imports/` gitignoré, aucun envoi externe sauf LLM activé explicitement |
| 16 | Perception de conseil financier | Mauvaise utilisation | Mentions « simulation », « pas un conseil », valeurs par défaut non personnalisées |

---

## 7. Intégration des données Trade Republic — moyens autorisés uniquement

À ma connaissance, **Trade Republic ne propose pas d'API publique officielle** pour les particuliers.
Les bibliothèques communautaires existantes reposent sur l'API privée de l'application et nécessitent
numéro de téléphone + PIN + 2FA : elles sont **exclues** de ce projet.

Moyens envisageables, du plus simple au plus avancé :

1. **Saisie manuelle** des positions (ISIN, quantité, prix moyen, date) dans l'application. Toujours disponible.
2. **Export fourni par Trade Republic à l'utilisateur** : relevés de compte et de titres, avis d'opéré,
   rapports fiscaux (PDF), et export de l'historique de transactions s'il est proposé dans l'app/web.
   L'utilisateur télécharge le fichier lui-même, puis l'importe dans AI Investor. Le parseur ne lit que le
   fichier, ne se connecte à rien, et rejette tout champ sensible.
3. **Droit d'accès / portabilité RGPD (art. 15 et 20)** : l'utilisateur peut demander à Trade Republic une
   copie de ses données dans un format structuré, puis l'importer.
4. **Open banking DSP2 (plus tard, optionnel)** : le compte espèces Trade Republic étant un compte de
   paiement, un agrégateur agréé (prestataire AISP, avec consentement explicite et authentification sur le
   site de la banque) pourrait fournir les **transactions espèces**. Cela ne couvre en général **pas** le
   compte-titres. L'application ne verrait jamais les identifiants.
5. **API officielle future** : si Trade Republic publie une API officielle (OAuth, lecture seule), un
   nouveau `BrokerDataProvider` pourra être ajouté **en lecture seule**, sans toucher au reste.

Dans tous les cas : pas d'automatisation de l'app, pas de scraping de session, pas de stockage
d'identifiants, pas d'ordre.

---

## 8. Plan de livraison

| Étape | Livrable | Critère de validation |
| --- | --- | --- |
| 1 | Squelette, config, permissions, interfaces, CI locale (ruff/mypy/pytest) | App démarre, tests de sécurité de base verts |
| 2 | Modèles Pydantic + tables SQL + journal hash-chaîné | Tests de validation et d'immuabilité |
| 3 | Portefeuille simulé + import CSV/JSON/manuel | Import d'exemple, transactions virtuelles enregistrées |
| 4 | Portfolio Agent | Métriques correctes sur jeux de données de référence |
| 5 | Market Agent (FACTS / INTERPRETATIONS / HYPOTHESES) | Séparation vérifiée par schéma |
| 6 | Quant Agent | Résultats comparés à des valeurs calculées à la main |
| 7 | Macro Agent (3 scénarios) | Scénarios toujours présents |
| 8 | News Agent | Source/date/fiabilité obligatoires, tests d'injection |
| 9 | Risk Manager | Chaque règle testée en limite, BLOCK prioritaire |
| 10 | Devil's Advocate | 6 questions obligatoires couvertes |
| 11 | Strategist | Tous les champs obligatoires, aucune exécution |
| 12 | Final Review + vote + qualité | Tables de vérité des priorités |
| 13 | Dashboard + page Décision | Parcours complet sur données fictives |
| 14 | Paper trading + rapport IA / Buy & Hold / indice | Simulation multi-mois reproductible |
| 15 | Campagne de tests complète (§22) | Tous les cas obligatoires couverts |

Après chaque étape : tests → corrections → revue sécurité → explication → **attente de validation**.

---

## 9. Points à valider

1. **Emplacement** : sous-dossier `ai-investor/` de ce dépôt (proposé) ou dépôt dédié ?
2. **Stack** : Python + FastAPI + SQLite + HTMX conviennent-ils ?
3. **LLM** : aucun (explications par gabarits), local (Ollama) ou API Claude — et à partir de quelle étape ?
4. **Devise de base** : EUR ?
5. **Ordre du pipeline** : Strategist → Risk Manager → Devil's Advocate → Final Review (avec pré-contrôle
   risque), comme proposé au §2.1 ?
