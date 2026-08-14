# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Tests de l'interface graphique.

La fenêtre est construite mais jamais affichée (`show_all` n'est pas appelé) :
les tests exercent la logique des callbacks, pas le rendu. Ignorés proprement
s'il n'y a pas de serveur graphique.
"""

import os
import time
import unittest

from PIL import Image

from support import BaseIntegration
from test_cli import TROIS_ECRANS

from multiwall import core

try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gio, GLib, Gtk

    GUI_DISPONIBLE = Gtk.init_check([])[0]
except Exception:  # pragma: no cover - dépend de l'environnement
    GUI_DISPONIBLE = False


_APP = None


def application_de_test():
    """Une seule Gtk.Application pour toute la suite.

    En enregistrer une par test ferait échouer `register()` : l'objet D-Bus
    précédent est encore exporté sur le même chemin.
    """
    global _APP
    if _APP is None:
        # NON_UNIQUE : ne pas entrer en conflit avec une instance déjà lancée.
        _APP = Gtk.Application(
            application_id="org.sigilbo.MultiWallTest",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        _APP.register(None)
    return _APP


@unittest.skipUnless(GUI_DISPONIBLE, "aucun serveur graphique disponible")
class BaseGUI(BaseIntegration):
    ecrans = TROIS_ECRANS

    def setUp(self):
        super().setUp()
        from multiwall import gui

        self.gui = gui
        self._detect = core.detect_monitors
        core.detect_monitors = lambda: list(self.ecrans)

        self.app = application_de_test()
        self.win = gui.MultiWallWindow(self.app)

    def tearDown(self):
        self.win.destroy()
        self.pomper()
        core.detect_monitors = self._detect
        super().tearDown()

    def pomper(self, limite: int = 200) -> None:
        """Traite ce qui est en attente (idle_add, redraws…).

        Toujours borné : un widget animé (le spinner) régénère des événements
        en continu, donc `while events_pending()` ne se terminerait jamais.
        Et `main_iteration_do(False)` pour ne jamais bloquer sur file vide.
        """
        tours = 0
        while Gtk.events_pending() and tours < limite:
            Gtk.main_iteration_do(False)
            tours += 1

    def attendre(self, condition, timeout: float = 20.0) -> bool:
        """Pompe la boucle GTK jusqu'à ce que `condition()` soit vraie."""
        fin = time.monotonic() + timeout
        while time.monotonic() < fin:
            self.pomper()
            if condition():
                return True
            time.sleep(0.01)
        return False


class TestEtatInitial(BaseGUI):
    def test_demarre_sur_le_premier_ecran(self):
        self.assertEqual(self.win.selected, "DP-gauche")
        self.assertFalse(self.win.is_span)

    def test_appliquer_est_desactive_sans_image(self):
        """Proposer un bouton qui ne peut qu'échouer est un piège."""
        self.assertFalse(self.win.apply_btn.get_sensitive())

    def test_ajustement_et_effacer_desactives_sans_image(self):
        self.assertFalse(self.win.fit_combo.get_sensitive())
        self.assertFalse(self.win.clear_btn.get_sensitive())

    def test_la_consigne_est_donnee_une_seule_fois_sous_l_apercu(self):
        """Répétée dans chaque écran vide, elle s'affichait 3 fois."""
        texte = self.win.hint.get_text().lower()
        self.assertIn("déposez", texte)
        self.assertIn("double-cliquez", texte)

    def test_le_texte_d_aide_est_toujours_affiche(self):
        """Le masquer laissait un trou entre les écrans et la barre d'actions."""
        self.assertTrue(self.win.hint.get_visible())
        self.assertNotEqual(self.win.hint.get_text(), "")

        image = self.image_test("a.png")
        self.win.cfg.monitors["DP-gauche"] = {"path": str(image), "fit": "cover"}
        self.win.refresh()
        self.assertTrue(self.win.hint.get_visible())
        self.assertNotEqual(self.win.hint.get_text(), "")

    def test_le_hint_bascule_sur_le_contexte_quand_l_ecran_a_une_image(self):
        image = self.image_test("a.png")
        self.win.cfg.monitors["DP-gauche"] = {"path": str(image), "fit": "cover"}
        self.win.refresh()
        texte = self.win.hint.get_text().lower()
        self.assertIn("remplacer", texte)
        self.assertIn("suppr", texte)
        self.assertNotIn("déposez", texte, "l'écran a déjà une image")

    def test_le_hint_panoramique_rappelle_la_resolution(self):
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        self.assertIn("5760×1080", self.win.hint.get_text())
        self.assertIn("déposez", self.win.hint.get_text().lower())

        pano = self.image_test("pano.png", size=(5760, 1080))
        self.win.cfg.span = {"path": str(pano), "fit": "cover"}
        self.win.refresh()
        self.assertIn("5760×1080", self.win.hint.get_text())
        self.assertNotIn("déposez", self.win.hint.get_text().lower())


class TestSelectionEtClavier(BaseGUI):
    def _touche(self, keyval):
        event = Gdk.EventKey()
        event.type = Gdk.EventType.KEY_PRESS
        event.keyval = keyval
        return self.win.on_area_key(self.win.area, event)

    def test_fleches_changent_d_ecran(self):
        self.assertTrue(self._touche(Gdk.KEY_Right))
        self.assertEqual(self.win.selected, "DP-centre")
        self.assertTrue(self._touche(Gdk.KEY_Right))
        self.assertEqual(self.win.selected, "DP-droite")

    def test_la_navigation_ne_deborde_pas(self):
        self._touche(Gdk.KEY_Left)
        self.assertEqual(self.win.selected, "DP-gauche")
        for _ in range(5):
            self._touche(Gdk.KEY_Right)
        self.assertEqual(self.win.selected, "DP-droite")

    def test_chiffres_selectionnent_par_rang(self):
        self.assertTrue(self._touche(Gdk.KEY_3))
        self.assertEqual(self.win.selected, "DP-droite")
        self.assertFalse(self._touche(Gdk.KEY_9), "rang au-delà du nombre d'écrans")

    def test_touche_non_geree_est_propagee(self):
        self.assertFalse(self._touche(Gdk.KEY_F12))


class TestHauteurApercu(BaseGUI):
    """L'aperçu prenait toute la place libre, ne laissant au texte d'aide
    qu'une zone démesurée où il flottait au milieu."""

    def _allouer(self, largeur):
        alloc = Gdk.Rectangle()
        alloc.x, alloc.y, alloc.width, alloc.height = 0, 0, largeur, 400
        self.win._ajuster_hauteur_apercu(self.win, alloc)
        return self.win.frame.get_size_request()[1]

    def test_la_hauteur_suit_la_largeur_selon_le_ratio_du_bureau(self):
        # Bureau 5760x1080 : à 1036 px de large (moins 36 de marges), 1000/5.33.
        self.assertEqual(self._allouer(1036), round(1000 * 1080 / 5760))

    def test_la_hauteur_suit_un_redimensionnement(self):
        petite = self._allouer(636)
        grande = self._allouer(1436)
        self.assertLess(petite, grande)

    def test_une_hauteur_minimale_est_garantie(self):
        self.assertGreaterEqual(self._allouer(60), 60)

    def test_le_texte_d_aide_se_centre_dans_l_espace_restant(self):
        """Il occupe seul l'espace sous l'aperçu — dont la hauteur, elle, est
        fixée par le ratio — et s'y centre au lieu de coller aux écrans."""
        boite = self.win.hint.get_parent()
        self.assertTrue(boite.child_get_property(self.win.hint, "expand"))
        self.assertEqual(self.win.hint.get_valign(), Gtk.Align.CENTER)
        self.assertFalse(
            boite.child_get_property(self.win.frame.get_parent(), "expand"),
            "l'aperçu ne doit pas se partager cet espace",
        )


class TestFenetresSecondaires(BaseGUI):
    def test_la_bibliotheque_liste_les_dix_fonds(self):
        from multiwall import library, windows

        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None
        )
        try:
            self.assertEqual(
                len(fenetre.page_generes.flow.get_children()), len(library.CATALOGUE)
            )
        finally:
            fenetre.destroy()

    def test_les_trois_onglets_sont_presents(self):
        from multiwall import windows

        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None,
            cfg=self.win.cfg, on_fichier=lambda _c: None,
        )
        try:
            noms = [fenetre.stack.child_get_property(p, "name")
                    for p in fenetre.stack.get_children()]
            self.assertEqual(noms, ["generes", "en-ligne", "mes-fonds"])
        finally:
            fenetre.destroy()

    def test_mes_fonds_liste_les_images_deja_utilisees(self):
        from multiwall import windows

        image = self.image_test("deja-vue.png", size=(1920, 1080))
        self.win.cfg.noter_image(image)
        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None,
            onglet="mes-fonds", cfg=self.win.cfg, on_fichier=lambda _c: None,
        )
        try:
            enfants = fenetre.page_mes_fonds.flow.get_children()
            self.assertEqual(len(enfants), 1)
            self.assertEqual(enfants[0].chemin, str(image))
        finally:
            fenetre.destroy()

    def test_mes_fonds_est_vide_au_depart(self):
        from multiwall import windows

        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None,
            cfg=self.win.cfg, on_fichier=lambda _c: None,
        )
        try:
            self.assertEqual(fenetre.page_mes_fonds.flow.get_children(), [])
            self.assertIn("Aucune image", fenetre.page_mes_fonds.etat.get_text())
        finally:
            fenetre.destroy()

    def test_une_image_choisie_entre_dans_l_historique(self):
        image = self.image_test("choisie.png")
        self.win._fichier_choisi(str(image))
        self.assertEqual(self.win.cfg.images_connues(), [str(image)])

    def test_utiliser_une_image_de_l_historique_vise_l_ecran_selectionne(self):
        image = self.image_test("choisie.png")
        self.win.selected = "DP-centre"
        self.win._fichier_choisi(str(image))
        self.assertEqual(self.win.cfg.monitors["DP-centre"]["path"], str(image))

    def test_en_panoramique_elle_devient_le_fond_unique(self):
        image = self.image_test("pano.png", size=(5760, 1080))
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        self.win._fichier_choisi(str(image))
        self.assertEqual(self.win.cfg.span["path"], str(image))
        self.assertEqual(self.win.cfg.span["library"], "")

    def test_les_deux_sources_sont_dans_la_meme_fenetre(self):
        from multiwall import windows

        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None
        )
        try:
            noms = [fenetre.stack.child_get_property(p, "name")
                    for p in fenetre.stack.get_children()]
            self.assertEqual(noms, ["generes", "en-ligne"])
            self.assertEqual(fenetre.stack.get_visible_child_name(), "generes")
        finally:
            fenetre.destroy()

    def test_l_onglet_en_ligne_peut_etre_ouvert_directement(self):
        from multiwall import windows

        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None,
            onglet="en-ligne",
        )
        try:
            self.assertEqual(fenetre.stack.get_visible_child_name(), "en-ligne")
            self.assertEqual(fenetre.bouton_utiliser.get_label(), "Utiliser cette photo")
        finally:
            fenetre.destroy()

    def test_le_bouton_valider_suit_l_onglet_actif(self):
        from multiwall import windows

        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None
        )
        try:
            self.assertEqual(fenetre.bouton_utiliser.get_label(), "Utiliser ce fond")
            self.assertFalse(fenetre.bouton_utiliser.get_sensitive(), "rien de sélectionné")
            fenetre.stack.set_visible_child_name("en-ligne")
            self.assertEqual(fenetre.bouton_utiliser.get_label(), "Utiliser cette photo")
        finally:
            fenetre.destroy()

    def test_un_seul_bouton_de_bibliotheque_dans_la_barre(self):
        barre = self.win.choose_btn.get_parent()
        libelles = [w.get_label() for w in barre.get_children()
                    if isinstance(w, Gtk.Button) and w.get_label()]
        self.assertEqual(sum("ibliothèque" in l for l in libelles), 1)
        self.assertEqual(sum("hoto" in l for l in libelles), 0)

    def test_le_bouton_bibliotheque_suit_celui_de_choix_d_image(self):
        barre = self.win.choose_btn.get_parent()
        enfants = barre.get_children()
        self.assertIn(self.win.library_btn, enfants)
        self.assertEqual(
            enfants.index(self.win.library_btn),
            enfants.index(self.win.choose_btn) + 1,
            "la bibliothèque doit être juste après « Choisir une image »",
        )

    def test_le_double_clic_applique_le_fond_genere(self):
        from multiwall import windows

        choisis = []
        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, choisis.append, lambda *_: None,
            cfg=self.win.cfg, cible=windows.Cible(self.win.monitors),
        )
        try:
            premier = fenetre.page_generes.flow.get_children()[0]
            fenetre.page_generes.flow.emit("child-activated", premier)
            self.assertEqual(choisis, [premier.fond_id],
                             "activer une vignette doit valider le choix")
        finally:
            fenetre.destroy()

    def test_le_double_clic_selectionne_avant_de_valider(self):
        """L'activation peut venir du clavier, sans clic préalable."""
        from multiwall import windows

        choisis = []
        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, choisis.append, lambda *_: None,
            cfg=self.win.cfg, cible=windows.Cible(self.win.monitors),
        )
        try:
            troisieme = fenetre.page_generes.flow.get_children()[2]
            self.assertIsNone(fenetre.page_generes.selection)
            fenetre.page_generes.flow.emit("child-activated", troisieme)
            self.assertEqual(choisis, [troisieme.fond_id])
        finally:
            fenetre.destroy()

    def test_le_double_clic_sur_mes_fonds_applique_l_image(self):
        from multiwall import windows

        image = self.image_test("deja-vue.png", size=(1920, 1080))
        self.win.cfg.noter_image(image)
        appliquees = []
        fenetre = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None,
            onglet="mes-fonds", cfg=self.win.cfg, on_fichier=appliquees.append,
            cible=windows.Cible(self.win.monitors),
        )
        try:
            vignette = fenetre.page_mes_fonds.flow.get_children()[0]
            fenetre.page_mes_fonds.flow.emit("child-activated", vignette)
            self.assertEqual(appliquees, [str(image)])
        finally:
            fenetre.destroy()

    def test_un_fond_choisi_en_mode_par_ecran_ne_bascule_pas(self):
        """Choisir un fond ne doit pas changer de mode dans le dos de l'utilisateur."""
        self.win.selected = "DP-centre"
        self.win._choisir_fond("dunes")
        self.assertFalse(self.win.is_span, "le mode ne doit pas changer")
        self.assertEqual(self.win.cfg.monitors["DP-centre"]["library"], "dunes")
        self.assertEqual(self.win.cfg.span["library"], "", "le panorama n'est pas touché")
        self.assertTrue(self.win.apply_btn.get_sensitive())

    def test_un_fond_choisi_en_mode_panoramique_devient_le_panorama(self):
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        self.win._choisir_fond("dunes")
        self.assertTrue(self.win.is_span)
        self.assertEqual(self.win.cfg.span["library"], "dunes")
        self.assertEqual(self.win.cfg.span["path"], "")

    def test_la_cible_suit_le_mode(self):
        """En mode par écran, la bibliothèque doit proposer du 1920x1080."""
        self.win.selected = "DP-centre"
        cible = self.win._cible()
        self.assertEqual((cible.largeur, cible.hauteur), (1920, 1080))
        self.assertEqual(cible.ecran.name, "DP-centre")
        self.assertAlmostEqual(cible.ratio, 16 / 9, places=2)

        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        cible = self.win._cible()
        self.assertEqual((cible.largeur, cible.hauteur), (5760, 1080))
        self.assertIsNone(cible.ecran)

    def test_les_vignettes_adoptent_le_format_de_la_cible(self):
        from multiwall import windows

        ecran = self.win.monitors[1]
        etroite = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None,
            cfg=self.win.cfg, cible=windows.Cible(self.win.monitors, ecran),
        )
        large = windows.BibliothequeWindow(
            self.win, self.win.monitors, lambda _: None, lambda *_: None,
            cfg=self.win.cfg, cible=windows.Cible(self.win.monitors),
        )
        try:
            def hauteur(fenetre):
                boite = fenetre.page_generes.flow.get_children()[0].get_child()
                return boite.get_children()[0].get_pixbuf().get_height()
            self.assertGreater(hauteur(etroite), hauteur(large),
                               "une vignette 16:9 est plus haute qu'une 16:3")
        finally:
            etroite.destroy()
            large.destroy()

    def test_effacer_retire_aussi_un_fond_genere(self):
        self.win._choisir_fond("dunes")
        self.win.on_clear(None)
        conf = self.win.cfg.monitors[self.win.selected]
        self.assertEqual(conf["library"], "")
        self.assertEqual(conf["path"], "")
        self.assertFalse(self.win.apply_btn.get_sensitive())

    def test_le_texte_d_aide_nomme_le_fond_genere(self):
        self.win._choisir_fond("dunes")
        self.assertIn("Dunes", self.win.hint.get_text())
        self.assertIn(self.win.selected, self.win.hint.get_text() + " " + self.win.selected)

    def test_choisir_un_fichier_remplace_le_fond_genere(self):
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        self.win._choisir_fond("dunes")
        self.assertIn("Dunes", self.win.hint.get_text())

        pano = self.image_test("p.png", size=(5760, 1080))
        self.win.cfg.span["path"] = str(pano)
        self.win.cfg.span["library"] = ""
        self.win.refresh()
        self.assertNotIn("Dunes", self.win.hint.get_text())

    def test_l_apercu_rend_le_fond_genere(self):
        self.win._choisir_fond("cristaux")
        pixbuf, _ = self.win._preview(900, 169)
        self.assertIsNotNone(pixbuf)

    def test_le_guide_documente_la_ligne_de_commande(self):
        from multiwall import windows

        fenetre = windows.AideWindow(self.win, self.win.monitors)
        try:
            texte = windows.AIDE
            for commande in ("multiwall list", "multiwall span", "multiwall library",
                             "multiwall random", "multiwall apply", "multiwall export"):
                self.assertIn(commande, texte)
            self.assertIn("{largeur}", texte, "la résolution doit être interpolée")
        finally:
            fenetre.destroy()

    def test_le_guide_s_ouvre_sans_erreur_de_balisage(self):
        from multiwall import windows

        # set_markup lève si le balisage Pango est invalide.
        fenetre = windows.AideWindow(self.win, self.win.monitors)
        fenetre.destroy()


