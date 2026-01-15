from collections.abc import Sequence
from typing import Any

import gi


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from datetime import datetime, timedelta

from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from logbook import Logger

from ..config import ConfigManager
from ..github_client import GitHubClient
from ..models import ActivityData, ActivityItem, RepoItem


log = Logger('ReportPage')


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/report_page.ui')
class ReportPage(Adw.Bin):
    __gtype_name__ = 'ReportPage'

    list_view: Gtk.ListView = Gtk.Template.Child()
    btn_generate: Gtk.Button = Gtk.Template.Child()
    btn_yesterday: Gtk.ToggleButton = Gtk.Template.Child()
    btn_today: Gtk.ToggleButton = Gtk.Template.Child()
    activity_store: Gio.ListStore = Gtk.Template.Child()
    selection_model: Gtk.MultiSelection = Gtk.Template.Child()
    repo_store = Gio.ListStore(item_type=RepoItem)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.client = GitHubClient()
        self.config = ConfigManager()

        # Actions
        self.action_group = Gio.SimpleActionGroup()
        self.insert_action_group('report', self.action_group)

        action_filter = Gio.SimpleAction.new_stateful(
            'filter', GLib.VariantType.new('s'), GLib.Variant.new_string('today')
        )
        action_filter.connect('change-state', self.on_filter_change_state)
        self.action_group.add_action(action_filter)

        # Initial load
        GLib.idle_add(self.load_data)

    def on_filter_change_state(self, action: Gio.SimpleAction, value: GLib.Variant):
        action.set_state(value)
        self.load_data()

    def load_data(self):
        # Determine date
        now = datetime.now().astimezone()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Get filter state
        state = self.action_group.get_action_state('filter').get_string()

        if state == 'yesterday':
            target_date = today_start - timedelta(days=1)
        else:
            target_date = today_start

        # Clear current
        self.activity_store.remove_all()

        repos = self.config.load_repositories()
        if not repos:
            log.info('No repositories configured.')
            return

        # Prepare repo store
        self.repo_store.remove_all()
        for repo_name in repos:
            self.repo_store.append(RepoItem(name=repo_name))

        for i in range(self.repo_store.get_n_items()):
            repo_item = self.repo_store.get_item(i)
            repo_item.is_loading = True

            self.client.fetch_activities(
                repo_item.name,
                target_date,
                lambda items, error, item=repo_item: self.on_activities_loaded(items, error, repo_item=item),
            )

    def on_activities_loaded(self, items: Sequence[ActivityData], error: str | None, repo_item: RepoItem | None = None):
        if repo_item:
            repo_item.is_loading = False

        if error:
            log.error('Error loading data: {}', error)
            return

        for item_data in items:
            item = ActivityItem.from_activity_data(item_data)
            self.activity_store.append(item)

    @Gtk.Template.Callback()
    def on_refresh(self, btn: Gtk.Button):
        self.load_data()

    @Gtk.Template.Callback()
    def on_generate(self, btn: Gtk.Button):
        selected_items = []
        n_items = self.activity_store.get_n_items()
        for i in range(n_items):
            if self.selection_model.is_selected(i):
                item = self.activity_store.get_item(i)
                selected_items.append(item)

        if not selected_items:
            log.info('No items selected')
            return

        html_parts = ['<ul>']
        for item in selected_items:
            # Title already contains markup if we used display_text, BUT the model has raw title.
            # We want to escape for HTML export.
            esc_title = GLib.markup_escape_text(item.title)
            html_parts.append(f'<li><a href="{item.url}">[{item.repo_name}] {esc_title}</a></li>')
        html_parts.append('</ul>')

        html_content = '\n'.join(html_parts)

        clipboard = self.get_display().get_clipboard()
        content_provider = Gdk.ContentProvider.new_for_bytes('text/html', GLib.Bytes.new(html_content.encode('utf-8')))
        clipboard.set_content(content_provider)

        log.info('Report copied to clipboard.')

    @Gtk.Template.Callback()
    def is_loading(self, *args) -> bool:
        for i in range(self.repo_store.get_n_items()):
            item = self.repo_store.get_item(i)
            if item.is_loading:
                return True
        return False
