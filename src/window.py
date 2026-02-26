from typing import Any

import gi


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, GLib, Gtk

from .pages.preferences_page import PreferencesPage
from .pages.report_page import ReportPage
from .paths import VERSION


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/window.ui')
class MainWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'MainWindow'

    view_stack: Adw.ViewStack = Gtk.Template.Child()
    btn_back: Gtk.Button = Gtk.Template.Child()
    report_page: ReportPage = Gtk.Template.Child()
    preferences_page: PreferencesPage = Gtk.Template.Child()

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        # Actions for navigation
        action_group = Gio.SimpleActionGroup()
        self.insert_action_group('win', action_group)

        self.action_pref = Gio.SimpleAction.new('preferences', None)
        self.action_pref.connect('activate', self.on_preferences)
        action_group.add_action(self.action_pref)

        action_about = Gio.SimpleAction.new('about', None)
        action_about.connect('activate', self.on_about)
        action_group.add_action(action_about)

        action_back = Gio.SimpleAction.new('back', None)
        action_back.connect('activate', self.on_back)
        action_group.add_action(action_back)

    def on_preferences(self, action: Gio.SimpleAction, param: GLib.Variant | None):
        self.view_stack.set_visible_child_name('preferences')
        self.btn_back.set_visible(True)
        self.action_pref.set_enabled(False)

    def on_about(self, action: Gio.SimpleAction, param: GLib.Variant | None):
        about = Adw.AboutWindow(
            application_name='Social Coding Report',
            version=VERSION,
            developer_name='Nguyễn Hồng Quân',
            license_type=Gtk.License.GPL_3_0,
            issue_url='https://github.com/hongquan/SocialCodingReport/issues',
            website='https://github.com/hongquan/SocialCodingReport',
            application_icon='vn.ququ.SocialCodingReport',
            transient_for=self,
            modal=True,
        )
        about.present()

    def on_back(self, action: Gio.SimpleAction, param: GLib.Variant | None):
        self.view_stack.set_visible_child_name('report')
        self.btn_back.set_visible(False)
        self.action_pref.set_enabled(True)
