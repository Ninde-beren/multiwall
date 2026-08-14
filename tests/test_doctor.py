# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Tests du diagnostic d'environnement."""

import os
import unittest

from multiwall import core, doctor
from support import BaseIntegration
from test_cli import TROIS_ECRANS, BaseCLI


class BaseDoctor(BaseIntegration):
    """Neutralise la détection d'écrans et fige les variables d'environnement."""

    def setUp(self):
        super().setUp()
        self._detect = core.detect_monitors
        core.detect_monitors = lambda: list(TROIS_ECRANS)
        os.environ["XDG_CURRENT_DESKTOP"] = "GNOME"
        os.environ["XDG_SESSION_TYPE"] = "x11"

    def tearDown(self):
        core.detect_monitors = self._detect
        super().tearDown()

    def point(self, rapport, libelle):
        for p in rapport.points:
            if p.libelle == libelle:
                return p
        raise AssertionError(f"point absent du rapport : {libelle}")


class TestBureau(BaseDoctor):
    def test_bureau_supporte(self):
        for nom in ("GNOME", "Budgie:GNOME", "X-Cinnamon", "MATE", "ubuntu:GNOME"):
            with self.subTest(bureau=nom):
                os.environ["XDG_CURRENT_DESKTOP"] = nom
                self.assertEqual(self.point(doctor.analyser(), "Bureau").etat, doctor.OK)

    def test_bureau_incompatible_est_un_echec(self):
        """KDE et XFCE gèrent leur fond autrement : l'app n'aura aucune prise."""
        for nom in ("KDE", "XFCE", "LXQt", "sway"):
            with self.subTest(bureau=nom):
                os.environ["XDG_CURRENT_DESKTOP"] = nom
                rapport = doctor.analyser()
                self.assertEqual(self.point(rapport, "Bureau").etat, doctor.ECHEC)
                self.assertFalse(rapport.utilisable)

    def test_bureau_inconnu_est_un_avertissement(self):
        os.environ["XDG_CURRENT_DESKTOP"] = "MonBureauExotique"
        rapport = doctor.analyser()
        self.assertEqual(self.point(rapport, "Bureau").etat, doctor.ATTENTION)
        self.assertTrue(rapport.utilisable, "un doute n'est pas un échec")

    def test_bureau_absent(self):
        os.environ.pop("XDG_CURRENT_DESKTOP", None)
        os.environ.pop("DESKTOP_SESSION", None)
        self.assertEqual(self.point(doctor.analyser(), "Bureau").valeur, "inconnu")


class TestSession(BaseDoctor):
    def test_x11_est_le_cas_verifie(self):
        self.assertEqual(self.point(doctor.analyser(), "Session").etat, doctor.OK)

    def test_wayland_est_signale_comme_non_verifie(self):
        os.environ["XDG_SESSION_TYPE"] = "wayland"
        point = self.point(doctor.analyser(), "Session")
        self.assertEqual(point.etat, doctor.ATTENTION)
        self.assertIn("compositeur", point.detail)


class TestVersions(BaseDoctor):
    def test_les_versions_courantes_passent(self):
        rapport = doctor.analyser()
        for libelle in ("Python", "GTK 3", "Pillow"):
            self.assertEqual(self.point(rapport, libelle).etat, doctor.OK)

    def test_pillow_ancien_est_un_avertissement(self):
        original = doctor._version_pillow
        doctor._version_pillow = lambda: ("5.4.1", (5, 4))
        try:
            point = self.point(doctor.analyser(), "Pillow")
            self.assertEqual(point.etat, doctor.ATTENTION)
            self.assertIn("EXIF", point.detail)
        finally:
            doctor._version_pillow = original

    def test_gtk_trop_ancien_est_un_echec(self):
        original = doctor._version_gtk
        doctor._version_gtk = lambda: ("3.18", (3, 18))
        try:
            rapport = doctor.analyser()
            self.assertEqual(self.point(rapport, "GTK 3").etat, doctor.ECHEC)
            self.assertFalse(rapport.utilisable)
        finally:
            doctor._version_gtk = original

    def test_gtk_absent_est_un_echec(self):
        original = doctor._version_gtk
        doctor._version_gtk = lambda: ("absent (ImportError)", ())
        try:
            self.assertEqual(self.point(doctor.analyser(), "GTK 3").etat, doctor.ECHEC)
        finally:
            doctor._version_gtk = original


