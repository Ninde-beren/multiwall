# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Tests de bout en bout des sous-commandes (gsettings et écrans simulés)."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from PIL import Image

from multiwall import cli, core
from support import BaseIntegration

TROIS_ECRANS = [
    core.Monitor("DP-gauche", 1920, 1080, 0, 0),
    core.Monitor("DP-centre", 1920, 1080, 1920, 0, primary=True),
    core.Monitor("DP-droite", 1920, 1080, 3840, 0),
]


class BaseCLI(BaseIntegration):
    """Neutralise xrandr : les tests ne dépendent pas du matériel de la machine."""

    ecrans = TROIS_ECRANS

    def setUp(self):
        super().setUp()
        self._detect = core.detect_monitors
        core.detect_monitors = lambda: list(self.ecrans)

    def tearDown(self):
        core.detect_monitors = self._detect
        super().tearDown()

    def run_cli(self, *argv):
        """Exécute la commande et renvoie (code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def composite_courant(self):
        return sorted(core.DATA_DIR.glob("wall-*.png"))[-1]


class TestList(BaseCLI):
    def test_affiche_la_taille_du_bureau_et_les_ecrans(self):
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("5760x1080", out)
        for nom in ("DP-gauche", "DP-centre", "DP-droite"):
            self.assertIn(nom, out)

    def test_aucun_ecran_detecte(self):
        core.detect_monitors = lambda: []
        code, _, err = self.run_cli("list")
        self.assertEqual(code, 1)
        self.assertIn("Aucun écran", err)


class TestSet(BaseCLI):
    def test_chemins_nus_repartis_de_gauche_a_droite(self):
        a = self.image_test("a.png", couleur=(255, 0, 0))
        b = self.image_test("b.png", couleur=(0, 255, 0))
        c = self.image_test("c.png", couleur=(0, 0, 255))
        code, _, _ = self.run_cli("set", str(a), str(b), str(c))
        self.assertEqual(code, 0)

        with Image.open(self.composite_courant()) as img:
            self.assertEqual(img.size, (5760, 1080))
            self.assertEqual(img.getpixel((960, 540)), (255, 0, 0))
            self.assertEqual(img.getpixel((2880, 540)), (0, 255, 0))
            self.assertEqual(img.getpixel((4800, 540)), (0, 0, 255))

    def test_ciblage_par_nom_d_ecran(self):
        img = self.image_test("x.png", couleur=(9, 9, 9))
        code, _, _ = self.run_cli("set", f"DP-droite={img}")
        self.assertEqual(code, 0)
        cfg = core.Config.load()
        self.assertEqual(list(cfg.monitors), ["DP-droite"])

    def test_ecran_inconnu_refuse(self):
        img = self.image_test("x.png")
        code, _, err = self.run_cli("set", f"DP-fantome={img}")
        self.assertEqual(code, 1)
        self.assertIn("DP-fantome", err)

    def test_fichier_introuvable_refuse(self):
        code, _, err = self.run_cli("set", "/nexiste/pas.png")
        self.assertEqual(code, 1)
        self.assertIn("introuvable", err)

    def test_plus_d_images_que_d_ecrans_refuse(self):
        imgs = [str(self.image_test(f"{i}.png")) for i in range(4)]
        code, _, err = self.run_cli("set", *imgs)
        self.assertEqual(code, 1)
        self.assertIn("Trop d'images", err)

    def test_la_config_est_persistee(self):
        img = self.image_test("a.png")
        self.run_cli("set", f"DP-centre={img}", "--fit", "blur")
        cfg = core.Config.load()
        self.assertEqual(cfg.mode, "per-monitor")
        self.assertEqual(cfg.monitors["DP-centre"]["fit"], "blur")

    def test_mode_d_ajustement_invalide_rejete_par_argparse(self):
        with self.assertRaises(SystemExit):
            self.run_cli("set", "a.png", "--fit", "n-importe-quoi")


class TestSpan(BaseCLI):
    def test_image_panoramique_etalee_sur_le_bureau(self):
        pano = self.root / "pano.png"
        Image.new("RGB", (5760, 1080), (7, 8, 9)).save(pano)
        code, out, _ = self.run_cli("span", str(pano))
        self.assertEqual(code, 0)
        self.assertIn("5760x1080", out)
        self.assertEqual(self.valeur_definie("picture-options"), "spanned")
        with Image.open(self.composite_courant()) as img:
            self.assertEqual(img.size, (5760, 1080))
            for x in (10, 2880, 5750):
                self.assertEqual(img.getpixel((x, 540)), (7, 8, 9))

    def test_bascule_le_mode_dans_la_config(self):
        pano = self.image_test("p.png", size=(5760, 1080))
        self.run_cli("span", str(pano))
        self.assertEqual(core.Config.load().mode, "span")

    def test_couleur_de_fond_personnalisee(self):
        carree = self.image_test("carre.png", size=(500, 500))
        code, _, _ = self.run_cli("span", str(carree), "--fit", "contain",
                                  "--background", "#123456")
        self.assertEqual(code, 0)
        self.assertEqual(self.valeur_definie("primary-color"), "#123456")
        with Image.open(self.composite_courant()) as img:
            self.assertEqual(img.getpixel((10, 540)), (0x12, 0x34, 0x56))


class TestRandom(BaseCLI):
    def test_une_image_differente_par_ecran(self):
        dossier = self.root / "fonds"
        for i, couleur in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]):
            self.image_test(f"fonds/{i}.png", couleur=couleur)
        code, _, _ = self.run_cli("random", str(dossier))
        self.assertEqual(code, 0)
        cfg = core.Config.load()
        chemins = [c["path"] for c in cfg.monitors.values()]
        self.assertEqual(len(chemins), 3)
        self.assertEqual(len(set(chemins)), 3, "les 3 écrans doivent avoir des images distinctes")

    def test_moins_d_images_que_d_ecrans_ne_plante_pas(self):
        self.image_test("fonds/seule.png")
        code, _, _ = self.run_cli("random", str(self.root / "fonds"))
        self.assertEqual(code, 0)
        self.assertEqual(len(core.Config.load().monitors), 3)

    def test_dossier_vide_refuse(self):
        (self.root / "vide").mkdir()
        code, _, err = self.run_cli("random", str(self.root / "vide"))
        self.assertEqual(code, 1)
        self.assertIn("Aucune image", err)

    def test_option_span(self):
        self.image_test("fonds/p.png", size=(5760, 1080))
        code, _, _ = self.run_cli("random", str(self.root / "fonds"), "--span")
        self.assertEqual(code, 0)
        self.assertEqual(core.Config.load().mode, "span")


class TestApplyEtExport(BaseCLI):
    def test_apply_sans_config_echoue_proprement(self):
        code, _, err = self.run_cli("apply")
        self.assertEqual(code, 1)
        self.assertIn("Aucune image", err)

    def test_apply_rejoue_la_derniere_configuration(self):
        img = self.image_test("a.png", couleur=(3, 4, 5))
        self.run_cli("set", f"DP-gauche={img}")
        premier = self.composite_courant()
        code, _, _ = self.run_cli("apply")
        self.assertEqual(code, 0)
        self.assertNotEqual(self.composite_courant(), premier)
        with Image.open(self.composite_courant()) as composite:
            self.assertEqual(composite.getpixel((960, 540)), (3, 4, 5))

    def test_export_ecrit_le_composite_demande(self):
        img = self.image_test("a.png", couleur=(1, 2, 3))
        self.run_cli("set", f"DP-gauche={img}")
        dest = self.root / "export.png"
        code, out, _ = self.run_cli("export", str(dest))
        self.assertEqual(code, 0)
        self.assertIn("5760x1080", out)
        with Image.open(dest) as exporte:
            self.assertEqual(exporte.size, (5760, 1080))


class TestDispositionInhabituelle(BaseCLI):
    """Deux écrans empilés verticalement, de tailles différentes."""

    ecrans = [
        core.Monitor("HDMI-haut", 2560, 1440, 0, 0),
        core.Monitor("eDP-bas", 1920, 1080, 0, 1440, primary=True),
    ]

    def test_composite_englobe_les_deux_ecrans(self):
        a = self.image_test("a.png", couleur=(255, 0, 0))
        b = self.image_test("b.png", couleur=(0, 0, 255))
        code, _, _ = self.run_cli("set", str(a), str(b))
        self.assertEqual(code, 0)
        with Image.open(self.composite_courant()) as img:
            self.assertEqual(img.size, (2560, 2520))
            self.assertEqual(img.getpixel((1280, 720)), (255, 0, 0))    # écran du haut
            self.assertEqual(img.getpixel((960, 1980)), (0, 0, 255))    # écran du bas
            self.assertEqual(img.getpixel((2500, 1980)), (0, 0, 0))     # hors écran → fond


if __name__ == "__main__":
    unittest.main()
