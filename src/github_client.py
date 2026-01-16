import os
from datetime import datetime
from http import HTTPMethod
from urllib.parse import quote

import gi
import msgspec


gi.require_version('Soup', '3.0')

from gi.repository import Gio, GLib, GObject, Soup
from logbook import Logger

from .consts import GitHubEventType, Host, TaskType
from .models import ActivityData, ActivityType, InvolvementActivity, RepoInfo


log = Logger(__name__)


class GitHubError(msgspec.Struct):
    message: str | None = None
    documentation_url: str | None = None


class GitHubPullRequest(msgspec.Struct):
    url: str = ''
    html_url: str = ''


class GitHubUser(msgspec.Struct):
    login: str = ''


class GitHubIssue(msgspec.Struct):
    user: GitHubUser
    html_url: str
    created_at: datetime
    title: str = ''

    def to_activity_data(self, repo_name: str) -> InvolvementActivity:
        is_pr = '/pull/' in self.html_url
        type_enum = TaskType.PR if is_pr else TaskType.ISSUE

        # Parse repo_name "owner/name"
        if '/' in repo_name:
            owner, name = repo_name.split('/', 1)
        else:
            owner, name = '', repo_name

        repo_info = RepoInfo(name=name, owner=owner, host=Host.GITHUB)

        return InvolvementActivity(
            title=self.title,
            url=self.html_url,
            task_type=type_enum,
            author=self.user.login,
            created_at=self.created_at,
            repo_info=repo_info,
        )


class GitHubRepo(msgspec.Struct):
    name: str
    url: str


class GitHubIssuesPayload(msgspec.Struct):
    issue: GitHubIssue
    action: str = ''


class GitHubPullRequestPayload(msgspec.Struct):
    url: str = ''


class GitHubPullRequestEventPayload(msgspec.Struct):
    pull_request: GitHubPullRequestPayload
    action: str = ''


class GitHubReviewPayload(msgspec.Struct):
    pull_request: GitHubPullRequestPayload
    action: str = ''


class GitHubCommonEvent(msgspec.Struct):
    id: str
    created_at: datetime
    repo: GitHubRepo


class GitHubIssuesEvent(GitHubCommonEvent, tag=GitHubEventType.ISSUE.value, tag_field='type'):
    payload: GitHubIssuesPayload


class GitHubPullRequestEvent(GitHubCommonEvent, tag=GitHubEventType.PULL_REQUEST.value, tag_field='type'):
    payload: GitHubPullRequestEventPayload


class GitHubReviewEvent(GitHubCommonEvent, tag=GitHubEventType.PULL_REQUEST_REVIEW.value, tag_field='type'):
    payload: GitHubReviewPayload


GitHubEvent = GitHubIssuesEvent | GitHubPullRequestEvent | GitHubReviewEvent


