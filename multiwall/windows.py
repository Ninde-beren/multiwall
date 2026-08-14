# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Fenêtres secondaires : bibliothèque de fonds, et guide d'utilisation.

La bibliothèque réunit deux sources sous un même toit : les fonds **générés**
(instantanés, hors ligne) et les **photos en ligne** de Wikimedia Commons. Un
seul point d'entrée dans l'interface, deux onglets à l'intérieur.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

import os  # noqa: E402

from gi.repository import Pango  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

from . import core, doctor, library, photos  # noqa: E402

VIGNETTE_L = 320


class Cible:
    """Format visé par la bibliothèque.

    En mode panoramique c'est le bureau entier ; en mode « une image par
    écran » c'est l'écran sélectionné. Proposer des fonds 5760×1080 pour
    habiller un seul moniteur 1920×1080 n'aurait aucun sens.
    """

    def __init__(self, ecrans, ecran=None):
        self.ecran = ecran                      # None = bureau entier
        if ecran is not None:
            self.ecrans = [core.Monitor(ecran.name, ecran.width, ecran.height, 0, 0)]
            self.largeur, self.hauteur = ecran.width, ecran.height
            self.description = f"l'écran {ecran.name}"
        else:
            self.ecrans = ecrans
            self.largeur, self.hauteur = core.desktop_size(ecrans)
            self.description = "votre bureau"

    @property
    def ratio(self) -> float:
        return self.largeur / self.hauteur if self.hauteur else 0.0


def pil_to_pixbuf(img) -> GdkPixbuf.Pixbuf:
    data = GLib.Bytes.new(img.tobytes())
    return GdkPixbuf.Pixbuf.new_from_bytes(
        data, GdkPixbuf.Colorspace.RGB, False, 8, img.width, img.height, img.width * 3
    )


def _grille() -> Gtk.FlowBox:
    flow = Gtk.FlowBox()
    flow.set_valign(Gtk.Align.START)
    flow.set_max_children_per_line(2)
    flow.set_min_children_per_line(1)
    flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
    # Vrai par défaut : sans cela, un simple clic validerait et fermerait la
    # fenêtre. On veut sélectionner d'un clic, valider d'un double.
    flow.set_activate_on_single_click(False)
    flow.set_margin_start(12)
    flow.set_margin_end(12)
    flow.set_margin_top(10)
    flow.set_margin_bottom(12)
    flow.set_row_spacing(10)
    flow.set_column_spacing(10)
    return flow


class PageGeneres(Gtk.Box):
    """Fonds calculés localement : aucun fichier, aucune connexion."""

    titre_bouton = "Utiliser ce fond"

    def __init__(self, monitors, on_change, cible):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.monitors = monitors
        self.on_change = on_change
        self.cible = cible          # format visé : un écran, ou le bureau entier
        self.selection: str | None = None

        aide = Gtk.Label()
        aide.set_markup(
            f"<small>Ces fonds ne sont pas des fichiers : ils sont calculés à la "
            f"résolution exacte de {GLib.markup_escape_text(cible.description)} "
            f"({cible.largeur}×{cible.hauteur}).</small>"
        )
        aide.get_style_context().add_class("dim-label")
        aide.set_line_wrap(True)
        aide.set_margin_top(10)
        aide.set_margin_start(12)
        aide.set_margin_end(12)
        self.pack_start(aide, False, False, 0)

        defilement = Gtk.ScrolledWindow()
        defilement.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.flow = _grille()
        self.flow.connect("selected-children-changed", self._selection_changee)
        defilement.add(self.flow)
        self.pack_start(defilement, True, True, 0)

        self._remplir()

    def _remplir(self) -> None:
        # La vignette adopte le format de la cible : un aperçu 16:3 serait
        # trompeur quand le fond ira sur un seul écran 16:9.
        largeur, hauteur = self.cible.largeur, self.cible.hauteur
        hauteur_vignette = max(round(VIGNETTE_L * hauteur / largeur), 24) if largeur else 60
        ancres = library.ancres_ecrans(self.cible.ecrans, VIGNETTE_L)
        for fond in library.CATALOGUE:
            boite = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            image = fond.rendu((VIGNETTE_L, hauteur_vignette), ancres)
            boite.pack_start(Gtk.Image.new_from_pixbuf(pil_to_pixbuf(image)), False, False, 0)
            etiquette = Gtk.Label(label=fond.nom)
            etiquette.set_xalign(0.0)
            boite.pack_start(etiquette, False, False, 0)

            enfant = Gtk.FlowBoxChild()
            enfant.add(boite)
            enfant.fond_id = fond.id
            enfant.set_tooltip_text(f"{fond.nom} — {fond.style} / {fond.palette}")
            self.flow.add(enfant)

    def _selection_changee(self, _flow) -> None:
        enfants = self.flow.get_selected_children()
        self.selection = enfants[0].fond_id if enfants else None
        self.on_change()

    def peut_valider(self) -> bool:
        return self.selection is not None


