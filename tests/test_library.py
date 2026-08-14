# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Tests de la bibliothèque de fonds générés."""

import time
import unittest

from multiwall import core, library
from support import BaseIntegration
from test_cli import TROIS_ECRANS, BaseCLI

DEUX_ECRANS = [
    core.Monitor("DP-1", 1920, 1080, 0, 0),
    core.Monitor("DP-2", 1920, 1080, 1920, 0),
]


class TestCatalogue(unittest.TestCase):
    def test_dix_fonds_aux_identifiants_uniques(self):
        self.assertEqual(len(library.CATALOGUE), 10)
        identifiants = [f.id for f in library.CATALOGUE]
        self.assertEqual(len(set(identifiants)), 10)

    def test_tous_les_styles_et_palettes_existent(self):
        for fond in library.CATALOGUE:
            with self.subTest(fond=fond.id):
                self.assertIn(fond.style, library.STYLES)
                self.assertIn(fond.palette, library.PALETTES)

    def test_les_quatre_styles_sont_representes(self):
        self.assertEqual({f.style for f in library.CATALOGUE}, set(library.STYLES))

    def test_identifiant_inconnu(self):
        with self.assertRaises(ValueError) as ctx:
            library.get("nexiste-pas")
        self.assertIn("nexiste-pas", str(ctx.exception))
        self.assertFalse(library.existe("nexiste-pas"))


class TestRendu(unittest.TestCase):
    def test_chaque_fond_rend_exactement_la_taille_demandee(self):
        for fond in library.CATALOGUE:
            with self.subTest(fond=fond.id):
                img = fond.rendu((640, 120))
                self.assertEqual(img.size, (640, 120))
                self.assertEqual(img.mode, "RGB")

    def test_le_rendu_est_reproductible(self):
        """Même recette, même image : la config ne stocke qu'un identifiant."""
        a = library.get("cristaux").rendu((320, 60))
        b = library.get("cristaux").rendu((320, 60))
        self.assertEqual(list(a.getdata()), list(b.getdata()))

    def test_deux_fonds_different_visuellement(self):
        a = library.get("crepuscule").rendu((160, 30))
        b = library.get("recif").rendu((160, 30))
        self.assertNotEqual(list(a.getdata()), list(b.getdata()))

    def test_l_image_n_est_pas_unie(self):
        for fond in library.CATALOGUE:
            with self.subTest(fond=fond.id):
                couleurs = set(fond.rendu((240, 45)).getdata())
                self.assertGreater(len(couleurs), 12, "un fond uni serait raté")

    def test_s_adapte_a_n_importe_quelle_resolution(self):
        for taille in ((3840, 1080), (5760, 1080), (1920, 1080), (2560, 2880)):
            with self.subTest(taille=taille):
                self.assertEqual(library.get("massif").rendu(taille).size, taille)

    def test_taille_degeneree_ne_plante_pas(self):
        self.assertEqual(library.get("dunes").rendu((0, 0)).size, (1, 1))

    def test_le_rendu_pleine_taille_reste_rapide(self):
        depart = time.monotonic()
        library.get("montagnes" if library.existe("montagnes") else "massif").rendu(
            (5760, 1080)
        )
        self.assertLess(time.monotonic() - depart, 3.0)


