# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Tests d'intégration de l'application du fond d'écran (gsettings simulé)."""

import unittest

from PIL import Image

from multiwall import core
from support import FAUX_GSETTINGS_SANS_DARK, BaseIntegration


class TestApplyWallpaper(BaseIntegration):
    def test_ecrit_le_composite_a_la_bonne_taille(self):
        chemin = core.apply_wallpaper(Image.new("RGB", (5760, 1080), (1, 2, 3)))
        self.assertTrue(chemin.is_file())
        with Image.open(chemin) as img:
            self.assertEqual(img.size, (5760, 1080))
        self.assertEqual(chemin.suffix, ".png")

    def test_active_le_mode_spanned(self):
        """Le cœur du fonctionnement : sans `spanned`, l'image serait zoomée par écran."""
        core.apply_wallpaper(Image.new("RGB", (5760, 1080)))
        self.assertEqual(self.valeur_definie("picture-options"), "spanned")

    def test_pointe_picture_uri_sur_le_fichier_genere(self):
        chemin = core.apply_wallpaper(Image.new("RGB", (100, 100)))
        self.assertEqual(self.valeur_definie("picture-uri"), chemin.as_uri())

    def test_definit_aussi_la_variante_sombre(self):
        chemin = core.apply_wallpaper(Image.new("RGB", (100, 100)))
        self.assertEqual(self.valeur_definie("picture-uri-dark"), chemin.as_uri())

    def test_couleur_de_fond_transmise(self):
        core.apply_wallpaper(Image.new("RGB", (100, 100)), background="#112233")
        self.assertEqual(self.valeur_definie("primary-color"), "#112233")

    def test_deux_applications_produisent_des_uri_differentes(self):
        """GNOME/Budgie ignore une picture-uri identique à l'actuelle : le nom doit changer."""
        a = core.apply_wallpaper(Image.new("RGB", (50, 50)))
        b = core.apply_wallpaper(Image.new("RGB", (50, 50)))
        self.assertNotEqual(a, b)

    def test_purge_les_anciens_composites_sans_toucher_au_courant(self):
        chemins = [core.apply_wallpaper(Image.new("RGB", (40, 40))) for _ in range(5)]
        restants = sorted(core.DATA_DIR.glob("wall-*.png"))
        self.assertLessEqual(len(restants), 2)
        self.assertTrue(chemins[-1].is_file(), "le composite courant ne doit pas être supprimé")

    def test_ordre_des_appels_uri_apres_options(self):
        """picture-options doit être posé avant picture-uri, sinon le premier rendu
        utilise l'ancien mode d'ajustement."""
        core.apply_wallpaper(Image.new("RGB", (50, 50)))
        appels = self.appels_gsettings()
        i_opt = next(i for i, a in enumerate(appels) if "picture-options" in a)
        i_uri = next(i for i, a in enumerate(appels) if f"{core.SCHEMA} picture-uri " in a)
        self.assertLess(i_opt, i_uri)


class TestApplySansCleSombre(BaseIntegration):
    """Sur un GNOME antérieur à 42, `picture-uri-dark` n'existe pas."""

    gsettings_script = FAUX_GSETTINGS_SANS_DARK

    def test_ne_tente_pas_de_definir_une_cle_absente(self):
        core.apply_wallpaper(Image.new("RGB", (100, 100)))
        self.assertIsNone(self.valeur_definie("picture-uri-dark"))
        self.assertIsNotNone(self.valeur_definie("picture-uri"))


class TestConfigApply(BaseIntegration):
    def test_applique_la_config_par_moniteur(self):
        monitors = [
            core.Monitor("DP-1", 1920, 1080, 0, 0),
            core.Monitor("DP-2", 1920, 1080, 1920, 0),
        ]
        cfg = core.Config()
        cfg.monitors = {
            "DP-1": {"path": str(self.image_test("a.png", couleur=(255, 0, 0))), "fit": "cover"},
            "DP-2": {"path": str(self.image_test("b.png", couleur=(0, 0, 255))), "fit": "cover"},
        }
        chemin = cfg.apply(monitors)
        with Image.open(chemin) as img:
            self.assertEqual(img.size, (3840, 1080))
            self.assertEqual(img.getpixel((960, 540)), (255, 0, 0))
            self.assertEqual(img.getpixel((2880, 540)), (0, 0, 255))

    def test_chemin_avec_accents_et_espaces(self):
        monitors = [core.Monitor("DP-1", 800, 600, 0, 0)]
        cfg = core.Config()
        cfg.monitors = {
            "DP-1": {"path": str(self.image_test("mon été/fond d'écran.png")), "fit": "cover"}
        }
        chemin = cfg.apply(monitors)
        self.assertTrue(chemin.is_file())
        self.assertEqual(self.valeur_definie("picture-uri"), chemin.as_uri())


if __name__ == "__main__":
    unittest.main()