class TestOutils(BaseDoctor):
    def test_schema_absent_est_un_echec(self):
        original = doctor._schema_present
        doctor._schema_present = lambda _s: False
        try:
            rapport = doctor.analyser()
            point = self.point(rapport, "Schéma du bureau")
            self.assertEqual(point.etat, doctor.ECHEC)
            self.assertIn("gsettings-desktop-schemas", point.detail)
            self.assertFalse(rapport.utilisable)
        finally:
            doctor._schema_present = original

    def test_xrandr_absent_est_tolere(self):
        original = doctor.shutil.which
        doctor.shutil.which = lambda nom: None if nom == "xrandr" else f"/usr/bin/{nom}"
        try:
            rapport = doctor.analyser()
            self.assertEqual(self.point(rapport, "xrandr").etat, doctor.ATTENTION)
            self.assertTrue(rapport.utilisable, "GDK prend le relais")
        finally:
            doctor.shutil.which = original


class TestEcrans(BaseDoctor):
    def test_les_ecrans_sont_listes(self):
        rapport = doctor.analyser()
        self.assertIn("5760×1080", self.point(rapport, "Détectés").valeur)
        self.point(rapport, "  DP-centre")

    def test_aucun_ecran_est_un_echec(self):
        core.detect_monitors = lambda: []
        rapport = doctor.analyser()
        self.assertFalse(rapport.utilisable)


class TestFormatage(BaseDoctor):
    def test_verdict_favorable(self):
        texte = doctor.formater(doctor.analyser())
        self.assertIn("pleinement supporté", texte)

    def test_verdict_avec_reserves(self):
        os.environ["XDG_SESSION_TYPE"] = "wayland"
        texte = doctor.formater(doctor.analyser())
        self.assertIn("avec des réserves", texte)
        self.assertIn("--mire", texte)

    def test_verdict_defavorable(self):
        os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
        texte = doctor.formater(doctor.analyser())
        self.assertIn("NON supporté", texte)


class TestMire(BaseDoctor):
    def test_une_couleur_par_ecran(self):
        image = doctor.mire(TROIS_ECRANS)
        self.assertEqual(image.size, (5760, 1080))
        couleurs = [image.getpixel((mon.x + mon.width // 2, mon.height // 2))
                    for mon in TROIS_ECRANS]
        self.assertEqual(len(set(couleurs)), 3, "chaque écran doit être distinct")

    def test_un_cadre_blanc_borde_chaque_ecran(self):
        image = doctor.mire(TROIS_ECRANS)
        for mon in TROIS_ECRANS:
            marge = max(min(mon.width, mon.height) // 40, 4)
            self.assertEqual(image.getpixel((mon.x + marge + 2, mon.y + mon.height // 2)),
                             (255, 255, 255))

    def test_plus_d_ecrans_que_de_couleurs(self):
        beaucoup = [core.Monitor(f"DP-{i}", 800, 600, i * 800, 0) for i in range(8)]
        self.assertEqual(doctor.mire(beaucoup).size, (6400, 600))


class TestCommandeDoctor(BaseCLI):
    def test_code_de_retour_favorable(self):
        os.environ["XDG_CURRENT_DESKTOP"] = "GNOME"
        os.environ["XDG_SESSION_TYPE"] = "x11"
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 0)
        self.assertIn("diagnostic", out)

    def test_code_de_retour_defavorable(self):
        """Utilisable dans un script d'installation."""
        os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("NON supporté", out)

    def test_le_diagnostic_ne_modifie_pas_le_fond(self):
        self.run_cli("doctor")
        self.assertIsNone(self.valeur_definie("picture-uri"),
                          "sans --mire, rien ne doit être appliqué")

    def test_sans_ecran_le_diagnostic_repond_quand_meme(self):
        """C'est précisément le symptôme qu'on vient diagnostiquer."""
        core.detect_monitors = lambda: []
        code, out, err = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("diagnostic", out)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
