from collections.abc import Sequence
from typing import Any, Self

import gi


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GObject', '2.0')
from datetime import datetime, timedelta

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk
from logbook import Logger

from ..config import ConfigManager
from ..consts import ActivityAction, DateNamedRange, Host, TaskType
from ..github_client import GitHubClient
from ..models import ActivityItem, InvolvementActivity, RepoInfo, RepoItem, ReportActivity
from ..reporting import generate_report


log = Logger(__name__)


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/report_page.ui')
class ReportPage(Adw.Bin):
    __gtype_name__ = 'ReportPage'

    date_named_range = GObject.Property(type=str, default=DateNamedRange.YESTERDAY.value)
    is_loading = GObject.Property(type=bool, default=False)
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

        # Initial load
        GLib.idle_add(self.load_data)

    @Gtk.Template.Callback()
    def is_yesterday_active(self, wd: Self, value: str) -> bool:
        return value == DateNamedRange.YESTERDAY

    @Gtk.Template.Callback()
    def load_data(self, ytd_btn: Gtk.ToggleButton | None = None):
        self.is_loading = True
        # Get filter state
        if ytd_btn is not None:
            if ytd_btn.get_active():
                state = DateNamedRange.YESTERDAY
            else:
                state = DateNamedRange.TODAY
            self.date_named_range = state
        else:
            state = DateNamedRange(self.date_named_range)

        # Determine date
        now = datetime.now().astimezone()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if state == DateNamedRange.YESTERDAY:
            since_date = today_start - timedelta(days=1)
            until_date = today_start
        else:
            since_date = today_start
            until_date = now

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
            self.repo_store.append(repo_item)

        # Get GitHub username and token
        accounts = self.config.load_accounts()
        github_account = next((a for a in accounts if a.host == Host.GITHUB), None)

        if not github_account:
            log.error('No GitHub account configured.')
            # Clear loading state
            self.is_loading = False
            return

        self.client.fetch_user_events(github_account.username, since_date, until_date, token=github_account.token)

    def on_activities_loaded(
        self, client: GitHubClient, username: str, activities: Sequence[InvolvementActivity], error: str
    ):
        # Clear loading state for ALL repos
        self.is_loading = False

        if error:
            log.error('Error loading data: {}', error)
            return

        # Filter items based on configured repos
        configured_repos = frozenset(f'{rp.owner}/{rp.name}' for rp in self.repo_store)
        log.debug('Configured repos: {}', configured_repos)

        for act in activities:
            if act.repo_long_name in configured_repos:
                # We can now create ActivityItem directly
                item = ActivityItem.from_activity_data(act)
                self.activity_store.append(item)

        log.info('Loaded {} activities for user {}', self.activity_store.get_n_items(), username)

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
                api_url=item.url,
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