class TestAncres(unittest.TestCase):
    """Les éléments focaux ne doivent pas tomber sur une bordure entre écrans."""

    def test_les_ancres_sont_les_centres_d_ecran(self):
        self.assertEqual(library.ancres_ecrans(TROIS_ECRANS), [960.0, 2880.0, 4800.0])

    def test_les_ancres_suivent_l_echelle_de_la_vignette(self):
        ancres = library.ancres_ecrans(TROIS_ECRANS, 576)  # 1/10e
        self.assertEqual([round(a) for a in ancres], [96, 288, 480])

    def test_deux_ecrans(self):
        self.assertEqual(library.ancres_ecrans(DEUX_ECRANS), [960.0, 2880.0])

    def test_sans_ecran(self):
        self.assertEqual(library.ancres_ecrans([]), [])

    def test_l_astre_est_pose_sur_un_centre_d_ecran(self):
        """Sur un style à astre, la colonne la plus claire doit être proche d'un
        centre d'écran, jamais d'une bordure."""
        largeur, hauteur = 1152, 216  # 5760x1080 au 1/5e
        img = library.rendu("nuit-claire", (largeur, hauteur), TROIS_ECRANS)
        bande = img.crop((0, 0, largeur, hauteur // 3))
        luminosite = [
            sum(sum(bande.getpixel((x, y))) for y in range(0, bande.height, 4))
            for x in range(largeur)
        ]
        pic = luminosite.index(max(luminosite))
        centres = library.ancres_ecrans(TROIS_ECRANS, largeur)
        bordures = [1920 * largeur / 5760, 3840 * largeur / 5760]
        self.assertLess(min(abs(pic - c) for c in centres),
                        min(abs(pic - b) for b in bordures),
                        "l'astre doit être plus près d'un centre que d'une bordure")


class TestConfigAvecFondGenere(BaseIntegration):
    def test_compose_depuis_un_identifiant(self):
        cfg = core.Config(mode="span")
        cfg.span = {"path": "", "fit": "cover", "library": "vallees"}
        self.assertTrue(cfg.has_image())
        self.assertEqual(cfg.compose(TROIS_ECRANS).size, (5760, 1080))

    def test_le_fond_suit_un_changement_d_ecrans(self):
        """Un fichier serait redimensionné ; une recette se recalcule."""
        cfg = core.Config(mode="span")
        cfg.span = {"path": "", "fit": "cover", "library": "vallees"}
        self.assertEqual(cfg.compose(DEUX_ECRANS).size, (3840, 1080))

    def test_aller_retour_dans_la_config(self):
        cfg = core.Config(mode="span")
        cfg.span = {"path": "", "fit": "cover", "library": "braise"}
        cfg.save()
        self.assertEqual(core.Config.load().span["library"], "braise")

    def test_un_identifiant_disparu_est_ignore_au_chargement(self):
        """Une entrée retirée du catalogue ne doit pas bloquer le démarrage."""
        core.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        core.CONFIG_PATH.write_text('{"mode": "span", "span": {"library": "fond-supprime"}}')
        cfg = core.Config.load()
        self.assertEqual(cfg.span["library"], "")
        self.assertFalse(cfg.has_image())


class TestHistorique(BaseIntegration):
    """« Mes fonds » : les images déjà apportées, retrouvables plus tard."""

    def test_une_image_notee_apparait_en_tete(self):
        cfg = core.Config()
        a = self.image_test("a.png")
        b = self.image_test("b.png")
        cfg.noter_image(a)
        cfg.noter_image(b)
        self.assertEqual(cfg.images_connues(), [str(b), str(a)], "la plus récente d'abord")

    def test_une_image_reutilisee_remonte_sans_doublon(self):
        cfg = core.Config()
        a = self.image_test("a.png")
        b = self.image_test("b.png")
        cfg.noter_image(a)
        cfg.noter_image(b)
        cfg.noter_image(a)
        self.assertEqual(cfg.images_connues(), [str(a), str(b)])
        self.assertEqual(len(cfg.historique), 2, "pas de doublon")

    def test_un_fichier_disparu_n_est_plus_propose(self):
        cfg = core.Config()
        a = self.image_test("a.png")
        cfg.noter_image(a)
        cfg.noter_image("/chemin/effacé.png")
        self.assertEqual(cfg.images_connues(), [str(a)])
        self.assertEqual(len(cfg.historique), 2, "l'entrée reste, mais n'est pas proposée")

    def test_oublier_une_image(self):
        cfg = core.Config()
        a = self.image_test("a.png")
        cfg.noter_image(a)
        cfg.oublier_image(str(a))
        self.assertEqual(cfg.images_connues(), [])
        self.assertTrue(a.is_file(), "le fichier lui-même ne doit pas être touché")

    def test_l_historique_est_plafonne(self):
        cfg = core.Config()
        for i in range(core.HISTORIQUE_MAX + 15):
            cfg.noter_image(f"/tmp/img{i}.png")
        self.assertEqual(len(cfg.historique), core.HISTORIQUE_MAX)

    def test_l_historique_survit_a_un_redemarrage(self):
        cfg = core.Config()
        a = self.image_test("a.png")
        cfg.noter_image(a)
        cfg.save()
        self.assertEqual(core.Config.load().images_connues(), [str(a)])

    def test_un_historique_corrompu_est_ignore(self):
        core.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        core.CONFIG_PATH.write_text(
            '{"historique": ["pas-un-objet", {"path": 42}, {"autre": "x"}]}'
        )
        self.assertEqual(core.Config.load().historique, [])


class TestHistoriqueCLI(BaseCLI):
    def test_set_memorise_les_images(self):
        a = self.image_test("a.png")
        b = self.image_test("b.png")
        self.run_cli("set", str(a), str(b))
        self.assertCountEqual(core.Config.load().images_connues(), [str(a), str(b)])

    def test_span_memorise_l_image(self):
        pano = self.image_test("p.png", size=(5760, 1080))
        self.run_cli("span", str(pano))
        self.assertEqual(core.Config.load().images_connues(), [str(pano)])

    def test_un_fond_genere_n_entre_pas_dans_l_historique(self):
        """Il n'a pas de fichier : sa place est dans l'onglet « Fonds générés »."""
        self.run_cli("library", "dunes")
        self.assertEqual(core.Config.load().images_connues(), [])


class TestCommandeLibrary(BaseCLI):
    def test_la_liste_affiche_les_dix_fonds(self):
        code, out, _ = self.run_cli("library")
        self.assertEqual(code, 0)
        for fond in library.CATALOGUE:
            self.assertIn(fond.id, out)
        self.assertIn("5760x1080", out)

    def test_appliquer_un_fond(self):
        code, out, err = self.run_cli("library", "dunes")
        self.assertEqual(code, 0, err)
        self.assertIn("Dunes", out)
        self.assertEqual(self.valeur_definie("picture-options"), "spanned")
        composite = sorted(core.DATA_DIR.glob("wall-*.png"))[-1]
        from PIL import Image

        with Image.open(composite) as img:
            self.assertEqual(img.size, (5760, 1080))

    def test_la_recette_est_persistee_pas_le_fichier(self):
        self.run_cli("library", "recif")
        cfg = core.Config.load()
        self.assertEqual(cfg.mode, "span")
        self.assertEqual(cfg.span["library"], "recif")
        self.assertEqual(cfg.span["path"], "", "aucun fichier ne doit être référencé")

    def test_apply_rejoue_le_fond_genere(self):
        self.run_cli("library", "massif")
        code, _, err = self.run_cli("apply")
        self.assertEqual(code, 0, err)

    def test_identifiant_inconnu_refuse_proprement(self):
        code, _, err = self.run_cli("library", "pas-un-fond")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("pas-un-fond", err)


if __name__ == "__main__":
    unittest.main()