class PageEnLigne(Gtk.Box):
    """Photos panoramiques de Wikimedia Commons, sans quitter l'application."""

    titre_bouton = "Utiliser cette photo"

    #: Chaque vignette est une requête : en demander trop épuise le quota.
    MAX_RESULTATS = 6

    def __init__(self, monitors, on_change, cible):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.monitors = monitors
        self.on_change = on_change
        self.cible = cible
        self.resultats: list = []
        self.selection = None
        self.en_cours = False
        self.source = "commons"

        barre = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        barre.set_margin_start(12)
        barre.set_margin_end(12)
        barre.set_margin_top(12)

        # Un sélecteur à une seule entrée n'apporte rien : il n'apparaît que
        # si une deuxième source est déclarée.
        self.combo_source = None
        if len(photos.SOURCES) > 1:
            self.combo_source = Gtk.ComboBoxText()
            for identifiant, source in photos.SOURCES.items():
                self.combo_source.append(identifiant, source.nom)
            self.combo_source.set_active_id(self.source)
            self.combo_source.connect("changed", self._source_changee)
            barre.pack_start(self.combo_source, False, False, 0)

        self.champ = Gtk.SearchEntry()
        self.champ.set_placeholder_text("Rechercher (en anglais : mountain, coast, city…)")
        self.champ.connect("activate", lambda _e: self.lancer(self.champ.get_text()))
        barre.pack_start(self.champ, True, True, 0)
        self.pack_start(barre, False, False, 0)

        # Les thèmes dépendent de la source : ils sont reconstruits à chaque
        # changement plutôt que d'en proposer d'inadaptés.
        self.themes = Gtk.FlowBox()
        self.themes.set_selection_mode(Gtk.SelectionMode.NONE)
        self.themes.set_max_children_per_line(8)
        self.themes.set_margin_start(12)
        self.themes.set_margin_end(12)
        self.themes.set_margin_top(8)
        self.pack_start(self.themes, False, False, 0)
        self._remplir_themes()

        self.etat = Gtk.Label()
        self.etat.get_style_context().add_class("dim-label")
        self.etat.set_line_wrap(True)
        self.etat.set_margin_top(10)
        self.etat.set_margin_start(12)
        self.etat.set_margin_end(12)
        self.etat.set_text(photos.SOURCES[self.source].note)
        self.pack_start(self.etat, False, False, 0)

        defilement = Gtk.ScrolledWindow()
        defilement.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.flow = _grille()
        self.flow.connect("selected-children-changed", self._selection_changee)
        defilement.add(self.flow)
        self.pack_start(defilement, True, True, 0)

    def _remplir_themes(self) -> None:
        for enfant in self.themes.get_children():
            self.themes.remove(enfant)
        for libelle, requete in photos.SOURCES[self.source].themes:
            bouton = Gtk.Button(label=libelle)
            bouton.connect("clicked", lambda _b, r=requete, l=libelle: self.lancer(r, l))
            self.themes.add(bouton)
        self.themes.show_all()

    def _source_changee(self, combo) -> None:
        identifiant = combo.get_active_id()
        if not identifiant or identifiant == self.source or self.en_cours:
            return
        self.source = identifiant
        self.resultats = []
        self.selection = None
        for enfant in self.flow.get_children():
            self.flow.remove(enfant)
        self._remplir_themes()
        self.etat.set_text(photos.SOURCES[self.source].note)
        self.on_change()

    # ------------------------------------------------------------ Recherche --
    def lancer(self, terme: str, libelle: str | None = None) -> None:
        terme = (terme or "").strip()
        if not terme or self.en_cours:
            return
        self.en_cours = True
        self.resultats = []
        self.selection = None
        for enfant in self.flow.get_children():
            self.flow.remove(enfant)
        self.etat.set_text(f"Recherche de « {libelle or terme} »…")
        self.on_change()

        ratio = self.cible.ratio

        def travail():
            try:
                trouvees = photos.rechercher(
                    terme, ratio, source=self.source
                )[: self.MAX_RESULTATS]
                if not trouvees:
                    GLib.idle_add(self._fin, None, True)
                    return
                # Vignette par vignette : l'utilisateur voit la grille se
                # remplir au lieu d'attendre devant une fenêtre vide.
                for rang, photo in enumerate(trouvees, 1):
                    try:
                        donnees = photos.telecharger_vignette(photo)
                    except photos.ReseauIndisponible:
                        donnees = None  # aperçu manquant, photo utilisable quand même
                    GLib.idle_add(self._ajouter, photo, donnees, rang, len(trouvees))
                GLib.idle_add(self._fin, None, False)
            except photos.ReseauIndisponible as exc:
                GLib.idle_add(self._fin, exc, False)
            except Exception as exc:  # pragma: no cover - garde-fou
                GLib.idle_add(self._fin, exc, False)

        threading.Thread(target=travail, daemon=True).start()

    def _ajouter(self, photo, donnees, rang, total) -> bool:
        boite = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)

        pixbuf = None
        if donnees:
            chargeur = GdkPixbuf.PixbufLoader()
            try:
                chargeur.write(donnees)
                chargeur.close()
                pixbuf = chargeur.get_pixbuf()
            except GLib.Error:
                pixbuf = None

        if pixbuf is not None:
            boite.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 0)
        else:
            substitut = Gtk.Label(label="aperçu indisponible")
            substitut.get_style_context().add_class("dim-label")
            substitut.set_size_request(320, 90)
            boite.pack_start(substitut, False, False, 0)

        titre = Gtk.Label(label=photo.nom[:56])
        titre.set_xalign(0.0)
        titre.set_ellipsize(3)
        boite.pack_start(titre, False, False, 0)

        credit = Gtk.Label()
        credit.set_markup(
            f"<small>{GLib.markup_escape_text(photo.licence)} · "
            f"{GLib.markup_escape_text(photo.auteur[:38])} · "
            f"{photo.largeur}×{photo.hauteur}</small>"
        )
        credit.get_style_context().add_class("dim-label")
        credit.set_xalign(0.0)
        boite.pack_start(credit, False, False, 0)

        enfant = Gtk.FlowBoxChild()
        enfant.add(boite)
        enfant.photo = photo
        enfant.set_tooltip_text(f"{photo.nom}\n{photo.licence} — {photo.auteur}")
        self.flow.add(enfant)
        self.flow.show_all()
        self.resultats.append(photo)
        self.etat.set_text(f"Chargement des aperçus… {rang}/{total}")
        return False

    def _fin(self, erreur, vide) -> bool:
        self.en_cours = False
        if erreur is not None:
            self.etat.set_text(str(erreur))
        elif vide:
            self.etat.set_text(
                "Aucune photo au format de votre bureau pour cette recherche. "
                "Essayez un autre terme, en anglais."
            )
        else:
            self.etat.set_text(
                f"{len(self.resultats)} photo(s) au format de votre bureau. "
                "Les images restent la propriété de leurs auteurs, sous la licence indiquée."
            )
        self.on_change()
        return False

    def _selection_changee(self, _flow) -> None:
        enfants = self.flow.get_selected_children()
        self.selection = enfants[0].photo if enfants else None
        self.on_change()

    def peut_valider(self) -> bool:
        return self.selection is not None and not self.en_cours