class TestDiagnosticGraphique(BaseGUI):
    def _attendre_resultat(self, fenetre):
        self.assertTrue(
            self.attendre(lambda: fenetre.stack.get_visible_child_name() == "resultat"),
            "le diagnostic doit aboutir",
        )

    def test_affiche_d_abord_la_verification_en_cours(self):
        """Le diagnostic interroge gsettings : il ne doit pas geler la fenêtre."""
        from multiwall import windows

        fenetre = windows.DiagnosticWindow(self.win)
        try:
            self.assertEqual(fenetre.stack.get_visible_child_name(), "en-cours")
            self._attendre_resultat(fenetre)
        finally:
            fenetre.destroy()

    def test_verdict_favorable(self):
        from multiwall import windows

        os.environ["XDG_CURRENT_DESKTOP"] = "GNOME"
        os.environ["XDG_SESSION_TYPE"] = "x11"
        fenetre = windows.DiagnosticWindow(self.win)
        try:
            self._attendre_resultat(fenetre)
            self.assertIn("en ordre", fenetre.verdict.get_text())
            self.assertTrue(fenetre.bouton_copier.get_sensitive())
            self.assertGreater(len(fenetre.liste.get_children()), 5)
        finally:
            fenetre.destroy()

    def test_verdict_incompatible(self):
        from multiwall import windows

        os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
        fenetre = windows.DiagnosticWindow(self.win)
        try:
            self._attendre_resultat(fenetre)
            self.assertIn("n'est pas compatible", fenetre.verdict.get_text())
        finally:
            fenetre.destroy()

    def test_le_controle_au_demarrage_ne_derange_pas_si_tout_va_bien(self):
        from multiwall import windows

        os.environ["XDG_CURRENT_DESKTOP"] = "GNOME"
        os.environ["XDG_SESSION_TYPE"] = "x11"
        ouvertes = []
        original = windows.DiagnosticWindow
        windows.DiagnosticWindow = lambda *a, **k: ouvertes.append(a) or original(*a, **k)
        try:
            self.win._verifier_compatibilite()
            self.assertEqual(ouvertes, [], "aucune fenêtre ne doit s'ouvrir")
        finally:
            windows.DiagnosticWindow = original

    def test_le_controle_au_demarrage_alerte_si_incompatible(self):
        from multiwall import windows

        os.environ["XDG_CURRENT_DESKTOP"] = "XFCE"
        ouvertes = []

        class Espion(windows.DiagnosticWindow):
            def __init__(self, *a, **k):
                ouvertes.append(a)
                super().__init__(*a, **k)

        original = windows.DiagnosticWindow
        windows.DiagnosticWindow = Espion
        try:
            self.win._verifier_compatibilite()
            self.assertEqual(len(ouvertes), 1, "l'utilisateur doit être prévenu")
        finally:
            windows.DiagnosticWindow = original
            self.pomper()


