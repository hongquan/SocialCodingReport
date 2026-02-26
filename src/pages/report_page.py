import re
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
from ..models import ActivityItem, GraphQLQueryContext, InvolvementActivity, RepoInfo, RepoItem, ReportActivity
from ..reporting import generate_report
from ..schemas import GHGraphQLConnection, GHGraphQLResponse, GHSearchIssue


log = Logger(__name__)


def extract_titles_from_connection(connection: GHGraphQLConnection) -> dict[int, str]:
    return {node.databaseId: node.title for node in connection.nodes if node.title}


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/report_page.ui')
class ReportPage(Adw.Bin):
    __gtype_name__ = 'ReportPage'

    date_named_range = GObject.Property(type=str, default=DateNamedRange.YESTERDAY.value)
    is_loading = GObject.Property(type=bool, default=False)
    btn_generate: Gtk.Button = Gtk.Template.Child()
    btn_yesterday: Gtk.ToggleButton = Gtk.Template.Child()
    btn_today: Gtk.ToggleButton = Gtk.Template.Child()
    btn_last_7_days: Gtk.ToggleButton = Gtk.Template.Child()
    btn_copy: Gtk.Button = Gtk.Template.Child()
    btn_refresh: Gtk.Button = Gtk.Template.Child()
    past_activity_store: Gio.ListStore = Gtk.Template.Child()
    today_activity_store: Gio.ListStore = Gtk.Template.Child()
    past_selection_model: Gtk.MultiSelection = Gtk.Template.Child()
    today_selection_model: Gtk.MultiSelection = Gtk.Template.Child()
    past_activity_table: Gtk.ColumnView = Gtk.Template.Child()
    today_activity_table: Gtk.ColumnView = Gtk.Template.Child()
    report_paned: Gtk.Paned = Gtk.Template.Child()
    view_stack: Adw.ViewStack = Gtk.Template.Child()
    report_preview: WebKit.WebView = Gtk.Template.Child()
    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()
    repo_store = Gio.ListStore(item_type=RepoItem)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.client = GitHubClient()
        self.client.connect('user-activities-fetched', self.on_activities_loaded)
        self.client.connect('graphql-query-done', self.on_titles_fetched)
        self.client.connect('authored-prs-fetched', self.on_authored_prs_loaded)
        self.config = ConfigManager()
        self.github_token = None
        self.github_token = None
        self.current_report_html = ''
        resource_path = '/vn/ququ/SocialCodingReport/queries/list-issues.gql'
        bytes_data = Gio.resources_lookup_data(resource_path, Gio.ResourceLookupFlags.NONE)
        self.graphql_query = bytes_data.get_data().decode('utf-8')

        # Connect selection models
        self.past_selection_model.connect('selection-changed', self.on_selection_changed, self.past_activity_store)
        self.today_selection_model.connect('selection-changed', self.on_selection_changed, self.today_activity_store)

        # Initial load
        GLib.idle_add(self.fetch_remote_activities)

    def add_toast(self, message: str, timeout: int = 5) -> None:
        """Add a toast with optional timeout in seconds."""
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

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
            if new_state == DateNamedRange.TODAY:
                self.view_stack.set_visible_child_name('today')
            else:
                self.view_stack.set_visible_child_name('past')
            self.fetch_remote_activities(force=False)

    def fetch_remote_activities(self, force: bool = False):
        self.is_loading = True
        state = DateNamedRange(self.date_named_range)

        # Skip fetching if data is already present and not forced
        target_store = self.today_activity_store if state == DateNamedRange.TODAY else self.past_activity_store
        if not force and len(target_store) > 0:
            log.info('Data already present for {}, skipping fetch.', state)
            self.is_loading = False
            return

        # Determine date
        now = datetime.now().astimezone()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if state == DateNamedRange.YESTERDAY:
            since_date = today_start - timedelta(days=1)
            until_date = today_start
            self.past_activity_store.remove_all()
        elif state == DateNamedRange.LAST_7_DAYS:
            since_date = today_start - timedelta(days=7)
            until_date = today_start
            self.past_activity_store.remove_all()
        else:
            since_date = today_start
            until_date = now
            self.today_activity_store.remove_all()

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

        self.add_toast('Fetching data from GitHub...')

        self.client.fetch_user_events(github_account.username, since_date, until_date, token=github_account.token)

        repo_list = [f'{rp.owner}/{rp.name}' for rp in self.repo_store]
        self.client.fetch_authored_prs(github_account.username, repos=repo_list, token=github_account.token)

    def on_activities_loaded(
        self,
        client: GitHubClient,
        username: str,
        activities: Sequence[InvolvementActivity],
        error: str,
        is_rate_limit: bool,
    ):
        # Clear loading state for ALL repos
        self.is_loading = False

        if error:
            log.error('Error loading data: {}', error)
            if is_rate_limit:
                self.add_toast('Rate limited! Add a GitHub API token in Preferences.')
            else:
                self.add_toast(f'Error: {error}')
            return

        self.add_toast('Data loaded successfully.')

        # Filter items based on configured repos
        configured_repos = frozenset(f'{rp.owner}/{rp.name}' for rp in self.repo_store)
        log.debug('Configured repos: {}', configured_repos)

        target_store = (
            self.today_activity_store if self.date_named_range == DateNamedRange.TODAY else self.past_activity_store
        )

        for act in activities:
            if act.repo_long_name in configured_repos:
                item = ActivityItem.from_activity_data(act)
                # Ensure no duplicates in the store
                if not any(existing.database_id == item.database_id for existing in target_store):
                    target_store.append(item)
                    # Select by default in the UI model
                    selection_model = (
                        self.today_selection_model
                        if self.date_named_range == DateNamedRange.TODAY
                        else self.past_selection_model
                    )
                    selection_model.select_item(len(target_store) - 1, False)

        # Check for missing titles
        missing_items_by_repo: dict[tuple[str, str], list[ActivityItem]] = {}
        for store in [self.past_activity_store, self.today_activity_store]:
            for item in store:
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
                user_data=GraphQLQueryContext(items=items, repo_owner=owner, repo_name=name),
            )

        log.info(
            'Loaded activities. Past: {}, Today: {}',
            len(self.past_activity_store),
            len(self.today_activity_store),
        )

    def on_titles_fetched(
        self,
        client: GitHubClient,
        response_json: str,
        user_data: GraphQLQueryContext,
    ):
        items, owner, name = user_data.items, user_data.repo_owner, user_data.repo_name
        is_rate_limit = user_data.is_rate_limit

        if not response_json:
            log.warning('GraphQL response empty for {}/{} (is_rate_limit={})', owner, name, is_rate_limit)
            if is_rate_limit:
                self.add_toast('Rate limited! Add a GitHub API token in Preferences.')
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

        log.debug('Titles found in GraphQL: {}', list(title_map.values()))
        log.debug('IDs found in GraphQL: {}', list(title_map.keys()))

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

    def on_authored_prs_loaded(
        self, client: GitHubClient, username: str, prs: list[GHSearchIssue], error: str, is_rate_limit: bool
    ):
        if error:
            log.error('Error loading authored PRs: {}', error)
            if is_rate_limit:
                self.add_toast('Rate limited! Add a GitHub API token in Preferences.')
            return

        configured_repos = frozenset(f'{rp.owner}/{rp.name}' for rp in self.repo_store)
        self.ongoing_activities = []  # Just for internal ref if needed, but not using it anymore

        for pr in prs:
            if pr.repo_long_name in configured_repos:
                # Map GHSearchIssue to ActivityItem
                activity = InvolvementActivity(
                    title=pr.title,
                    api_url=pr.html_url,  # Search API doesn't give PR API URL directly in same field
                    html_url=pr.html_url,
                    task_type=TaskType.PR,
                    action=ActivityAction.CREATED_PR,  # We treat as created since it's authored
                    author=username,
                    created_at=datetime.now(),  # Not critical for plans
                    repo_info=RepoInfo(name=pr.repo_name, owner=pr.repo_owner),
                    database_id=pr.id,
                    number=pr.number,
                )
                item = ActivityItem.from_activity_data(activity)

                # Ensure no duplicates in today_activity_store
                if not any(existing.database_id == item.database_id for existing in self.today_activity_store):
                    self.today_activity_store.append(item)
                    self.today_selection_model.select_item(len(self.today_activity_store) - 1, False)

        log.info('Loaded ongoing PRs for user {}', username)

    def on_selection_changed(self, model: Gtk.SelectionModel, position: int, n_items: int, store: Gio.ListStore):
        for i in range(position, position + n_items):
            item = store.get_item(i)
            if item:
                item.selected = model.is_selected(i)

    @Gtk.Template.Callback()
    def on_refresh(self, btn: Gtk.Button):
        self.fetch_remote_activities(force=True)

    @Gtk.Template.Callback()
    def on_generate(self, btn: Gtk.Button):
        # Yesterday section: Selected items from past_activity_store.
        # Today section: All items from today_activity_store.

        past_activities = []
        for item in self.past_activity_store:
            if item.selected:
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
                past_activities.append(activity)

        today_plans = []
        # If user is on TODAY tab, they might want to select specific plans?
        # If nothing is selected in today tab, we include everything.
        # If something is selected, only include selected.

        has_today_selection = any(item.selected for item in self.today_activity_store)

        for item in self.today_activity_store:
            # If there is a selection, only include selected ones.
            # Otherwise, include everything from today_activity_store.
            if not has_today_selection or item.selected:
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

        html_content = generate_report(past_activities, today_plans)
        self.current_report_html = html_content

        self.report_preview.load_html(html_content, None)
        self.btn_copy.set_sensitive(True)

        # Auto-expand preview if there is content
        if past_activities or today_plans:
            # We want preview to occupy roughly 60% of the space
            # So we set position to 40% of the height
            height = self.report_paned.get_height()
            if height > 0:
                self.report_paned.set_position(int(height * 0.4))

        self.add_toast('Report generated successfully.')

    @Gtk.Template.Callback()
    def on_copy(self, btn: Gtk.Button):
        if not self.current_report_html:
            return

        display = self.get_display()
        clipboard = display.get_clipboard()

        # Create a content provider for both HTML and plain text for better compatibility
        # We need to strip HTML for plain text fallback
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
        self.add_toast('Report copied to clipboard.')
        log.info('Report copied to clipboard as HTML and plain text.')