class PageMesFonds(Gtk.Box):
    """Les images déjà apportées par l'utilisateur, la plus récente en tête."""

    titre_bouton = "Utiliser cette image"

    MAX_AFFICHEES = 24

    def __init__(self, monitors, on_change, cfg):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.monitors = monitors
        self.on_change = on_change
        self.cfg = cfg
        self.selection: str | None = None

        barre = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        barre.set_margin_start(12)
        barre.set_margin_end(12)
        barre.set_margin_top(10)
        self.etat = Gtk.Label()
        self.etat.get_style_context().add_class("dim-label")
        self.etat.set_xalign(0.0)
        self.etat.set_line_wrap(True)
        barre.pack_start(self.etat, True, True, 0)
        self.bouton_oublier = Gtk.Button(label="Oublier")
        self.bouton_oublier.set_tooltip_text(
            "Retire l'image de cette liste, sans toucher au fichier"
        )
        self.bouton_oublier.set_sensitive(False)
        self.bouton_oublier.connect("clicked", self._oublier)
        barre.pack_end(self.bouton_oublier, False, False, 0)
        self.pack_start(barre, False, False, 0)

        defilement = Gtk.ScrolledWindow()
        defilement.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.flow = _grille()
        self.flow.connect("selected-children-changed", self._selection_changee)
        defilement.add(self.flow)
        self.pack_start(defilement, True, True, 0)

        self._remplir()

    def _remplir(self) -> None:
        for enfant in self.flow.get_children():
            self.flow.remove(enfant)
        self.selection = None

        chemins = self.cfg.images_connues()[: self.MAX_AFFICHEES]
        if not chemins:
            self.etat.set_text(
                "Aucune image pour l'instant. Celles que vous choisirez ou déposerez "
                "apparaîtront ici."
            )
            return
        self.etat.set_text(f"{len(chemins)} image(s) déjà utilisée(s), la plus récente d'abord.")

        for chemin in chemins:
            vignette = self._vignette(chemin)
            if vignette is None:
                continue
            boite = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            boite.pack_start(Gtk.Image.new_from_pixbuf(vignette), False, False, 0)

            nom = Gtk.Label(label=os.path.basename(chemin))
            nom.set_xalign(0.0)
            nom.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            nom.set_max_width_chars(38)
            boite.pack_start(nom, False, False, 0)

            enfant = Gtk.FlowBoxChild()
            enfant.add(boite)
            enfant.chemin = chemin
            enfant.set_tooltip_text(chemin)
            self.flow.add(enfant)

    def _vignette(self, chemin: str):
        """Aperçu au ratio de l'image, décodé en basse résolution."""
        try:
            image = Image.open(chemin)
            image.draft("RGB", (VIGNETTE_L * 2, VIGNETTE_L * 2))
            image = ImageOps.exif_transpose(image).convert("RGB")
            hauteur = max(round(VIGNETTE_L * image.height / image.width), 20)
            return pil_to_pixbuf(image.resize((VIGNETTE_L, hauteur), Image.BICUBIC))
        except Exception:
            return None  # fichier illisible : on le passe sous silence

    def _selection_changee(self, _flow) -> None:
        enfants = self.flow.get_selected_children()
        self.selection = enfants[0].chemin if enfants else None
        self.bouton_oublier.set_sensitive(self.selection is not None)
        self.on_change()

    def _oublier(self, _bouton) -> None:
        if self.selection:
            self.cfg.oublier_image(self.selection)
            self._remplir()
            self.flow.show_all()
            self.on_change()

    def peut_valider(self) -> bool:
        return self.selection is not None


