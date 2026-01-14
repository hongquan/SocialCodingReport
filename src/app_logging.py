from typing import Any

import gi
import logbook
from logbook.handlers import Handler, StringFormatterHandlerMixin


gi.require_version('GLib', '2.0')
from gi.repository import GLib

from .consts import SHORT_NAME


LOGBOOK_LEVEL_TO_GLIB = {
    logbook.DEBUG: GLib.LogLevelFlags.LEVEL_DEBUG,
    logbook.INFO: GLib.LogLevelFlags.LEVEL_INFO,
    logbook.WARNING: GLib.LogLevelFlags.LEVEL_WARNING,
    logbook.ERROR: GLib.LogLevelFlags.LEVEL_CRITICAL,
}


def log_to_glib(level: GLib.LogLevelFlags, message: str):
    variant_message = GLib.Variant('s', message)
    variant_dict = GLib.Variant(
        'a{sv}',
        {
            'MESSAGE': variant_message,
        },
    )
    GLib.log_variant(SHORT_NAME, level, variant_dict)


class GLibLogHandler(Handler, StringFormatterHandlerMixin):
    def emit(self, record: Any):
        message = self.format(record)
        level = LOGBOOK_LEVEL_TO_GLIB.get(record.level, GLib.LogLevelFlags.LEVEL_INFO)
        log_to_glib(level, message)
