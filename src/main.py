import os
import sys

import gi


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('WebKit', '6.0')
from gi.repository import Adw, Gio, GLib
from logbook import Logger

from .consts import APP_ID
from .logup import GLibLogHandler


log = Logger(__name__)


class SocialCodingReportApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def define_shortcuts(self):
        action_quit = Gio.SimpleAction.new('quit', None)
        action_quit.connect('activate', self.on_quit)
        self.add_action(action_quit)
        self.set_accels_for_action('app.quit', ['<Control>q'])

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.define_shortcuts()

    def on_quit(self, action, param):
        self.quit()

    def do_activate(self):
        from .window import MainWindow

        win = self.get_active_window()
        if not win:
            win = MainWindow(application=self)
        win.present()


def main() -> int:
    # Load GResource
    resource_path = os.path.join(os.path.dirname(__file__), '..', 'socialcodingreport.gresource')
    # When installed, it is in pkgdatadir.
    # We need to know where pkgdatadir is.
    # For now, let's try to locate it relative to this file?
    # In meson install:
    #   moduledir = pkgdatadir / 'socialcodingreport' -> src/main.py is in pkgdatadir/socialcodingreport
    #   resources installed to pkgdatadir.
    #   So resource is at ../socialcodingreport.gresource relative to main.py

    # However, if creating from 'run_command', we need to be careful.
    # Let's assume standard install layout.

    try:
        resource = Gio.Resource.load(resource_path)
        resource._register()
    except GLib.Error as e:
        log.warning('Failed to load resource from {}: {}', resource_path, e)
        # If running locally without install, this might fail unless we point to build dir.
        # But user is running 'meson install', so we assume installed layout.

    # Logging
    handler = GLibLogHandler()
    handler.push_application()

    app = SocialCodingReportApplication()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