class BibliothequeWindow(Gtk.Window):
    """Les deux sources de fonds panoramiques, réunies en deux onglets."""

    def __init__(self, parent, monitors, on_fond_genere, on_photo, onglet: str = "generes",
                 cfg=None, on_fichier=None, cible=None):
        super().__init__(title="Bibliothèque")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(860, 660)
        self.monitors = monitors
        self.on_fond_genere = on_fond_genere
        self.on_photo = on_photo
        self.on_fichier = on_fichier
        self.cible = cible or Cible(monitors)
        self._telechargement = False

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.page_generes = PageGeneres(monitors, self._etat_change, self.cible)
        self.page_en_ligne = PageEnLigne(monitors, self._etat_change, self.cible)
        self.stack.add_titled(self.page_generes, "generes", "Fonds générés")
        self.stack.add_titled(self.page_en_ligne, "en-ligne", "Photos en ligne")
        self.page_mes_fonds = None
        if cfg is not None:
            self.page_mes_fonds = PageMesFonds(monitors, self._etat_change, cfg)
            self.stack.add_titled(self.page_mes_fonds, "mes-fonds", "Mes fonds")
        self.stack.connect("notify::visible-child", lambda *_: self._etat_change())

        # Double-clic (ou Entrée) sur une vignette : équivaut au bouton.
        for page in (self.page_generes, self.page_en_ligne, self.page_mes_fonds):
            if page is not None:
                page.flow.connect("child-activated", self._activer)

        entete = Gtk.HeaderBar(show_close_button=True)
        self.set_title(
            "Bibliothèque" if self.cible.ecran is None
            else f"Bibliothèque — {self.cible.ecran.name}"
        )
        selecteur = Gtk.StackSwitcher()
        selecteur.set_stack(self.stack)
        entete.set_custom_title(selecteur)
        self.bouton_utiliser = Gtk.Button(label=PageGeneres.titre_bouton)
        self.bouton_utiliser.get_style_context().add_class("suggested-action")
        self.bouton_utiliser.set_sensitive(False)
        self.bouton_utiliser.connect("clicked", self._valider)
        entete.pack_end(self.bouton_utiliser)
        self.spinner = Gtk.Spinner()
        entete.pack_end(self.spinner)
        self.set_titlebar(entete)

        self.add(self.stack)
        self.stack.show_all()  # sinon le Stack n'a aucun enfant visible
        if onglet in [self.stack.child_get_property(p, "name")
                      for p in self.stack.get_children()]:
            self.stack.set_visible_child_name(onglet)
        self._etat_change()
        self.connect("key-press-event", self._touche)

    # ------------------------------------------------------------- Interne --
    @property
    def page(self):
        return self.stack.get_visible_child()

    def _activer(self, flow, enfant) -> None:
        """Une vignette a été activée : on la sélectionne puis on valide.

        La sélection suit normalement le clic, mais l'activation peut aussi
        venir du clavier sur une vignette qui n'était pas encore choisie.
        """
        flow.select_child(enfant)
        self._valider(None)

    def _etat_change(self) -> None:
        page = self.page
        if page is None:
            return
        self.bouton_utiliser.set_label(page.titre_bouton)
        self.bouton_utiliser.set_sensitive(page.peut_valider() and not self._telechargement)

    def _valider(self, _bouton) -> None:
        page = self.page
        if page is self.page_generes:
            if page.selection:
                self.on_fond_genere(page.selection)
                self.destroy()
            return
        if page is self.page_mes_fonds:
            if page.selection and self.on_fichier:
                self.on_fichier(page.selection)
                self.destroy()
            return
        self._telecharger(page.selection)

    def _telecharger(self, photo) -> None:
        if photo is None or self._telechargement:
            return
        self._telechargement = True
        self.spinner.start()
        self.bouton_utiliser.set_sensitive(False)
        self.page_en_ligne.etat.set_text(f"Téléchargement de « {photo.nom[:40]} »…")
        largeur = self.cible.largeur

        def travail():
            try:
                chemin = photos.obtenir(photo, largeur)
                photos.purger()
                GLib.idle_add(self._telechargee, chemin, photo, None)
            except Exception as exc:
                GLib.idle_add(self._telechargee, None, photo, exc)

        threading.Thread(target=travail, daemon=True).start()

    def _telechargee(self, chemin, photo, erreur) -> bool:
        self._telechargement = False
        self.spinner.stop()
        if erreur is not None:
            self.page_en_ligne.etat.set_text(f"Échec : {erreur}")
            self._etat_change()
            return False
        self.on_photo(str(chemin), photo)
        self.destroy()
        return False

    def _touche(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False


class DiagnosticWindow(Gtk.Window):
    """Vérification du système, en version graphique.

    Le diagnostic interroge gsettings et xrandr : quelques centaines de
    millisecondes qui gèleraient la fenêtre. Il tourne donc dans un thread,
    derrière un indicateur d'activité.
    """

    ICONES = {
        doctor.OK: "emblem-ok-symbolic",
        doctor.ATTENTION: "dialog-warning-symbolic",
        doctor.ECHEC: "dialog-error-symbolic",
    }

    def __init__(self, parent=None):
        super().__init__(title="Vérification du système")
        if parent is not None:
            self.set_transient_for(parent)
            self.set_modal(True)
        self.set_default_size(620, 560)
        self.rapport = None

        entete = Gtk.HeaderBar(show_close_button=True, title="Vérification du système")
        self.bouton_copier = Gtk.Button(label="Copier le rapport")
        self.bouton_copier.set_tooltip_text(
            "Copie le diagnostic, à joindre à un signalement de bogue"
        )
        self.bouton_copier.set_sensitive(False)
        self.bouton_copier.connect("clicked", self._copier)
        entete.pack_end(self.bouton_copier)
        self.set_titlebar(entete)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.add(self.stack)

        # --- Page « en cours » ---
        attente = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        attente.set_valign(Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        attente.pack_start(self.spinner, False, False, 0)
        message = Gtk.Label(label="Vérification en cours…")
        attente.pack_start(message, False, False, 0)
        self.stack.add_named(attente, "en-cours")

        # --- Page « résultat » ---
        self.resultat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.verdict = Gtk.Label()
        self.verdict.set_line_wrap(True)
        self.verdict.set_margin_top(16)
        self.verdict.set_margin_start(18)
        self.verdict.set_margin_end(18)
        self.resultat.pack_start(self.verdict, False, False, 0)

        defilement = Gtk.ScrolledWindow()
        defilement.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.liste = Gtk.ListBox()
        self.liste.set_selection_mode(Gtk.SelectionMode.NONE)
        self.liste.set_margin_top(12)
        self.liste.set_margin_start(18)
        self.liste.set_margin_end(18)
        self.liste.set_margin_bottom(18)
        defilement.add(self.liste)
        self.resultat.pack_start(defilement, True, True, 0)
        self.stack.add_named(self.resultat, "resultat")

        self.stack.show_all()
        self.stack.set_visible_child_name("en-cours")
        self.connect("key-press-event", self._touche)
        self.lancer()

    def lancer(self) -> None:
        self.spinner.start()
        self.stack.set_visible_child_name("en-cours")

        def travail():
            try:
                rapport = doctor.analyser()
            except Exception as exc:  # pragma: no cover - garde-fou
                rapport = exc
            GLib.idle_add(self._afficher, rapport)

        threading.Thread(target=travail, daemon=True).start()

    def _afficher(self, rapport) -> bool:
        self.spinner.stop()
        if isinstance(rapport, Exception):
            self.verdict.set_markup(
                f"<big><b>Le diagnostic a échoué</b></big>\n{GLib.markup_escape_text(str(rapport))}"
            )
            self.stack.set_visible_child_name("resultat")
            return False

        self.rapport = rapport
        self.bouton_copier.set_sensitive(True)

        if rapport.echecs:
            titre = "MultiWall n'est pas compatible avec cet environnement"
            detail = ("Les points marqués d'une croix empêchent l'application de "
                      "poser un fond d'écran.")
        elif rapport.avertissements:
            titre = "Devrait fonctionner, avec des réserves"
            detail = "Les points d'attention ci-dessous n'ont pas pu être garantis."
        else:
            titre = "Tout est en ordre"
            detail = "Votre environnement est pleinement supporté."
        self.verdict.set_markup(
            f"<big><b>{GLib.markup_escape_text(titre)}</b></big>\n"
            f"{GLib.markup_escape_text(detail)}"
        )

        for enfant in self.liste.get_children():
            self.liste.remove(enfant)
        for point in rapport.points:
            self.liste.add(self._ligne(point))
        self.liste.show_all()
        self.stack.set_visible_child_name("resultat")
        return False

    def _ligne(self, point) -> Gtk.ListBoxRow:
        ligne = Gtk.ListBoxRow()
        ligne.set_activatable(False)
        boite = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        boite.set_margin_top(6)
        boite.set_margin_bottom(6)
        boite.set_margin_start(6)
        boite.set_margin_end(6)

        icone = Gtk.Image.new_from_icon_name(self.ICONES[point.etat], Gtk.IconSize.BUTTON)
        icone.set_valign(Gtk.Align.START)
        boite.pack_start(icone, False, False, 0)

        texte = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        libelle = Gtk.Label()
        libelle.set_markup(
            f"<b>{GLib.markup_escape_text(point.libelle.strip())}</b>  "
            f"{GLib.markup_escape_text(point.valeur)}"
        )
        libelle.set_xalign(0.0)
        libelle.set_line_wrap(True)
        texte.pack_start(libelle, False, False, 0)
        if point.detail:
            detail = Gtk.Label(label=point.detail)
            detail.get_style_context().add_class("dim-label")
            detail.set_xalign(0.0)
            detail.set_line_wrap(True)
            texte.pack_start(detail, False, False, 0)
        boite.pack_start(texte, True, True, 0)
        ligne.add(boite)
        return ligne

    def _copier(self, _bouton) -> None:
        if self.rapport is None:
            return
        presse_papiers = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        presse_papiers.set_text(doctor.formater(self.rapport), -1)

    def _touche(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False


AIDE = """
<big><b>MultiWall</b></big>

Sous X11, vos écrans forment <b>un seul bureau</b> — ici {largeur}×{hauteur}. \
MultiWall compose donc une image unique à cette taille et l'installe en mode \
« étalé », ce qui la répartit pixel pour pixel sur l'ensemble des moniteurs.

<b>Les deux modes</b>

• <b>Une image par écran</b> — chaque image est collée à la position de son \
écran dans le grand canevas.
• <b>Image panoramique unique</b> — une seule image couvre tous les écrans. \
Résolution idéale : {largeur}×{hauteur}.

<b>Dans l'aperçu</b>

• <b>Clic</b> : sélectionner un écran · <b>double-clic</b> : choisir son image
• <b>Glisser-déposer</b> une image sur un écran ; en déposer plusieurs d'un coup \
les répartit sur les écrans suivants
• <b>Clic droit</b> : menu contextuel
• <b>← →</b> ou <b>1</b>–<b>9</b> : changer d'écran · <b>Suppr</b> : effacer

<b>Ajustement</b>

<b>Remplir</b> recadre pour couvrir l'écran · <b>Entier (bandes)</b> montre toute \
l'image · <b>Entier (fond flouté)</b> comble avec l'image floutée · <b>Étirer</b> \
déforme · <b>Taille réelle</b> centre sans redimensionner · <b>Mosaïque</b> répète.

<b>Bibliothèque</b>

Elle propose des fonds <b>au format de ce que vous habillez</b> : la résolution \
du bureau entier en mode panoramique, celle de l'écran sélectionné en mode \
« une image par écran » — et l'appliquer ne change jamais de mode.

<b>Double-cliquez</b> sur une vignette pour l'appliquer directement, ou \
sélectionnez-la puis utilisez le bouton.

Un seul bouton, trois onglets :

• <b>Fonds générés</b> — dix fonds panoramiques calculés localement, sans fichier \
ni connexion. Ils sont recalculés à la résolution de votre bureau et suivent donc \
un changement d'écrans.
• <b>Mes fonds</b> — les images que vous avez déjà utilisées au moins une fois, \
la plus récente en tête. « Utiliser » l'affecte à l'écran sélectionné, ou en fait \
le panorama si vous êtes en mode panoramique. « Oublier » la retire de la liste \
sans toucher au fichier ; une image déplacée ou supprimée disparaît d'elle-même.
• <b>Photos en ligne</b> — photos panoramiques de <b>Wikimedia Commons</b>, sous \
licence Creative Commons. Seules celles dont le format approche celui de votre \
bureau sont proposées ; licence et auteur sont affichés sous chaque vignette. Les \
images restent la propriété de leurs auteurs. Nécessite une connexion, et les \
recherches se font en anglais.

<b>Ligne de commande</b>

L'application s'utilise aussi depuis un terminal — pratique pour un raccourci \
clavier, un script ou une tâche planifiée.

<tt>multiwall</tt>                        ouvre cette fenêtre
<tt>multiwall list</tt>                   écrans détectés
<tt>multiwall set a.jpg b.jpg c.jpg</tt>  une image par écran, de gauche à droite
<tt>multiwall set DP-1=a.jpg</tt>         en ciblant une sortie par son nom
<tt>multiwall span pano.jpg</tt>          une image étalée sur tous les écrans
<tt>multiwall library</tt>                liste les fonds générés
<tt>multiwall library dunes</tt>          applique le fond « Dunes »
<tt>multiwall photos "coast"</tt>         cherche des photos panoramiques
<tt>multiwall photos "coast" --use 2</tt> applique la 2e de la liste
<tt>multiwall random ~/Images</tt>        tire au sort dans un dossier
<tt>multiwall apply</tt>                  réapplique la dernière configuration
<tt>multiwall export fond.png</tt>        enregistre le composite
<tt>multiwall doctor</tt>                 vérifie la compatibilité du système

Options utiles : <tt>--fit</tt> (cover, contain, blur, stretch, center, tile), \
<tt>--background '#101010'</tt>, et <tt>--span</tt> pour <tt>random</tt>.

<b>Changer de fond automatiquement</b>

<tt>systemd-run --user --on-calendar=hourly multiwall random ~/Images/Fonds</tt>

<b>Bon à savoir</b>

• Le branchement d'un écran est détecté automatiquement ; <b>F5</b> force la \
redétection.
• <b>Ctrl+D</b> vérifie que votre environnement de bureau est compatible. Le \
contrôle est aussi fait au démarrage, et ne s'affiche qu'en cas de problème.
• La configuration est enregistrée à la fermeture, même sans avoir appliqué.
• Le fond composé est écrit dans <tt>~/.local/share/multiwall/</tt> ; seuls les \
deux derniers sont conservés.
"""


class AideWindow(Gtk.Window):
    """Guide d'utilisation intégré : gestes de l'interface et commandes."""

    def __init__(self, parent, monitors):
        super().__init__(title="Guide d'utilisation")
        self.set_transient_for(parent)
        self.set_default_size(720, 640)

        entete = Gtk.HeaderBar(show_close_button=True, title="Guide d'utilisation")
        self.set_titlebar(entete)

        defilement = Gtk.ScrolledWindow()
        defilement.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        largeur, hauteur = core.desktop_size(monitors)
        texte = Gtk.Label()
        texte.set_markup(AIDE.format(largeur=largeur, hauteur=hauteur).strip())
        texte.set_line_wrap(True)
        texte.set_xalign(0.0)
        texte.set_selectable(True)  # pour copier une commande
        texte.set_margin_top(18)
        texte.set_margin_bottom(18)
        texte.set_margin_start(20)
        texte.set_margin_end(20)
        defilement.add(texte)
        self.add(defilement)

        self.connect("key-press-event", self._touche)

    def _touche(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False