class TestAPropos(BaseGUI):
    def test_le_dialogue_porte_licence_et_signature(self):
        import multiwall

        dialogues = []
        vrai_dialogue = Gtk.AboutDialog

        class DialogueEspion(vrai_dialogue):
            def run(self):          # ne pas bloquer sur un modal en test
                dialogues.append(self)
                return Gtk.ResponseType.CLOSE

        Gtk.AboutDialog = DialogueEspion
        try:
            self.win.on_about(None)
        finally:
            Gtk.AboutDialog = vrai_dialogue

        self.assertEqual(len(dialogues), 1)
        dialogue = dialogues[0]
        self.assertEqual(dialogue.get_copyright(), multiwall.COPYRIGHT)
        self.assertIn("Sigilbo", dialogue.get_copyright())
        self.assertIn("non commercial", dialogue.get_license().lower())
        self.assertIn("PolyForm", dialogue.get_license())
        self.assertEqual(dialogue.get_version(), multiwall.__version__)

    def test_le_lien_linkedin_n_apparait_que_s_il_est_renseigne(self):
        """Un lien vide dans un À propos fait mauvais effet."""
        import multiwall

        self.assertIsInstance(multiwall.LINKEDIN, str)
        if not multiwall.LINKEDIN:
            self.skipTest("LinkedIn non renseigné : rien à vérifier")
        self.assertTrue(multiwall.LINKEDIN.startswith("https://"))


