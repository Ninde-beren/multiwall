# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2026 Sigilbo
"""Interface graphique GTK3 de MultiWall.

L'écran principal est un aperçu à l'échelle de la disposition réelle des
moniteurs : on clique (ou on dépose une image) sur un écran pour lui affecter
un fond, puis « Appliquer ».
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import gi

# L'ordre compte : sans require_version explicite, `import Gdk` chargerait
# GTK4 et entrerait en conflit avec Gtk 3.0.
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("PangoCairo", "1.0")

from gi.repository import (  # noqa: E402
    Gdk,
    GdkPixbuf,
    Gio,
    GLib,
    Gtk,
    Pango,
    PangoCairo,
)
from PIL import Image, ImageOps  # noqa: E402

from . import ANNEE, AUTEUR, COPYRIGHT, LICENCE_NOM, LICENCE_RESUME  # noqa: E402
from . import LINKEDIN, __version__  # noqa: E402
from . import core, library, windows  # noqa: E402

#: Icône de l'application, embarquée avec le paquet.
LOGO = Path(__file__).parent / "data" / "logo.svg"


def charger_logo(taille: int):
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(str(LOGO), taille, taille)
    except (GLib.Error, OSError):
        return None  # icône absente : on retombera sur celle du thème

#: Description longue de chaque mode d'ajustement (tooltip du sélecteur).
FIT_TOOLTIPS = {
    "cover": "L'image remplit tout l'écran ; les bords qui dépassent sont recadrés.",
    "contain": "L'image est visible en entier ; des bandes de la couleur de fond "
               "complètent l'écran.",
    "blur": "L'image est visible en entier, sur un fond flouté tiré de l'image "
            "elle-même.",
    "stretch": "L'image est étirée aux dimensions de l'écran, sans respecter ses "
               "proportions.",
    "center": "L'image garde sa taille d'origine, centrée ; elle est recadrée si "
              "elle dépasse l'écran.",
    "tile": "L'image est répétée en damier jusqu'à couvrir l'écran.",
}

SHORTCUTS_XML = """
<interface>
  <object class="GtkShortcutsWindow" id="shortcuts">
    <property name="modal">1</property>
    <child>
      <object class="GtkShortcutsSection">
        <property name="visible">1</property>
        <property name="section-name">principal</property>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="visible">1</property>
            <property name="title">Images</property>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">&lt;Primary&gt;o</property>
                <property name="title">Choisir une image</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">&lt;Primary&gt;r</property>
                <property name="title">Nouveau tirage aléatoire</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">Delete</property>
                <property name="title">Effacer l'image de l'écran</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">&lt;Primary&gt;e</property>
                <property name="title">Exporter le composite</property>
              </object>
            </child>
          </object>
        </child>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="visible">1</property>
            <property name="title">Aperçu</property>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">Left Right</property>
                <property name="title">Écran précédent / suivant</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">1...9</property>
                <property name="title">Sélectionner un écran par son rang</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">Return</property>
                <property name="title">Choisir l'image de l'écran sélectionné</property>
              </object>
            </child>
          </object>
        </child>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="visible">1</property>
            <property name="title">Général</property>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">&lt;Primary&gt;Return</property>
                <property name="title">Appliquer le fond d'écran</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">&lt;Primary&gt;1 &lt;Primary&gt;2</property>
                <property name="title">Mode par écran / panoramique</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">F5</property>
                <property name="title">Redétecter les écrans</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="visible">1</property>
                <property name="accelerator">&lt;Primary&gt;w</property>
                <property name="title">Fermer</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
  </object>
