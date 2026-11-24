# Guide en français

Le banc compare des **configurations** (un outil, un modèle, une consigne) sur des **tâches**. Pour chaque course, il
note le code avec des tests cachés que l'agent n'a jamais vus, relève le coût et la durée, fait relire le code à
l'aveugle par un autre modèle, et vérifie d'abord que ce relecteur est fiable.

## Les commandes

À lancer depuis le dossier du dépôt :

```bash
bin/aibench doctor
```

Elle dit quels outils sont installés. Aucun modèle n'est appelé.

```bash
bin/aibench campaign campaigns/fake.toml
```

Elle déroule toute la chaîne avec un faux agent : gratuit, une seconde.

```bash
bin/aibench campaign campaigns/demo.toml --dry-run
```

Elle montre ce que ferait la vraie campagne, sans rien lancer.

```bash
bin/aibench campaign campaigns/demo.toml
```

Elle lance la vraie campagne : Haiku, Sonnet, Codex et Antigravity, 3 courses chacun, plafond 10 $.

```bash
bin/aibench calibrate demo-invoice claude-opus --repeat 2
```

Elle teste un juge sur des défauts plantés.

```bash
bin/aibench report
```

Elle affiche le tableau, puis ouvre `dashboard/index.html`.

## Où sont les choses

- `configs/` : une configuration par fichier. Pour en ajouter une, copie un fichier et change `model`, `effort` ou la consigne.
- `tasks/` : les tâches publiques (la démo). Tes tâches privées vont **hors du dépôt**, déclarées dans
  `aibench.local.toml`.
- `runs/` : tous les résultats, jamais envoyés sur GitHub.
- `campaigns/` : les campagnes, une liste de tâches × configurations × répétitions, avec un plafond.

## Les clés

Une clé (DeepSeek, OpenRouter…) se met dans ton terminal, jamais dans un fichier du dépôt. La configuration ne contient
que son nom (`env_pass`). Claude Code, Codex et Antigravity utilisent les connexions déjà ouvertes sur ta machine.