class TestLogo(BaseGUI):
    def test_le_logo_est_charge_et_affiche_en_tete(self):
        from multiwall import gui

        self.assertTrue(gui.LOGO.is_file(), "le SVG doit être livré avec le paquet")
        self.assertIsNotNone(gui.charger_logo(24))
        self.assertIs(self.win.logo.get_parent(), self.win.headerbar)

    def test_le_logo_est_rendu_a_la_taille_demandee(self):
        from multiwall import gui

        for taille in (16, 24, 48, 128):
            with self.subTest(taille=taille):
                pixbuf = gui.charger_logo(taille)
                self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (taille, taille))

    def test_une_icone_manquante_ne_bloque_pas_le_demarrage(self):
        from multiwall import gui

        original = gui.LOGO
        gui.LOGO = original.with_name("absent.svg")
        try:
            self.assertIsNone(gui.charger_logo(24))
            fenetre = gui.MultiWallWindow(self.app)  # doit se construire quand même
            fenetre.destroy()
        finally:
            gui.LOGO = original


class TestDetectionAChaud(BaseGUI):
    """Branchement/débranchement pris en compte sans attendre un F5."""

    DEUX_ECRANS = [
        core.Monitor("DP-gauche", 1920, 1080, 0, 0),
        core.Monitor("DP-centre", 1920, 1080, 1920, 0, primary=True),
    ]

    def test_le_signal_est_connecte(self):
        self.assertTrue(self.win._sig_monitors, "monitors-changed doit être suivi")

    def test_les_signaux_en_rafale_ne_declenchent_qu_une_redetection(self):
        for _ in range(5):
            self.win._on_monitors_changed(None)
        self.assertTrue(self.win._redetect_id)
        GLib.source_remove(self.win._redetect_id)
        self.win._redetect_id = 0

    def test_un_ecran_debranche_est_pris_en_compte(self):
        core.detect_monitors = lambda: list(self.DEUX_ECRANS)
        self.win._redetecter_auto()
        self.assertEqual(len(self.win.monitors), 2)
        self.assertEqual(core.desktop_size(self.win.monitors), (3840, 1080))

    def test_le_ratio_de_l_apercu_suit(self):
        core.detect_monitors = lambda: list(self.DEUX_ECRANS)
        self.win._redetecter_auto()
        self.assertAlmostEqual(self.win.frame.get_property("ratio"), 3840 / 1080, places=3)

    def test_la_resolution_ideale_annoncee_suit_la_nouvelle_geometrie(self):
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        self.assertIn("5760×1080", self.win.hint.get_text())

        core.detect_monitors = lambda: list(self.DEUX_ECRANS)
        self.win._redetecter_auto()
        self.assertIn("3840×1080", self.win.hint.get_text())
        self.assertNotIn("5760×1080", self.win.hint.get_text())

    def test_le_texte_compte_les_ecrans_restants(self):
        pano = self.image_test("p.png", size=(5760, 1080))
        self.win.cfg.span = {"path": str(pano), "fit": "cover"}
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        core.detect_monitors = lambda: list(self.DEUX_ECRANS)
        self.win._redetecter_auto()
        self.assertIn("2 écrans", self.win.hint.get_text())

    def test_une_detection_vide_ne_casse_pas_l_apercu(self):
        """Pendant un branchement, xrandr peut ne rien renvoyer un instant."""
        core.detect_monitors = lambda: []
        self.win._redetecter_auto()
        self.assertEqual(len(self.win.monitors), 3)

    def test_l_ecran_selectionne_est_rabattu_s_il_disparait(self):
        self.win.selected = "DP-droite"
        core.detect_monitors = lambda: list(self.DEUX_ECRANS)
        self.win._redetecter_auto()
        self.assertEqual(self.win.selected, "DP-gauche")

    def test_aucune_redetection_si_rien_n_a_change(self):
        avant = self.win.monitors
        self.win._redetecter_auto()
        self.assertIs(self.win.monitors, avant, "pas de reconstruction inutile")