class GitHubClient(GObject.Object):
    __gsignals__ = {
        'user-activities-fetched': (GObject.SignalFlags.RUN_FIRST, None, (str, object, str)),
    }

    def __init__(self):
        super().__init__()
        self.session = Soup.Session.new()
        self.token = os.getenv('GITHUB_TOKEN')
        self.user_agent = 'SocialCodingReport/0.1'

    def fetch_user_events(
        self,
        username: str,
        since_date: datetime,
    ):
        """
        Fetch public events for a user.
        Emits 'user-activities-fetched' (username, activity_list, error_message)
        """
        url = f'https://api.github.com/users/{quote(username)}/events'

        msg = Soup.Message.new(HTTPMethod.GET, url)
        msg.get_request_headers().append('User-Agent', self.user_agent)
        # We are ignoring the token for now as requested

        log.info('Fetching events for {}', username)
        self.session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            None,
            self.on_events_fetching_done,
            (username, since_date),
        )

    def on_events_fetching_done(self, session: Soup.Session, result: Gio.AsyncResult, user_data: tuple[str, datetime]):
        username, since_date = user_data
        msg = session.get_async_result_message(result)
        try:
            bytes_data = session.send_and_read_finish(result)
        except GLib.Error as e:
            log.error('Network error during fetch: {}', e)
            self.emit('user-activities-fetched', username, [], str(e))
            return

        status_code = msg.get_status()
        if status_code != 200:
            log.error('GitHub API returned status code: {}', status_code)
            self.emit('user-activities-fetched', username, [], f'GitHub API Error: Status {status_code}')
            return

        raw_data = bytes_data.get_data()

        try:
            # 1. Parse as list of Raw items
            raw_events = msgspec.json.decode(raw_data, type=tuple[msgspec.Raw, ...])
        except (msgspec.DecodeError, UnicodeDecodeError) as e:
            log.error('JSON decode error (generic): {}', e)
            self.emit('user-activities-fetched', username, [], str(e))
            return

        items = []
        for raw_event in raw_events:
            try:
                # 2. Parse each Raw item as Tagged Union
                event = msgspec.json.decode(raw_event, type=GitHubEvent)
            except msgspec.DecodeError:
                # Ignore unknown events
                continue

            if event.created_at < since_date:
                continue

            # Map event to ActivityData
            activity_type = None
            title = 'Unknown Activity'
            url = ''

            repo_name = event.repo.name

            if isinstance(event, GitHubIssuesEvent):
                activity_type = ActivityType.ISSUE
                title = event.payload.issue.title
                url = event.payload.issue.html_url

            elif isinstance(event, GitHubPullRequestEvent):
                activity_type = ActivityType.PR
                title = '--'
                url = event.payload.pull_request.url

            elif isinstance(event, GitHubReviewEvent):
                activity_type = ActivityType.PR
                title = '--'
                url = event.payload.pull_request.url

            if activity_type:
                items.append(
                    ActivityData(
                        title=title,
                        url=url,
                        type=activity_type,
                        created_at=event.created_at,
                        repo_name=repo_name,
                    )
                )

        self.fill_missing_titles(username, items)

    def fill_missing_titles(self, username: str, items: list[ActivityData]):
        # Items with title '--' need fetching. Their 'url' is currently the API URL.
        missing_items = [item for item in items if item.title == '--' and item.url]

        if not missing_items:
            self.emit('user-activities-fetched', username, items, '')
            return

        # Context for tracking concurrent requests
        context = {
            'username': username,
            'items': items,
            'pending': len(missing_items),
        }

        log.info('Fetching missing titles for {} items', len(missing_items))

        for item in missing_items:
            api_url = item.url
            try:
                msg = Soup.Message.new(HTTPMethod.GET, api_url)
                msg.get_request_headers().append('User-Agent', self.user_agent)

                self.session.send_and_read_async(
                    msg,
                    GLib.PRIORITY_DEFAULT,
                    None,
                    self.on_detail_fetched,
                    (item, context),
                )
            except Exception as e:
                log.error('Error preparing fetch for {}: {}', api_url, e)
                self.check_pending_complete(context)

    def on_detail_fetched(self, session: Soup.Session, result: Gio.AsyncResult, user_data: tuple[ActivityData, dict]):
        item, context = user_data
        msg = session.get_async_result_message(result)

        try:
            bytes_data = session.send_and_read_finish(result)
            if msg.get_status() == 200:
                raw_data = bytes_data.get_data()
                # Decode as a partial dict to get title and html_url
                data = msgspec.json.decode(raw_data)
                if 'title' in data:
                    item.title = data['title']
                    # Add prefix if it was a review event?
                    # But we lost the event type context here (it is in item.type but that is just PR/ISSUE).
                    # Actually, for Review event, we wanted "Reviewed: ...".
                    # For now, let's just get the PR title.
                    # If we want to distinguish "Reviewed: ", we might need to store that intent or check original event.
                    # But ActivityData doesn't store original event type.
                    # Let's keep it simple: just the PR title.

                if 'html_url' in data:
                    item.url = data['html_url']
        except Exception as e:
            log.error('Error fetching details: {}', e)

        self.check_pending_complete(context)

    def check_pending_complete(self, context: dict):
        context['pending'] -= 1
        if context['pending'] <= 0:
            self.emit(
                'user-activities-fetched',
                context['username'],
                context['items'],
                '',
            )
