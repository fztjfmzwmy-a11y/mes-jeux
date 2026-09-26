# Sécurité — AI Investor

## Garanties de la phase 1

| Garantie | Mise en œuvre | Test |
| --- | --- | --- |
| Aucune exécution d'ordre, transfert, retrait, modification de compte | Ces actions ne sont pas des permissions (`security/permissions.py`) ; aucune fonction correspondante n'existe | `tests/security/test_permissions.py`, `test_no_execution_capability.py` (analyse statique de tout le code) |
| Aucune connexion réseau / courtier dans le code | Imports réseau et bibliothèques de courtage interdits | `test_no_execution_capability.py`, `test_dependencies.py` |
| Fournisseurs de données en lecture seule | Interfaces limitées à des méthodes `get_*` ; un fournisseur exigeant des identifiants personnels est refusé | `test_no_execution_capability.py` |
| Aucun identifiant accepté | `security/secrets_guard.py` refuse tout import contenant mot de passe, PIN, 2FA, cookie, token, IBAN… sans recopier la valeur | `test_secrets_guard.py` |
| Simulation imposée | `SIMULATION_ONLY` n'accepte que `true` | `tests/unit/test_config.py` |
| Moindre privilège | Permissions des agents fixées dans le code, non modifiables à l'exécution | `test_permissions.py` |
| Journal non modifiable | Triggers SQLite refusant UPDATE/DELETE, chaînage SHA-256, dépôt sans méthode de modification | `tests/unit/test_journal.py` |
| Aucun vote ne contourne un blocage | Invariants du modèle `FinalDecision` (Risk BLOCK ⇒ BLOCKED, Devil's Advocate REVIEW ⇒ pas de validation) | `tests/unit/test_models.py` |
| Actualités non fiables par construction | `NewsItem.untrusted` vaut toujours `True` | `tests/unit/test_models.py` |
| Simulation seulement | Transactions marquées `simulated=True` (non modifiable), aucun appel externe, retrait = capital virtuel | `tests/unit/test_simulator.py`, `test_ledger.py` |
| Import sûr | Taille et nombre de lignes limités, tout ou rien, champs inconnus refusés, identifiants refusés, contenu conservé comme donnée | `tests/unit/test_importers.py` |
| Application locale | Écoute sur `127.0.0.1`, en-têtes de sécurité (CSP, X-Frame-Options…) | `tests/unit/test_app.py` |

## Contenu externe

Les actualités, fichiers et données externes sont des **données**, jamais des
instructions. Les défenses contre l'injection de prompt seront ajoutées avec le
News Agent (étape 8) et testées.

## Liste d'exclusions

Bibliothèques utilisant l'API privée de Trade Republic (ex. `pytr`), automatisation de
navigateur, clients d'API de courtage : interdits.