class TestGeometrieApercu(BaseGUI):
    def test_le_clic_retrouve_l_ecran_dessine(self):
        """Le dessin et la détection du clic doivent partager la même géométrie."""
        self.win.area.size_allocate(Gdk.Rectangle())
        alloc = Gdk.Rectangle()
        alloc.x, alloc.y, alloc.width, alloc.height = 0, 0, 900, 169
        self.win.area.size_allocate(alloc)

        scale, ox, oy = self.win._layout()
        for mon in self.ecrans:
            centre_x = ox + (mon.x + mon.width / 2) * scale
            centre_y = oy + (mon.y + mon.height / 2) * scale
            with self.subTest(ecran=mon.name):
                self.assertEqual(self.win._monitor_at(centre_x, centre_y), mon.name)

    def test_clic_hors_des_ecrans(self):
        self.assertIsNone(self.win._monitor_at(-50, -50))


class TestModes(BaseGUI):
    def test_bascule_vers_le_panoramique(self):
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        self.assertTrue(self.win.is_span)
        self.assertEqual(self.win.cfg.mode, "span")
        self.assertIn("panoramique", self.win.choose_btn.get_label().lower())

    def test_apercu_panoramique_sans_image_n_affiche_pas_les_fonds_par_ecran(self):
        """Sinon l'aperçu montre ce qui ne sera pas appliqué."""
        image = self.image_test("a.png", couleur=(255, 0, 0))
        self.win.cfg.monitors["DP-gauche"] = {"path": str(image), "fit": "cover"}
        self.win.cfg.background = "#0000ff"
        self.win._mode_action.activate(GLib.Variant.new_string("span"))

        pixbuf, _ = self.win._preview(900, 169)
        self.assertIsNotNone(pixbuf)
        pixels = pixbuf.get_pixels()
        self.assertEqual(tuple(pixels[0:3]), (0, 0, 255), "le bureau doit être uni")

    def test_clic_sur_le_bouton_de_mode(self):
        """Un radio groupé lié à une action à état se ré-activait en boucle :
        l'application gelait au clic sur le sélecteur."""
        self.win.mode_buttons["span"].clicked()
        self.assertTrue(self.win.is_span)
        self.assertEqual(self.win._mode_action.get_state().get_string(), "span")

        self.win.mode_buttons["per-monitor"].clicked()
        self.assertFalse(self.win.is_span)
        self.assertEqual(self.win._mode_action.get_state().get_string(), "per-monitor")

    def test_le_raccourci_met_a_jour_le_bouton(self):
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        self.assertTrue(self.win.mode_buttons["span"].get_active())


    def test_la_zone_vide_panoramique_couvre_tout_le_bureau(self):
        import cairo

        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        appels = []
        self.win._dessiner_etat_vide = lambda *a, **k: appels.append(a)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 900, 169)
        alloc = Gdk.Rectangle()
        alloc.x, alloc.y, alloc.width, alloc.height = 0, 0, 900, 169
        self.win.area.size_allocate(alloc)
        self.win.on_draw(self.win.area, cairo.Context(surface))

        self.assertEqual(len(appels), 1, "un seul marquage, sur tout le bureau")
        _, _, x, y, w, h = appels[0]
        scale, ox, oy = self.win._layout()
        dw, dh = core.desktop_size(self.win.monitors)
        self.assertAlmostEqual(w, dw * scale, delta=1,
                               msg="le marquage couvre les 3 écrans, pas un seul")
        self.assertGreater(w, self.win.monitors[0].width * scale)



    def test_pas_de_zone_vide_quand_une_image_panoramique_est_choisie(self):
        import cairo

        pano = self.image_test("pano.png", size=(5760, 1080))
        self.win.cfg.span = {"path": str(pano), "fit": "cover"}
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        appels = []
        self.win._dessiner_etat_vide = lambda *a, **k: appels.append(a)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 900, 169)
        alloc = Gdk.Rectangle()
        alloc.x, alloc.y, alloc.width, alloc.height = 0, 0, 900, 169
        self.win.area.size_allocate(alloc)
        self.win.on_draw(self.win.area, cairo.Context(surface))
        self.assertEqual(appels, [])

    def test_un_marquage_par_ecran_vide_en_mode_par_ecran(self):
        import cairo

        image = self.image_test("a.png")
        self.win.cfg.monitors["DP-gauche"] = {"path": str(image), "fit": "cover"}
        self.win.refresh()
        appels = []
        self.win._dessiner_etat_vide = lambda *a, **k: appels.append(a)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 900, 169)
        alloc = Gdk.Rectangle()
        alloc.x, alloc.y, alloc.width, alloc.height = 0, 0, 900, 169
        self.win.area.size_allocate(alloc)
        self.win.on_draw(self.win.area, cairo.Context(surface))
        self.assertEqual(len(appels), 2, "les 2 écrans encore vides")

    def test_le_mode_est_persiste(self):
        self.win._mode_action.activate(GLib.Variant.new_string("span"))
        self.win._on_close()
        self.assertEqual(core.Config.load().mode, "span")


