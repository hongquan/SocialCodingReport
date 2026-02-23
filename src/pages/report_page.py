from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import gi
from pydantic import ValidationError


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GObject', '2.0')
gi.require_version('WebKit', '6.0')
gi.require_version('Gdk', '4.0')


from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, WebKit
from logbook import Logger

from ..config import ConfigManager
from ..consts import ActivityAction, DateNamedRange, Host, TaskType
from ..github_client import GitHubClient
from ..models import ActivityItem, InvolvementActivity, RepoInfo, RepoItem, ReportActivity
from ..reporting import generate_report
from ..schemas import GHGraphQLConnection, GHGraphQLResponse


log = Logger(__name__)


def extract_titles_from_connection(connection: GHGraphQLConnection) -> dict[int, str]:
    return {node.databaseId: node.title for node in connection.nodes if node.title}


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/report_page.ui')
class ReportPage(Adw.Bin):
    __gtype_name__ = 'ReportPage'

    date_named_range = GObject.Property(type=str, default=DateNamedRange.YESTERDAY.value)
    is_loading = GObject.Property(type=bool, default=False)
    activity_table: Gtk.ColumnView = Gtk.Template.Child()
    btn_generate: Gtk.Button = Gtk.Template.Child()
    btn_yesterday: Gtk.ToggleButton = Gtk.Template.Child()
    btn_today: Gtk.ToggleButton = Gtk.Template.Child()
    btn_last_7_days: Gtk.ToggleButton = Gtk.Template.Child()
    btn_copy: Gtk.Button = Gtk.Template.Child()
    activity_store: Gio.ListStore = Gtk.Template.Child()
    selection_model: Gtk.MultiSelection = Gtk.Template.Child()
    report_preview: WebKit.WebView = Gtk.Template.Child()
    repo_store = Gio.ListStore(item_type=RepoItem)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.client = GitHubClient()
        self.client.connect('user-activities-fetched', self.on_activities_loaded)
        self.client.connect('graphql-query-done', self.on_titles_fetched)
        self.config = ConfigManager()
        self.github_token = None
        self.today_activities: list[ActivityItem] = []
        self.current_report_html = ''
        resource_path = '/vn/ququ/SocialCodingReport/queries/list-issues.gql'
        bytes_data = Gio.resources_lookup_data(resource_path, Gio.ResourceLookupFlags.NONE)
        self.graphql_query = bytes_data.get_data().decode('utf-8')

        # Initial load
        GLib.idle_add(self.load_data)

    @Gtk.Template.Callback()
    def is_today_active(self, wd: Self, value: str) -> bool:
        return value == DateNamedRange.TODAY

    @Gtk.Template.Callback()
    def is_yesterday_active(self, wd: Self, value: str) -> bool:
        return value == DateNamedRange.YESTERDAY

    @Gtk.Template.Callback()
    def is_last_7_days_active(self, wd: Self, value: str) -> bool:
        return value == DateNamedRange.LAST_7_DAYS

    @Gtk.Template.Callback()
    def on_date_range_toggled(self, widget: Gtk.ToggleButton):
        if self.btn_yesterday.get_active():
            new_state = DateNamedRange.YESTERDAY
        elif self.btn_today.get_active():
            new_state = DateNamedRange.TODAY
        elif self.btn_last_7_days.get_active():
            new_state = DateNamedRange.LAST_7_DAYS
        else:
            return  # Should not happen as they are grouped

        if new_state != self.date_named_range:
            self.date_named_range = new_state
            self.load_data()

    def load_data(self):
        self.is_loading = True
        state = DateNamedRange(self.date_named_range)

        # Determine date
        now = datetime.now().astimezone()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if state == DateNamedRange.YESTERDAY:
            since_date = today_start - timedelta(days=1)
            until_date = today_start
        elif state == DateNamedRange.LAST_7_DAYS:
            since_date = today_start - timedelta(days=7)
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

        self.github_token = github_account.token
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

        # Store today's activity items for automated plans
        if self.date_named_range == DateNamedRange.TODAY:
            self.today_activities = []
            for item in self.activity_store:
                self.today_activities.append(item)

        # Check for missing titles
        missing_items_by_repo: dict[tuple[str, str], list[ActivityItem]] = {}
        for item in self.activity_store:
            # Check for no title and valid database_id
            if not item.title and item.database_id:
                key = (item.repo_owner, item.repo_name)
                if key not in missing_items_by_repo:
                    missing_items_by_repo[key] = []
                missing_items_by_repo[key].append(item)

        for (owner, name), items in missing_items_by_repo.items():
            if not items:
                continue

            # Determine distinct 'since' date for this batch.
            # Ideally we want the earliest created_at of the missing items.
            # But converting ActivityItem.created_at (which is object/datetime) to ISO string is needed.
            min_date = min(item.created_at for item in items if isinstance(item.created_at, datetime))
            # GitHub GraphQL API expects UTC for the 'since' parameter
            since_iso = (min_date.astimezone(UTC) - timedelta(minutes=1)).isoformat()

            log.info('Fetching missing titles for {}/{} since {}...', owner, name, since_iso)

            # Pass repo key and items to callback
            self.client.run_graphql_query(
                self.graphql_query,
                {'owner': owner, 'name': name, 'since': since_iso},
                token=self.github_token,
                user_data=(items, owner, name),
            )

        log.info('Loaded {} activities for user {}', self.activity_store.get_n_items(), username)

    def on_titles_fetched(
        self, client: GitHubClient, response_json: str, user_data: tuple[list[ActivityItem], str, str]
    ):
        items, owner, name = user_data

        if not response_json:
            log.warning('GraphQL response empty for {}/{}', owner, name)
            return

        try:
            response = GHGraphQLResponse.model_validate_json(response_json)
        except ValidationError as e:
            log.error('GraphQL validation failed for {}/{}: {}', owner, name, e)
            return

        repo_data = response.data.repository

        # Collect databaseId -> title map
        title_map = extract_titles_from_connection(repo_data.issues)
        title_map.update(extract_titles_from_connection(repo_data.pullRequests))

        update_count = 0
        for item in items:
            if item.database_id in title_map:
                item.title = title_map[item.database_id]
                update_count += 1
            else:
                log.debug(
                    'Title not found for item {} (db_id: {}) in GraphQL response', item.repo_long_name, item.database_id
                )

        log.info('Updated titles for {}/{} items: {}/{} found', owner, name, update_count, len(items))

    @Gtk.Template.Callback()
    def on_refresh(self, btn: Gtk.Button):
        self.load_data()

    @Gtk.Template.Callback()
    def on_generate(self, btn: Gtk.Button):
        selected_items = []
        for i, item in enumerate(self.activity_store):
            if self.selection_model.is_selected(i):
                selected_items.append(item)

        activities = []
        for item in selected_items:
            # Reconstruct ActivityData and RepoInfo
            # We assume GitHub host for now.
            repo_info = RepoInfo(name=item.repo_name, owner=item.repo_owner, host=Host.GITHUB)

            activity = ReportActivity(
                title=item.title,
                api_url=item.api_url,
                html_url=item.url,
                task_type=TaskType(item.task_type),
                action=ActivityAction(item.action),
                author=item.author,
                created_at=item.created_at,
                repo_info=repo_info,
                database_id=item.database_id,
                number=item.number,
            )
            activities.append(activity)

        today_plans = []
        for item in self.today_activities:
            repo_info = RepoInfo(name=item.repo_name, owner=item.repo_owner, host=Host.GITHUB)
            activity = ReportActivity(
                title=item.title,
                api_url=item.api_url,
                html_url=item.url,
                task_type=TaskType(item.task_type),
                action=ActivityAction(item.action),
                author=item.author,
                created_at=item.created_at,
                repo_info=repo_info,
                database_id=item.database_id,
                number=item.number,
            )
            today_plans.append(activity)

        html_content = generate_report(activities, today_plans)
        self.current_report_html = html_content

        self.report_preview.load_html(html_content, None)
        self.btn_copy.set_sensitive(True)

        log.info('Report generated and displayed in preview.')

    @Gtk.Template.Callback()
    def on_copy(self, btn: Gtk.Button):
        if not self.current_report_html:
            return

        display = self.get_display()
        clipboard = display.get_clipboard()

        # Create a content provider for both HTML and plain text for better compatibility
        # We need to strip HTML for plain text fallback
        import re

        plain_text = re.sub('<[^<]+?>', '', self.current_report_html)

        content = Gdk.ContentProvider.new_union(
            [
                Gdk.ContentProvider.new_for_bytes(
                    'text/html', GLib.Bytes.new(self.current_report_html.encode('utf-8'))
                ),
                Gdk.ContentProvider.new_for_bytes('text/plain', GLib.Bytes.new(plain_text.encode('utf-8'))),
            ]
        )

        clipboard.set_content(content)
        log.info('Report copied to clipboard as HTML and plain text.')
