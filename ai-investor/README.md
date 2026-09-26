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
| 2 | Modèle de données | à venir |

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

Voir [docs/SECURITY.md](docs/SECURITY.md) pour le modèle de sécurité.