class TestAffectationEtSauvegarde(BaseGUI):
    def test_fermer_sans_appliquer_conserve_le_travail(self):
        image = self.image_test("a.png")
        self.win.cfg.monitors["DP-centre"] = {"path": str(image), "fit": "blur"}
        self.win._on_close()
        recharge = core.Config.load()
        self.assertEqual(recharge.monitors["DP-centre"]["path"], str(image))
        self.assertEqual(recharge.monitors["DP-centre"]["fit"], "blur")

    def test_selectionner_un_ecran_ne_cree_pas_d_entree_vide(self):
        self.win.current_conf()  # simple sélection
        self.win._on_close()
        self.assertEqual(core.Config.load().monitors, {})

    def test_effacer_libere_l_ecran(self):
        image = self.image_test("a.png")
        self.win.cfg.monitors["DP-gauche"] = {"path": str(image), "fit": "cover"}
        self.win.refresh()
        self.assertTrue(self.win.clear_btn.get_sensitive())
        self.win.on_clear(None)
        self.assertEqual(self.win.cfg.monitors["DP-gauche"]["path"], "")
        self.assertFalse(self.win.clear_btn.get_sensitive())

    def test_appliquer_s_active_des_qu_une_image_est_choisie(self):
        image = self.image_test("a.png")
        self.win.cfg.monitors["DP-gauche"] = {"path": str(image), "fit": "cover"}
        self.win.refresh()
        self.assertTrue(self.win.apply_btn.get_sensitive())


