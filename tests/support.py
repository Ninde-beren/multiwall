# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Outillage commun aux tests d'intégration.

Les tests ne doivent JAMAIS changer le vrai fond d'écran : on place en tête du
PATH un faux `gsettings` qui journalise ses arguments au lieu d'agir.
"""

import os
import stat
import tempfile
import unittest
from pathlib import Path

from multiwall import core

FAUX_GSETTINGS = """#!/bin/sh
printf '%s\\n' "$*" >> "$GSETTINGS_LOG"
if [ "$1" = "list-keys" ]; then
    printf 'picture-uri\\npicture-uri-dark\\npicture-options\\nprimary-color\\ncolor-shading-type\\n'
fi
if [ "$1" = "list-schemas" ]; then
    printf 'org.gnome.desktop.background\\norg.gnome.desktop.interface\\n'
fi
if [ "$1" = "get" ]; then
    printf "'valeur-simulee'\\n"
fi
exit 0
"""

# Variante d'un système plus ancien : pas de clé `picture-uri-dark`.
FAUX_GSETTINGS_SANS_DARK = FAUX_GSETTINGS.replace("picture-uri-dark\\n", "")

# Variante en échec : simule un dconf inaccessible.
FAUX_GSETTINGS_ECHEC = """#!/bin/sh
printf '%s\\n' "$*" >> "$GSETTINGS_LOG"
if [ "$1" = "list-keys" ]; then
    printf 'picture-uri\\npicture-options\\n'
    exit 0
fi
echo "impossible de se connecter au bus de session" >&2
exit 1
"""


class BaseIntegration(unittest.TestCase):
    """Isole HOME, XDG_*, le PATH et les chemins de module de MultiWall."""

    gsettings_script = FAUX_GSETTINGS

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

        bindir = self.root / "bin"
        bindir.mkdir()
        stub = bindir / "gsettings"
        stub.write_text(self.gsettings_script)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        self.log = self.root / "gsettings.log"
        self._env = dict(os.environ)
        os.environ["PATH"] = f"{bindir}:{os.environ['PATH']}"
        os.environ["GSETTINGS_LOG"] = str(self.log)

        # Les constantes de chemin sont calculées à l'import : on les redirige.
        self._paths = (core.DATA_DIR, core.CONFIG_DIR, core.CONFIG_PATH)
        core.DATA_DIR = self.root / "data"
        core.CONFIG_DIR = self.root / "config"
        core.CONFIG_PATH = core.CONFIG_DIR / "config.json"

    def tearDown(self):
        core.DATA_DIR, core.CONFIG_DIR, core.CONFIG_PATH = self._paths
        os.environ.clear()
        os.environ.update(self._env)
        self.tmp.cleanup()

    # -- helpers ----------------------------------------------------------
    def appels_gsettings(self) -> list[str]:
        if not self.log.exists():
            return []
        return [l for l in self.log.read_text().splitlines() if l.strip()]

    def valeur_definie(self, cle: str) -> str | None:
        """Dernière valeur passée à `gsettings set <schema> <cle> …`."""
        prefixe = f"set {core.SCHEMA} {cle} "
        for appel in reversed(self.appels_gsettings()):
            if appel.startswith(prefixe):
                return appel[len(prefixe):]
        return None

    def image_test(self, nom: str, size=(1920, 1080), couleur=(255, 0, 0)) -> Path:
        from PIL import Image

        p = self.root / nom
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, couleur).save(p)
        return p
