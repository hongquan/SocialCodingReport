from collections.abc import Sequence
from typing import Any

import gi


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from datetime import datetime, timedelta

from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from logbook import Logger

from ..config import ConfigManager
from ..consts import ActivityAction, Host, TaskType
from ..github_client import GitHubClient
from ..models import ActivityData, ActivityItem, RepoInfo, RepoItem, ReportActivity
from ..reporting import generate_report


log = Logger('ReportPage')


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/report_page.ui')
class ReportPage(Adw.Bin):
    __gtype_name__ = 'ReportPage'

    activity_table: Gtk.ColumnView = Gtk.Template.Child()
    btn_generate: Gtk.Button = Gtk.Template.Child()
    btn_yesterday: Gtk.ToggleButton = Gtk.Template.Child()
    btn_today: Gtk.ToggleButton = Gtk.Template.Child()
    activity_store: Gio.ListStore = Gtk.Template.Child()
    selection_model: Gtk.MultiSelection = Gtk.Template.Child()
    repo_store = Gio.ListStore(item_type=RepoItem)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.client = GitHubClient()
        self.client.connect('user-activities-fetched', self.on_activities_loaded)
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
            since_date = today_start - timedelta(days=1)
        else:
            since_date = today_start

        # Clear current
        self.activity_store.remove_all()

        repos = self.config.load_repositories()
        if not repos:
            log.info('No repositories configured.')
            return

        # Prepare repo store
        self.repo_store.remove_all()
        for repo_info in repos:
            repo_item = RepoItem(name=repo_info.name, owner=repo_info.owner)
            repo_item.is_loading = True
            self.repo_store.append(repo_item)

        # Get GitHub username
        accounts = self.config.load_accounts()
        github_username = next((a.username for a in accounts if a.host == Host.GITHUB), None)

        if not github_username:
            log.error('No GitHub account configured.')
            # Clear loading state
            for i in range(self.repo_store.get_n_items()):
                self.repo_store.get_item(i).is_loading = False
            return

        self.client.fetch_user_events(github_username, since_date)

    def on_activities_loaded(self, client: GitHubClient, username: str, items: Sequence[ActivityData], error: str):
        # Clear loading state for ALL repos
        for i in range(self.repo_store.get_n_items()):
            repo_item = self.repo_store.get_item(i)
            repo_item.is_loading = False

        if error:
            log.error('Error loading data: {}', error)
            return

        # Filter items based on configured repos
        configured_repos = set()
        for i in range(self.repo_store.get_n_items()):
            configured_repos.add(self.repo_store.get_item(i).name)

        count = 0
        for item in items:
            if item.repo_name in configured_repos:
                # We can now create ActivityItem directly
                item_obj = ActivityItem.from_activity_data(item)
                self.activity_store.append(item_obj)
                count += 1

        log.info('Loaded {} activities for user {}', count, username)

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

        activities = []
        for item in selected_items:
            # Reconstruct ActivityData
            # We assume GitHub host for now or we could store it in ActivityItem if needed.
            if '/' in item.repo_name:
                owner, name = item.repo_name.split('/', 1)
            else:
                owner, name = '', item.repo_name

            repo_info = RepoInfo(name=name, owner=owner, host=Host.GITHUB)

            activity = ReportActivity(
                title=item.title,
                url=item.url,
                task_type=TaskType(
                    item.task_type
                ),  # Convert string back to Enum? Or check if ActivityData expects Enum.
                created_at=item.created_at,
                repo_info=repo_info,
                author=item.author,
                action=ActivityAction(item.action),
            )
            activities.append(activity)

        html_content = generate_report(activities)

        clipboard = self.get_display().get_clipboard()
        content_provider = Gdk.ContentProvider.new_for_bytes('text/html', GLib.Bytes.new(html_content.encode('utf-8')))
        clipboard.set_content(content_provider)

        log.info('Report copied to clipboard.')

    @Gtk.Template.Callback()
    def is_loading(self, *args) -> bool:
        for item in self.repo_store:
            if item.is_loading:
                return True
        return False