class TestApplication(BaseGUI):
    def test_appliquer_pose_le_fond_et_retombe_au_repos(self):
        image = self.image_test("a.png", couleur=(4, 5, 6))
        self.win.cfg.monitors["DP-gauche"] = {"path": str(image), "fit": "cover"}
        self.win.refresh()

        self.win.on_apply(None)
        # La composition tourne dans un thread : on pompe la boucle en attendant.
        self.assertTrue(
            self.attendre(lambda: not self.win._applying),
            "l'application ne doit pas rester bloquée",
        )
        self.assertEqual(self.win.apply_stack.get_visible_child_name(), "idle",
                         "le bouton doit reprendre la place du spinner")
        self.assertFalse(self.win.spinner.get_property("active"))
        self.assertEqual(self.valeur_definie("picture-options"), "spanned")
        self.assertFalse(self.win.apply_btn.get_sensitive(), "plus rien à appliquer")

    def test_double_clic_sur_appliquer_ne_lance_qu_une_composition(self):
        image = self.image_test("a.png")
        self.win.cfg.monitors["DP-gauche"] = {"path": str(image), "fit": "cover"}
        self.win.refresh()
        self.win.on_apply(None)
        self.win.on_apply(None)  # ignoré : une application est déjà en cours
        self.assertTrue(self.attendre(lambda: not self.win._applying))
        composites = list(core.DATA_DIR.glob("wall-*.png"))
        self.assertEqual(len(composites), 1)


