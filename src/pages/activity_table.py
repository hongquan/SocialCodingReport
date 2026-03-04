import gi


gi.require_version('Gtk', '4.0')

from gi.repository import Gtk


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/activity_table.ui')
class ActivityTable(Gtk.ColumnView):
    __gtype_name__ = 'ActivityTable'