</interface>
"""


def pil_to_pixbuf(img: Image.Image) -> GdkPixbuf.Pixbuf:
    data = GLib.Bytes.new(img.tobytes())
    return GdkPixbuf.Pixbuf.new_from_bytes(
        data, GdkPixbuf.Colorspace.RGB, False, 8, img.width, img.height, img.width * 3
    )


class MultiWallWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="MultiWall")

        self.cfg = core.Config.load()
        self.monitors = core.detect_monitors()
        self.selected: str | None = self.monitors[0].name if self.monitors else None

        self._preview_cache: tuple | None = None
        self._thumbs: dict = {}
        self._thumb_box = (320, 200)
        self._hover: str | None = None
        self._drop_target: str | None = None
        self._dragging = False
        self._applying = False
        self._dirty = False
        self._toast_id = 0
        self._sync_mode = False
        self._redetect_id = 0

        # Hauteur calée sur le contenu : en-tête + aperçu au ratio du bureau
        # + texte d'aide + barre d'actions, sans réserve superflue.
        dw, dh = core.desktop_size(self.monitors)
        self.set_default_size(1040, max(360, round(1004 * dh / dw) + 150))

        self._build_actions(app)
        self._build_header()
        self._build_body()
        self.connect("delete-event", self._on_close)
        self._brancher_detection_auto()
        self.refresh(initial=True)
        # Après l'affichage de la fenêtre, pour ne pas retarder son ouverture.
        GLib.timeout_add(400, self._verifier_compatibilite)

    # ------------------------------------------------------------ Actions --
    def _build_actions(self, app: Gtk.Application) -> None:
        actions = (
            ("choose", self.on_choose, ["<Primary>o"]),
            ("apply", self.on_apply, ["<Primary>Return", "<Primary>s"]),
            ("clear", self.on_clear, ["Delete"]),
            ("random", self.on_random, []),
            ("reroll", self.on_reroll, ["<Primary>r"]),
            ("library", self.on_library, ["<Primary>l"]),
            ("photos", self.on_photos, ["<Primary>p"]),
            ("aide", self.on_aide, ["F1"]),
            ("diagnostic", self.on_diagnostic, ["<Primary>d"]),
            ("export", self.on_export, ["<Primary>e"]),
            ("redetect", self.on_redetect, ["F5"]),
            ("reset", self.on_reset, []),
            ("shortcuts", self.on_shortcuts, ["<Primary>question"]),
            ("about", self.on_about, []),
            ("close", lambda *_: self.close(), ["<Primary>w", "<Primary>q"]),
        )
        self._actions = {}
        for name, callback, accels in actions:
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda a, p, cb=callback: cb(None))
            self.add_action(act)
            self._actions[name] = act
            if accels:
                app.set_accels_for_action(f"win.{name}", accels)

        mode = Gio.SimpleAction.new_stateful(
            "mode", GLib.VariantType.new("s"), GLib.Variant.new_string(self.cfg.mode)
        )
        mode.connect("change-state", self.on_mode_action)
        self.add_action(mode)
        self._mode_action = mode
        app.set_accels_for_action("win.mode('per-monitor')", ["<Primary>1"])
        app.set_accels_for_action("win.mode('span')", ["<Primary>2"])

    # ----------------------------------------------------------------- UI --
    def _build_header(self) -> None:
        hb = Gtk.HeaderBar(show_close_button=True)
        self.headerbar = hb

        pixbuf = charger_logo(24)
        self.logo = (Gtk.Image.new_from_pixbuf(pixbuf) if pixbuf else
                     Gtk.Image.new_from_icon_name("preferences-desktop-wallpaper",
                                                  Gtk.IconSize.LARGE_TOOLBAR))
        self.logo.set_margin_end(6)
        self.logo.set_tooltip_text("MultiWall")
        hb.pack_start(self.logo)

        # Sélecteur de mode en titre : il gouverne toute la fenêtre, et cela
        # libère une bande de hauteur précieuse pour un bureau très large.
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        for style in ("linked", "stack-switcher"):
            mode_box.get_style_context().add_class(style)
        first = None
        self.mode_buttons: dict[str, Gtk.RadioButton] = {}
        for value, label in (
            ("per-monitor", "_Une image par écran"),
            ("span", "Image _panoramique unique"),
        ):
            btn = Gtk.RadioButton.new_with_mnemonic_from_widget(first, label)
            first = first or btn
            btn.set_mode(False)
            btn.connect("toggled", self._on_mode_toggled, value)
            mode_box.pack_start(btn, False, False, 0)
            self.mode_buttons[value] = btn
        self._sync_mode = True
        self.mode_buttons[self.cfg.mode].set_active(True)
        self._sync_mode = False
        w, h = core.desktop_size(self.monitors)
        mode_box.set_tooltip_text(f"{len(self.monitors)} écran(s) · bureau {w}×{h}")
        hb.set_custom_title(mode_box)

        menu_btn = Gtk.MenuButton()
        menu_btn.add(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        menu_btn.set_tooltip_text("Menu principal")
        menu_btn.get_accessible().set_name("Menu principal")
        menu_btn.set_menu_model(self._build_menu())
        hb.pack_end(menu_btn)

        # Le bouton laisse place à un spinner pendant la composition.
        self.apply_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.apply_btn = Gtk.Button(label="Appliquer")
        self.apply_btn.get_style_context().add_class("suggested-action")
        self.apply_btn.set_action_name("win.apply")
        self.apply_btn.set_tooltip_text("Composer et installer le fond d'écran (Ctrl+Entrée)")
        spinner_box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner()
        spinner_box.pack_start(self.spinner, False, False, 0)
        self.apply_stack.add_named(self.apply_btn, "idle")
        self.apply_stack.add_named(spinner_box, "busy")
        self.apply_stack.show_all()  # sinon le Stack n'a aucun enfant visible
        self.apply_stack.set_visible_child_name("idle")
        hb.pack_end(self.apply_stack)

        self.set_titlebar(hb)

    def _build_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("Choisir une image…", "win.choose")
        section.append("Aléatoire depuis un dossier…", "win.random")
        section.append("Bibliothèque…", "win.library")
        section.append("Nouveau tirage", "win.reroll")
        section.append("Effacer", "win.clear")
        menu.append_section(None, section)

        section = Gio.Menu()
        section.append("Exporter le composite…", "win.export")
        section.append("Redétecter les écrans", "win.redetect")
        section.append("Réinitialiser…", "win.reset")
        menu.append_section(None, section)

        section = Gio.Menu()
        section.append("Guide d'utilisation", "win.aide")
        section.append("Vérifier la compatibilité…", "win.diagnostic")
        section.append("Raccourcis clavier", "win.shortcuts")
        section.append("À propos de MultiWall", "win.about")
        menu.append_section(None, section)
        return menu

    def _build_body(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        self.area = Gtk.DrawingArea()
        self.area.set_can_focus(True)
        self.area.connect("draw", self.on_draw)
        self.area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.area.connect("button-press-event", self.on_click)
        self.area.connect("key-press-event", self.on_area_key)
        self.area.connect("motion-notify-event", self.on_motion)
        self.area.connect("leave-notify-event", self.on_leave)
        self.area.drag_dest_set(
            Gtk.DestDefaults.ALL, [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY
        )
        self.area.connect("drag-data-received", self.on_drop)
        self.area.connect("drag-motion", self.on_drag_motion)
        self.area.connect("drag-leave", self.on_drag_leave)

        dw, dh = core.desktop_size(self.monitors)
        # yalign=0 : l'aperçu reste ancré en haut. Centré, il se déplacerait
        # verticalement selon que le texte d'aide est affiché ou non.
        self.frame = Gtk.AspectFrame(xalign=0.5, yalign=0.0, ratio=dw / dh, obey_child=False)
        self.frame.set_shadow_type(Gtk.ShadowType.NONE)
        self.frame.set_margin_start(18)
        self.frame.set_margin_end(18)
        self.frame.set_margin_top(12)
        self._hauteur_apercu = 0
        self.area.set_size_request(360, max(round(360 * dh / dw), 60))
        self.frame.add(self.area)
        self.connect("size-allocate", self._ajuster_hauteur_apercu)

        # Superposition pour les messages transitoires (toasts).
        overlay = Gtk.Overlay()
        overlay.add(self.frame)
        self._toast_label = Gtk.Label(margin_top=10, margin_bottom=10,
                                      margin_start=18, margin_end=18)
        toast_frame = Gtk.Frame(shadow_type=Gtk.ShadowType.NONE)
        toast_frame.get_style_context().add_class("osd")
        toast_frame.add(self._toast_label)
        self._toast_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            halign=Gtk.Align.CENTER, valign=Gtk.Align.START, margin_top=12,
        )
        self._toast_revealer.add(toast_frame)
        overlay.add_overlay(self._toast_revealer)
        overlay.set_overlay_pass_through(self._toast_revealer, True)
        root.pack_start(overlay, False, False, 0)

        self.hint = Gtk.Label()
        self.hint.set_margin_top(2)
        self.hint.set_margin_bottom(2)
        self.hint.set_margin_start(18)
        self.hint.set_margin_end(18)
        self.hint.set_line_wrap(True)
        self.hint.set_valign(Gtk.Align.CENTER)
        self.hint.show()  # toujours affiché : sa disparition décalait la mise en page
        # Le texte d'aide occupe seul l'espace entre l'aperçu (hauteur fixe) et la
        # barre d'actions, et s'y centre verticalement.
        root.pack_start(self.hint, True, True, 0)

        # Barre d'actions : à gauche ce qui concerne l'écran sélectionné,
        # à droite ce qui est global.
        bar = Gtk.ActionBar()

        self.choose_btn = Gtk.Button(label="Choisir une image…")
        self.choose_btn.set_action_name("win.choose")
        bar.pack_start(self.choose_btn)

        self.library_btn = Gtk.Button(label="Bibliothèque…")
        self.library_btn.set_action_name("win.library")
        self.library_btn.set_tooltip_text(
            "Fonds générés et photos en ligne, au format de votre bureau (Ctrl+L)"
        )
        bar.pack_start(self.library_btn)

        fit_label = Gtk.Label(label="Ajustement")
        fit_label.get_style_context().add_class("dim-label")
        bar.pack_start(fit_label)

        self.fit_combo = Gtk.ComboBoxText()
        for mode in core.FIT_MODES:
            self.fit_combo.append(mode, core.FIT_LABELS[mode])
        self.fit_combo.connect("changed", self.on_fit_changed)
        bar.pack_start(self.fit_combo)

        self.clear_btn = Gtk.Button(label="Effacer")
        self.clear_btn.set_action_name("win.clear")
        bar.pack_start(self.clear_btn)

        self.status = Gtk.Label(xalign=0.0)
        self.status.get_style_context().add_class("dim-label")
        self.status.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.status.set_max_width_chars(34)
        bar.pack_start(self.status)

        self.color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.parse(self.cfg.background)
        self.color_btn.set_rgba(rgba)
        self.color_btn.connect("color-set", self.on_color)
        bar.pack_end(self.color_btn)
        color_label = Gtk.Label(label="Fond")
        color_label.get_style_context().add_class("dim-label")
        bar.pack_end(color_label)

        root.pack_end(bar, False, False, 0)

    def _ajuster_hauteur_apercu(self, _widget, alloc) -> None:
        """Donne à l'aperçu exactement la hauteur qu'impose sa largeur.

        Sans cela, il faudrait lui laisser toute la place disponible, et le
        texte d'aide hériterait d'une zone démesurée.
        """
        dw, dh = core.desktop_size(self.monitors)
        if not dw or not dh:
            return
        largeur = max(alloc.width - 36, 1)  # marges gauche + droite du cadre
        hauteur = max(round(largeur * dh / dw), 60)
        if hauteur != self._hauteur_apercu:
            self._hauteur_apercu = hauteur
            self.frame.set_size_request(-1, hauteur)

    # ------------------------------------------------------------- Données --
    @property
    def is_span(self) -> bool:
        return self.cfg.mode == "span"

    def current_conf(self) -> dict:
        """Configuration de la cible courante (écran sélectionné, ou panorama).

        L'entrée est créée à la volée : `Config.save` élague ensuite celles qui
        n'ont pas d'image, pour qu'un simple clic ne laisse pas de trace.
        """
        if self.is_span:
            return self.cfg.span
        if self.selected is None:
            return {}
        return self.cfg.monitors.setdefault(self.selected, {"path": "", "fit": "cover"})

    def refresh(self, initial: bool = False) -> None:
        conf = self.current_conf()
        a_une_image = bool(conf.get("path"))

        self.fit_combo.handler_block_by_func(self.on_fit_changed)
        self.fit_combo.set_active_id(conf.get("fit", "cover"))
        self.fit_combo.handler_unblock_by_func(self.on_fit_changed)
        self.fit_combo.set_sensitive(a_une_image)
        self.fit_combo.set_tooltip_text(
            FIT_TOOLTIPS.get(conf.get("fit", "cover"), "")
            + ("\nS'applique à l'image panoramique." if self.is_span
               else f"\nS'applique à l'écran {self.selected}.")
        )
        self._actions["clear"].set_enabled(a_une_image)
        self.clear_btn.set_sensitive(a_une_image)

        w, h = core.desktop_size(self.monitors)
        # La consigne « déposez / double-cliquez » est portée UNIQUEMENT par
        # l'aperçu : la répéter ici ferait lire deux fois la même chose.
        if self.is_span:
            self.choose_btn.set_label("Choisir l'image panoramique…")
            if self.cfg.span.get("library"):
                aide = (f"Fond généré « {library.get(self.cfg.span['library']).nom} » · "
                        f"recalculé en {w}×{h}")
            elif self.cfg.span.get("path"):
                aide = (f"Image étalée sur les {len(self.monitors)} écrans · "
                        f"résolution idéale {w}×{h}")
            else:
                aide = ("Déposez une image panoramique sur l'aperçu, ou double-cliquez "
                        f"· résolution idéale {w}×{h}")
        else:
            self.choose_btn.set_label("Choisir une image…")
            if a_une_image:
                aide = ("Double-cliquez pour remplacer · "
                        f"Suppr effacer · ← → changer d'écran")
            else:
                aide = ("Déposez une image ou double-cliquez "
                        f"· ← → changer d'écran")
        self.hint.set_text(aide)

        path = conf.get("path") or ""
        self.status.set_text(os.path.basename(path) if path else "")
        self.status.set_tooltip_text(path or None)

        self.area.get_accessible().set_name(
            "Aperçu du bureau, image panoramique unique" if self.is_span
            else f"Aperçu du bureau, écran {self.selected} sélectionné, "
                 f"{os.path.basename(path) if path else 'aucune image'}"
        )

        self._set_dirty(not initial)
        self._preview_cache = None
        self.area.queue_draw()

    def _set_dirty(self, dirty: bool) -> None:
        """Le bouton Appliquer n'est actif que s'il y a réellement quelque chose à poser."""
        self._dirty = dirty
        actionnable = dirty and self.cfg.has_image() and not self._applying
        self.apply_btn.set_sensitive(actionnable)
        self._actions["apply"].set_enabled(actionnable)
        style = self.apply_btn.get_style_context()
        (style.add_class if actionnable else style.remove_class)("suggested-action")

    def _toast(self, texte: str, secondes: int = 4) -> None:
        self._toast_label.set_text(texte)
        self._toast_revealer.set_reveal_child(True)
        if self._toast_id:
            GLib.source_remove(self._toast_id)
        self._toast_id = GLib.timeout_add_seconds(secondes, self._hide_toast)

    def _hide_toast(self) -> bool:
        self._toast_revealer.set_reveal_child(False)
        self._toast_id = 0
        return False

    # -------------------------------------------------------- Vignettes ----
    def _thumb(self, path) -> Image.Image:
        """Ouvre une version réduite et mise en cache — l'aperçu n'a pas besoin
        de décoder un JPEG de 24 Mpx pour en afficher 300 px de large."""
        path = str(path)
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            mtime = 0
        cible = (self._thumb_box[0] * 2, self._thumb_box[1] * 2)
        cle = (path, mtime, cible)
        cached = self._thumbs.get(cle)
        if cached is not None:
            return cached

        img = Image.open(path)
        img.draft("RGB", cible)  # décodage JPEG accéléré (1/2, 1/4, 1/8)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        img = img.convert("RGB")
        img.thumbnail(cible, Image.BICUBIC)

        if len(self._thumbs) > 12:
            self._thumbs.clear()
        self._thumbs[cle] = img
        return img

    def _preview(self, width: int, height: int):
        """Compose un aperçu à l'échelle de la zone de dessin (avec cache)."""
        dw, dh = core.desktop_size(self.monitors)
        scale = min(width / dw, height / dh, 1.0) if dw and dh else 1.0
        key = (
            scale,
            self.cfg.mode,
            self.cfg.background,
            repr(self.cfg.span),
            repr(sorted(self.cfg.monitors.items())),
        )
        if self._preview_cache and self._preview_cache[0] == key:
            return self._preview_cache[1], scale

        mons = core.scaled_monitors(self.monitors, scale)
        self._thumb_box = (
            max((m.width for m in mons), default=320),
            max((m.height for m in mons), default=200),
        )
        try:
            if self.is_span:
                if self.cfg.span.get("library"):
                    img = library.rendu(
                        self.cfg.span["library"], core.desktop_size(mons), mons
                    )
                elif self.cfg.span.get("path"):
                    img = core.compose_span(
                        mons, self.cfg.span["path"], self.cfg.span.get("fit", "cover"),
                        self.cfg.background, opener=self._thumb,
                    )
                else:
                    # Sans image panoramique, montrer un bureau vide — surtout pas
                    # les fonds par écran, qui ne seront pas ceux appliqués.
                    img = Image.new(
                        "RGB", core.desktop_size(mons), core.hex_to_rgb(self.cfg.background)
                    )
            else:
                img = core.compose_per_monitor(
                    mons, self.cfg.monitors, self.cfg.background, opener=self._thumb
                )
        except Exception:
            # Un aperçu ne doit jamais faire tomber la fenêtre (image corrompue,
            # bombe de décompression, format exotique…).
            img = None

        pixbuf = pil_to_pixbuf(img) if img else None
        self._preview_cache = (key, pixbuf)
        return pixbuf, scale

    # --------------------------------------------------------- Géométrie ---
    def _layout(self) -> tuple[float, float, float]:
        """Échelle et décalage de l'aperçu — source unique pour le dessin ET
        pour la détection du clic, qui doivent rester d'accord."""
        alloc = self.area.get_allocation()
        dw, dh = core.desktop_size(self.monitors)
        if not dw or not dh:
            return 1.0, 0.0, 0.0
        scale = min(alloc.width / dw, alloc.height / dh, 1.0)
        return scale, (alloc.width - dw * scale) / 2, (alloc.height - dh * scale) / 2

    def _monitor_at(self, px: float, py: float) -> str | None:
        scale, ox, oy = self._layout()
        for mon in self.monitors:
            if (ox + mon.x * scale <= px <= ox + (mon.x + mon.width) * scale
                    and oy + mon.y * scale <= py <= oy + (mon.y + mon.height) * scale):
                return mon.name
        return None

    # ------------------------------------------------------------ Dessin ---
    def _pango(self, cr, texte: str, echelle: float = 1.0):
        """Texte via Pango : respecte la police système et le facteur HiDPI."""
        layout = PangoCairo.create_layout(cr)
        nom = Gtk.Settings.get_default().get_property("gtk-font-name")
        desc = Pango.FontDescription.from_string(nom or "Sans 10")
        desc.set_size(max(round(desc.get_size() * echelle), Pango.SCALE * 6))
        layout.set_font_description(desc)
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_text(texte, -1)
        return layout

    def _couleur_theme(self, sc, *noms, defaut=(1, 1, 1, 1)) -> Gdk.RGBA:
        for nom in noms:
            ok, couleur = sc.lookup_color(nom)
            if ok:
                return couleur
        return Gdk.RGBA(*defaut)

    def on_draw(self, area: Gtk.DrawingArea, cr) -> None:
        sc = area.get_style_context()
        scale, ox, oy = self._layout()
        alloc = area.get_allocation()
        pixbuf, _ = self._preview(alloc.width, alloc.height)

        if pixbuf:
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, ox, oy)
            cr.paint()

        accent = self._couleur_theme(
            sc, "theme_selected_bg_color", "accent_bg_color", defaut=(0.30, 0.62, 1.0, 1.0)
        )

        if self.is_span and not self.cfg.span.get("path"):
            dw, dh = core.desktop_size(self.monitors)
            self._dessiner_etat_vide(cr, sc, ox, oy, dw * scale, dh * scale)

        for mon in self.monitors:
            x = ox + mon.x * scale
            y = oy + mon.y * scale
            w = mon.width * scale
            h = mon.height * scale

            conf = self.cfg.monitors.get(mon.name, {})
            vide = not self.is_span and not conf.get("path")

            if vide:
                self._dessiner_etat_vide(cr, sc, x, y, w, h)

            if self._hover == mon.name and not self._dragging:
                cr.set_source_rgba(1, 1, 1, 0.06)
                cr.rectangle(x, y, w, h)
                cr.fill()

            cible_drop = self._dragging and (self.is_span or self._drop_target == mon.name)
            if cible_drop:
                Gdk.cairo_set_source_rgba(
                    cr, Gdk.RGBA(accent.red, accent.green, accent.blue, 0.25)
                )
                cr.rectangle(x, y, w, h)
                cr.fill()

            # Double trait sombre/clair : reste lisible sur une image claire
            # comme sur une image sombre.
            cr.set_line_width(1)
            cr.set_source_rgba(0, 0, 0, 0.55)
            cr.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
            cr.stroke()
            cr.set_source_rgba(1, 1, 1, 0.85)
            cr.rectangle(x + 1.5, y + 1.5, w - 3, h - 3)
            cr.stroke()

            selectionne = (not self.is_span) and mon.name == self.selected
            if selectionne or cible_drop:
                Gdk.cairo_set_source_rgba(cr, accent)
                cr.set_line_width(3)
                cr.rectangle(x + 2, y + 2, w - 4, h - 4)
                cr.stroke()
            if selectionne and area.has_focus():
                Gtk.render_focus(sc, cr, x + 6, y + 6, w - 12, h - 12)

            self._dessiner_etiquette(cr, mon, conf, x, y, w)

    def _dessiner_etat_vide(self, cr, sc, x, y, w, h) -> None:
        """Marque une zone sans image. Sans texte : la consigne est donnée une
        seule fois sous l'aperçu, pas répétée dans chaque écran."""
        # Voile sombre plutôt qu'un gris de thème : le texte blanc doit rester
        # lisible quelle que soit la couleur de fond choisie.
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.rectangle(x, y, w, h)
        cr.fill()

        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.set_dash([6, 5])
        cr.set_line_width(2)
        cr.rectangle(x + 10, y + 10, max(w - 20, 1), max(h - 20, 1))
        cr.stroke()
        cr.set_dash([])

    def _dessiner_etiquette(self, cr, mon, conf, x, y, w) -> None:
        texte = f"{mon.name}  {mon.width}×{mon.height}"
        if not self.is_span and conf.get("fit") and conf.get("path"):
            texte += f"  ·  {core.FIT_LABELS.get(conf['fit'], '')}"
        layout = self._pango(cr, texte, 0.9)
        tw, th = layout.get_pixel_size()
        if tw + 28 > w:
            layout = self._pango(cr, mon.name, 0.9)
            tw, th = layout.get_pixel_size()
        cr.set_source_rgba(0, 0, 0, 0.65)
        cr.rectangle(x + 8, y + 8, tw + 14, th + 10)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(x + 15, y + 13)
        PangoCairo.show_layout(cr, layout)

    # --------------------------------------------------------- Callbacks ---
    def on_click(self, area, event) -> None:
        area.grab_focus()
        double = event.type == Gdk.EventType._2BUTTON_PRESS

        if event.button == 3:  # clic droit : menu contextuel
            nom = self._monitor_at(event.x, event.y)
            if nom and not self.is_span:
                self.selected = nom
                self.refresh()
            menu = Gtk.Menu.new_from_model(self._build_menu())
            menu.attach_to_widget(self)
            menu.popup_at_pointer(event)
            return

        if self.is_span:
            if double:
                self.on_choose(None)
            return

        nom = self._monitor_at(event.x, event.y)
        if nom:
            self.selected = nom
            self.refresh()
            if double:
                self.on_choose(None)

    def on_area_key(self, _area, event) -> bool:
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.on_choose(None)
            return True
        if self.is_span:
            return False

        noms = [m.name for m in self.monitors]
        if not noms:
            return False
        i = noms.index(self.selected) if self.selected in noms else 0

        if event.keyval in (Gdk.KEY_Left, Gdk.KEY_Up):
            self.selected = noms[max(i - 1, 0)]
        elif event.keyval in (Gdk.KEY_Right, Gdk.KEY_Down):
            self.selected = noms[min(i + 1, len(noms) - 1)]
        elif event.keyval in (Gdk.KEY_Home,):
            self.selected = noms[0]
        elif event.keyval in (Gdk.KEY_End,):
            self.selected = noms[-1]
        elif Gdk.KEY_1 <= event.keyval <= Gdk.KEY_9:
            rang = event.keyval - Gdk.KEY_1
            if rang >= len(noms):
                return False
            self.selected = noms[rang]
        else:
            return False
        self.refresh()
        return True

    def on_motion(self, area, event) -> bool:
        nom = None if self.is_span else self._monitor_at(event.x, event.y)
        survol = self.is_span or nom is not None
        window = area.get_window()
        if window:
            window.set_cursor(
                Gdk.Cursor.new_from_name(self.get_display(), "pointer") if survol else None
            )
        if nom != self._hover:
            self._hover = nom
            area.queue_draw()
        return False

    def on_leave(self, area, _event) -> bool:
        if self._hover is not None:
            self._hover = None
            area.queue_draw()
        return False

    def on_drag_motion(self, area, _ctx, x, y, _time) -> bool:
        self._dragging = True
        self._drop_target = None if self.is_span else self._monitor_at(x, y)
        area.queue_draw()
        return False

    def on_drag_leave(self, area, _ctx, _time) -> None:
        self._dragging = False
        self._drop_target = None
        area.queue_draw()

    def on_drop(self, _widget, _ctx, x, y, data, _info, _time) -> None:
        self._dragging = False
        self._drop_target = None
        uris = data.get_uris()
        if not uris:
            self.area.queue_draw()
            return
        chemins = [f for f in (Gio.File.new_for_uri(u).get_path() for u in uris) if f]
        if not chemins:
            self._toast("Seuls les fichiers locaux peuvent être déposés")
            self.area.queue_draw()
            return

        for chemin in chemins:
            self.cfg.noter_image(chemin)
        if self.is_span:
            self.cfg.span["path"] = chemins[0]
            self.cfg.span["library"] = ""
        else:
            cible = self._monitor_at(x, y) or self.selected
            noms = [m.name for m in self.monitors]
            if cible in noms:
                self.selected = cible
                depart = noms.index(cible)
                for i, chemin in enumerate(chemins):
                    if depart + i < len(noms):
                        conf = self.cfg.monitors.setdefault(
                            noms[depart + i], {"path": "", "fit": "cover"}
                        )
                        conf["path"] = chemin
        self.refresh()

    def _on_mode_toggled(self, bouton, valeur: str) -> None:
        """Clic sur un bouton de mode."""
        if self._sync_mode or not bouton.get_active():
            return
        self._appliquer_mode(valeur)

    def on_mode_action(self, _action, value) -> None:
        """Raccourci Ctrl+1 / Ctrl+2."""
        self._appliquer_mode(value.get_string())

    def _appliquer_mode(self, valeur: str) -> None:
        """Point d'entrée unique : synchronise config, action et boutons.

        Le garde `_sync_mode` empêche l'aller-retour bouton → action → bouton.
        """
        if self._sync_mode:
            return
        self._sync_mode = True
        try:
            self.cfg.mode = valeur
            self._mode_action.set_state(GLib.Variant.new_string(valeur))
            bouton = self.mode_buttons.get(valeur)
            if bouton is not None and not bouton.get_active():
                bouton.set_active(True)
        finally:
            self._sync_mode = False
        self.refresh()

    def on_fit_changed(self, combo) -> None:
        fit = combo.get_active_id()
        if fit:
            self.current_conf()["fit"] = fit
            self.refresh()

    def on_color(self, btn) -> None:
        rgba = btn.get_rgba()
        self.cfg.background = "#%02x%02x%02x" % (
            round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)
        )
        self.refresh()

    def on_clear(self, _btn) -> None:
        self.current_conf()["path"] = ""
        self.refresh()

    # ------------------------------------------------------------ Fichiers --
    def _dossier_initial(self) -> str:
        return (
            self.cfg.last_folder
            or GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
            or GLib.get_home_dir()
        )

    def _ajouter_apercu(self, dialog: Gtk.FileChooserDialog) -> None:
        image = Gtk.Image()
        dialog.set_preview_widget(image)
        dialog.set_use_preview_label(False)

        def maj(chooser):
            nom = chooser.get_preview_filename()
            pixbuf = None
            if nom and os.path.isfile(nom):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(nom, 256, 256)
                except GLib.Error:
                    pixbuf = None
            image.set_from_pixbuf(pixbuf)
            chooser.set_preview_widget_active(pixbuf is not None)

        dialog.connect("update-preview", maj)

    def on_choose(self, _btn) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Choisir une image", parent=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons("Annuler", Gtk.ResponseType.CANCEL, "Ouvrir", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_select_multiple(not self.is_span)
        dialog.set_local_only(True)
        dialog.set_current_folder(self._dossier_initial())
        self._ajouter_apercu(dialog)

        images = Gtk.FileFilter()
        images.set_name("Images")
        images.add_pixbuf_formats()
        for ext in core.IMAGE_EXTS:  # formats que Pillow lit mais pas GdkPixbuf
            images.add_pattern(f"*{ext}")
            images.add_pattern(f"*{ext.upper()}")
        dialog.add_filter(images)
        tous = Gtk.FileFilter()
        tous.set_name("Tous les fichiers")
        tous.add_pattern("*")
        dialog.add_filter(tous)

        if dialog.run() == Gtk.ResponseType.OK:
            fichiers = dialog.get_filenames()
            self.cfg.last_folder = dialog.get_current_folder() or ""
            if self.is_span:
                self.cfg.span["path"] = fichiers[0]
                self.cfg.span["library"] = ""
            else:
                noms = [m.name for m in self.monitors]
                depart = noms.index(self.selected) if self.selected in noms else 0
                for i, fichier in enumerate(fichiers):
                    if depart + i < len(noms):
                        conf = self.cfg.monitors.setdefault(
                            noms[depart + i], {"path": "", "fit": "cover"}
                        )
                        conf["path"] = fichier
            for fichier in fichiers:
                self.cfg.noter_image(fichier)
            self.refresh()
        dialog.destroy()

    def on_random(self, _item) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Dossier d'images", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons("Annuler", Gtk.ResponseType.CANCEL, "Choisir", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_current_folder(self.cfg.last_random_folder or self._dossier_initial())
        dossier = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        dialog.destroy()
        if dossier:
            self.cfg.last_random_folder = dossier
            self._tirer_au_sort(dossier)

    def on_reroll(self, _item) -> None:
        """Nouveau tirage dans le dernier dossier utilisé, sans repasser par le dialogue."""
        if self.cfg.last_random_folder:
            self._tirer_au_sort(self.cfg.last_random_folder)
        else:
            self.on_random(None)

    def _tirer_au_sort(self, dossier: str) -> None:
        import random

        images = core.list_images(dossier)
        if not images:
            self._error("Aucune image dans ce dossier.", dossier)
            return
        if self.is_span:
            tiree = str(random.choice(images))
            self.cfg.span["path"] = tiree
            self.cfg.span["library"] = ""
            self.cfg.noter_image(tiree)
        else:
            pool = (random.sample(images, len(self.monitors))
                    if len(images) >= len(self.monitors)
                    else [random.choice(images) for _ in self.monitors])
            for mon, image in zip(self.monitors, pool):
                conf = self.cfg.monitors.setdefault(mon.name, {"path": "", "fit": "cover"})
                conf["path"] = str(image)
                self.cfg.noter_image(image)
        self.refresh()
        self._toast("Nouveau tirage — Ctrl+R pour en relancer un")

    def on_library(self, _item, onglet: str = "generes") -> None:
        windows.BibliothequeWindow(
            self, self.monitors, self._choisir_fond, self._photo_choisie, onglet,
            cfg=self.cfg, on_fichier=self._fichier_choisi,
        ).show_all()

    def _fichier_choisi(self, chemin: str) -> None:
        """Applique une image de l'historique à la cible courante.

        En mode panoramique elle devient le fond unique ; sinon elle est
        affectée à l'écran sélectionné — c'est ce que l'utilisateur voit.
        """
        if self.is_span:
            self.cfg.span = {"path": chemin, "fit": "cover", "library": ""}
        else:
            conf = self.current_conf()
            conf["path"] = chemin
        self.cfg.noter_image(chemin)
        self.refresh()

    def _choisir_fond(self, identifiant: str) -> None:
        self.cfg.span = {"path": "", "fit": "cover", "library": identifiant}
        self._appliquer_mode("span")
        self._toast(f"« {library.get(identifiant).nom} » — cliquez sur Appliquer")

    def on_photos(self, _item) -> None:
        """Même fenêtre, ouverte directement sur l'onglet en ligne."""
        self.on_library(None, onglet="en-ligne")

    def _photo_choisie(self, chemin: str, photo) -> None:
        self.cfg.span = {"path": chemin, "fit": "cover", "library": ""}
        self.cfg.noter_image(chemin)
        self._appliquer_mode("span")
        self._toast(f"« {photo.nom[:36]} » — {photo.licence}")

    def on_aide(self, _item) -> None:
        windows.AideWindow(self, self.monitors).show_all()

    def on_diagnostic(self, _item) -> None:
        windows.DiagnosticWindow(self).show_all()

    def _verifier_compatibilite(self) -> bool:
        """Au premier plan, ouvre le diagnostic si l'environnement est inutilisable.

        Sans cela, l'utilisateur d'un bureau non supporté découvrirait le
        problème en constatant que « Appliquer » ne fait rien.
        """
        from . import doctor

        try:
            if not doctor.analyser().utilisable:
                windows.DiagnosticWindow(self).show_all()
        except Exception:
            pass  # le diagnostic ne doit jamais empêcher l'application de démarrer
        return False

    def on_export(self, _item) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Exporter le composite", parent=self, action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons("Annuler", Gtk.ResponseType.CANCEL, "Enregistrer", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_folder(self._dossier_initial())
        w, h = core.desktop_size(self.monitors)
        dialog.set_current_name(f"wallpaper-{w}x{h}.png")
        destination = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        dialog.destroy()
        if not destination:
            return
        try:
            self.cfg.compose(self.monitors).save(destination)
            self._toast("Composite exporté")
            self.status.set_tooltip_text(destination)
        except Exception as exc:
            self._error("Impossible d'exporter le composite.", str(exc))

    def on_redetect(self, _item) -> None:
        detectes = core.detect_monitors()
        if not detectes:
            # xrandr peut échouer transitoirement pendant un branchement :
            # mieux vaut garder l'ancienne disposition que se retrouver sans écran.
            self._error(
                "Aucun écran détecté.",
                "La disposition précédente est conservée. Réessayez dans un instant.",
            )
            return
        self._appliquer_detection(detectes)

    def _appliquer_detection(self, detectes: list) -> None:
        """Reprend une nouvelle disposition d'écrans : géométrie, aperçu, textes."""
        self.monitors = detectes
        if self.selected not in [m.name for m in self.monitors]:
            self.selected = self.monitors[0].name
        dw, dh = core.desktop_size(self.monitors)
        if dh:
            self.frame.set_property("ratio", dw / dh)
            self.area.set_size_request(360, max(round(360 * dh / dw), 60))
            self._hauteur_apercu = 0  # force le recalcul au prochain agencement
            self._ajuster_hauteur_apercu(self, self.get_allocation())
        title = self.headerbar.get_custom_title()
        if title:
            title.set_tooltip_text(f"{len(self.monitors)} écran(s) · bureau {dw}×{dh}")
        self._thumbs.clear()
        self._preview_cache = None
        self.refresh()
        self._toast(f"{len(self.monitors)} écran(s) · bureau {dw}×{dh}")

    # ------------------------------------------------- Écrans à chaud ------
    def _brancher_detection_auto(self) -> None:
        """Suit les branchements/débranchements sans attendre un F5."""
        self._screen = Gdk.Screen.get_default()
        self._sig_monitors = 0
        if self._screen is not None:
            self._sig_monitors = self._screen.connect(
                "monitors-changed", self._on_monitors_changed
            )
        self.connect("destroy", self._debrancher_detection_auto)

    def _on_monitors_changed(self, _screen) -> None:
        # Un seul branchement émet plusieurs signaux, et xrandr n'est pas
        # forcément à jour au premier : on attend que ça se stabilise.
        if self._redetect_id:
            GLib.source_remove(self._redetect_id)
        self._redetect_id = GLib.timeout_add(600, self._redetecter_auto)

    def _redetecter_auto(self) -> bool:
        self._redetect_id = 0
        detectes = core.detect_monitors()
        # Liste vide = détection transitoire pendant le branchement : on garde
        # l'existant plutôt que d'effacer l'aperçu.
        if detectes and detectes != self.monitors:
            self._appliquer_detection(detectes)
        return False

    def _debrancher_detection_auto(self, *_args) -> None:
        if self._redetect_id:
            GLib.source_remove(self._redetect_id)
            self._redetect_id = 0
        if getattr(self, "_screen", None) is not None and self._sig_monitors:
            self._screen.disconnect(self._sig_monitors)
            self._sig_monitors = 0

    def on_reset(self, _item) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE, text="Réinitialiser toute la configuration ?",
        )
        dialog.format_secondary_text("Les images affectées à chaque écran seront oubliées.")
        dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
        bouton = dialog.add_button("Réinitialiser", Gtk.ResponseType.ACCEPT)
        bouton.get_style_context().add_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        confirme = dialog.run() == Gtk.ResponseType.ACCEPT
        dialog.destroy()
        if not confirme:
            return
        ancienne = self.cfg
        self.cfg = core.Config(
            last_folder=ancienne.last_folder,
            last_random_folder=ancienne.last_random_folder,
        )
        self._sync_mode = True
        self._mode_action.set_state(GLib.Variant.new_string(self.cfg.mode))
        self.mode_buttons[self.cfg.mode].set_active(True)
        self._sync_mode = False
        rgba = Gdk.RGBA()
        rgba.parse(self.cfg.background)
        self.color_btn.set_rgba(rgba)
        self.selected = self.monitors[0].name if self.monitors else None
        self._thumbs.clear()
        self.refresh()
        self._toast("Configuration réinitialisée")

    # ------------------------------------------------------------ Appliquer --
    def on_apply(self, _btn) -> None:
        if self._applying or not self.cfg.has_image():
            return
        self._applying = True
        self.apply_stack.set_visible_child_name("busy")
        self.spinner.start()
        window = self.get_window()
        if window:
            window.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "progress"))

        # La composition d'un PNG 5760x1080 prend ~1 s : hors du thread
        # principal, sinon la fenêtre gèle et paraît plantée.
        def travail():
            try:
                self.cfg.save()
                self.cfg.apply(self.monitors)
                GLib.idle_add(self._apply_termine, None)
            except Exception as exc:  # y compris WallpaperError et erreurs Pillow
                GLib.idle_add(self._apply_termine, exc)

        threading.Thread(target=travail, daemon=True).start()

    def _apply_termine(self, exc: Exception | None) -> bool:
        self._applying = False
        self.spinner.stop()
        self.apply_stack.set_visible_child_name("idle")
        window = self.get_window()
        if window:
            window.set_cursor(None)
        if exc:
            self._set_dirty(True)
            self._error("Impossible d'appliquer le fond d'écran.", str(exc))
        else:
            self._set_dirty(False)
            self._toast("Fond d'écran appliqué")
        return False

    # ---------------------------------------------------------- Divers -----
    def on_shortcuts(self, _item) -> None:
        builder = Gtk.Builder.new_from_string(SHORTCUTS_XML, -1)
        window = builder.get_object("shortcuts")
        window.set_transient_for(self)
        window.show_all()

    def on_about(self, _item) -> None:
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("MultiWall")
        dialog.set_version(__version__)
        dialog.set_comments(
            "Un fond d'écran par moniteur, ou une image panoramique étalée sur "
            "tous les écrans."
        )
        dialog.set_copyright(COPYRIGHT)
        dialog.set_authors([AUTEUR])
        # Licence non commerciale : le résumé est affiché, le texte complet
        # est dans le fichier LICENSE à la racine du projet.
        dialog.set_license(f"{LICENCE_NOM}\n\n{LICENCE_RESUME}")
        dialog.set_wrap_license(True)
        if LINKEDIN:
            dialog.set_website(LINKEDIN)
            dialog.set_website_label(f"{AUTEUR} sur LinkedIn")

        logo = charger_logo(128)
        if logo:
            dialog.set_logo(logo)
        else:
            dialog.set_logo_icon_name("preferences-desktop-wallpaper")
        dialog.run()
        dialog.destroy()

    def _error(self, message: str, detail: str | None = None) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=message,
        )
        if detail:
            dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def _on_close(self, *_args) -> bool:
        """Sauvegarde la configuration même si l'utilisateur n'a pas appliqué."""
        try:
            self.cfg.save()
        except OSError:
            pass
        return False


class MultiWallApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.sigilbo.MultiWall")
        GLib.set_application_name("MultiWall")

    def do_startup(self):
        Gtk.Application.do_startup(self)
        pixbuf = charger_logo(128)
        if pixbuf:
            Gtk.Window.set_default_icon(pixbuf)
        else:
            Gtk.Window.set_default_icon_name("preferences-desktop-wallpaper")

    def do_activate(self):
        # Une seule fenêtre : deux vues divergeraient sur le même fichier de config.
        window = self.get_active_window() or MultiWallWindow(self)
        window.show_all()
        window.present()


def run() -> int:
    return MultiWallApp().run([])