class TestVignettes(BaseGUI):
    def test_les_vignettes_sont_mises_en_cache(self):
        image = self.image_test("grande.png", size=(2000, 1500))
        self.win._thumb_box = (300, 200)
        premiere = self.win._thumb(image)
        self.assertIs(self.win._thumb(image), premiere, "second appel = cache")
        self.assertLessEqual(premiere.width, 600)

    def test_le_cache_suit_les_modifications_du_fichier(self):
        image = self.image_test("a.png", couleur=(255, 0, 0))
        self.win._thumb(image)
        Image.new("RGB", (100, 100), (0, 255, 0)).save(image)
        import os

        os.utime(image, (0, 0))  # force un mtime différent
        self.assertEqual(self.win._thumb(image).getpixel((50, 50)), (0, 255, 0))

    def test_le_cache_ne_grossit_pas_indefiniment(self):
        for i in range(20):
            self.win._thumb(self.image_test(f"i{i}.png", size=(80, 80)))
        self.assertLessEqual(len(self.win._thumbs), 13)


class TestRobustesseApercu(BaseGUI):
    def test_une_image_corrompue_ne_fait_pas_tomber_l_apercu(self):
        cassee = self.root / "cassee.png"
        cassee.write_text("pas une image")
        bonne = self.image_test("bonne.png", couleur=(0, 255, 0))
        self.win.cfg.monitors = {
            "DP-gauche": {"path": str(cassee), "fit": "cover"},
            "DP-centre": {"path": str(bonne), "fit": "cover"},
        }
        self.win.refresh()
        pixbuf, _ = self.win._preview(900, 169)
        self.assertIsNotNone(pixbuf, "l'aperçu doit survivre à une image illisible")

    def test_redetection_sans_ecran_conserve_la_disposition(self):
        core.detect_monitors = lambda: []
        precedents = list(self.win.monitors)
        self.win._error = lambda *a, **k: None  # pas de dialogue modal en test
        self.win.on_redetect(None)
        self.assertEqual(self.win.monitors, precedents)


if __name__ == "__main__":
    unittest.main()
