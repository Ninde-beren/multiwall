#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
# Lance la suite de tests (unittest, stdlib — aucune dépendance à installer).
# Les tests n'écrivent jamais dans le vrai environnement : gsettings est simulé
# et HOME/XDG sont redirigés vers un dossier temporaire.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 -m unittest discover -s tests "$@"
