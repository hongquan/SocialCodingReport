from typing import Any

import gi


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, GLib, Gtk

from .pages.preferences_page import PreferencesPage
from .pages.report_page import ReportPage


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/window.ui')
class MainWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'MainWindow'

    view_stack: Adw.ViewStack = Gtk.Template.Child()
    report_page: ReportPage = Gtk.Template.Child()
    preferences_page: PreferencesPage = Gtk.Template.Child()

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        # Actions for navigation
        action_group = Gio.SimpleActionGroup()
        self.insert_action_group('win', action_group)

        action_pref = Gio.SimpleAction.new('preferences', None)
        action_pref.connect('activate', self.on_preferences)
        action_group.add_action(action_pref)

        action_back = Gio.SimpleAction.new('back', None)
        action_back.connect('activate', self.on_back)
        action_group.add_action(action_back)

    def on_preferences(self, action: Gio.SimpleAction, param: GLib.Variant | None):
        self.view_stack.set_visible_child_name('preferences')

    def on_back(self, action: Gio.SimpleAction, param: GLib.Variant | None):
        self.view_stack.set_visible_child_name('report')
