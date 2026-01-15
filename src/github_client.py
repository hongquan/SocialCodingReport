import os
from datetime import datetime
from http import HTTPMethod
from urllib.parse import quote, urlencode

import gi
import msgspec


gi.require_version('Soup', '3.0')

from gi.repository import Gio, GLib, GObject, Soup
from logbook import Logger

from .consts import ActivityAction, Host, TaskType
from .models import ActivityData, RepoInfo


log = Logger(__name__)


class GitHubError(msgspec.Struct):
    message: str | None = None
    documentation_url: str | None = None


class GitHubPullRequest(msgspec.Struct):
    url: str
    html_url: str


class GitHubUser(msgspec.Struct):
    login: str | None = None


class GitHubItem(msgspec.Struct):
    title: str
    html_url: str
    created_at: datetime
    user: GitHubUser
    pull_request: GitHubPullRequest | None = None

    def to_activity_data(self, repo_name: str, current_user: str | None = None) -> ActivityData:
        type_enum = TaskType.PR if self.pull_request is not None else TaskType.ISSUE

        # Determine action
        if current_user and self.user.login and self.user.login == current_user:
            action = ActivityAction.CREATED
        else:
            action = ActivityAction.REVIEWED

        # Parse repo_name "owner/name"
        if '/' in repo_name:
            owner, name = repo_name.split('/', 1)
        else:
            owner, name = '', repo_name

        repo_info = RepoInfo(name=name, owner=owner, host=Host.GITHUB)

        return ActivityData(
            title=self.title,
            url=self.html_url,
            task_type=type_enum,
            action=action,
            created_at=self.created_at,
            repo_info=repo_info,
        )


class GitHubClient(GObject.Object):
    __gsignals__ = {
        'repo-activities-fetched': (GObject.SignalFlags.RUN_FIRST, None, (str, object, str)),
    }

    def __init__(self):
        super().__init__()
        self.session = Soup.Session.new()
        self.token = os.getenv('GITHUB_TOKEN')
        self.user_agent = 'SocialCodingReport/0.1'
        self.current_user: str | None = None
        self.fetch_user()

    def fetch_user(self):
        url = 'https://api.github.com/user'
        msg = Soup.Message.new(HTTPMethod.GET, url)
        msg.get_request_headers().append('User-Agent', self.user_agent)
        if self.token:
            msg.get_request_headers().append('Authorization', f'token {self.token}')

        # We assume this finishes quickly.
        # Ideally we wait for this before processing others, but for simplicity we rely on async.
        self.session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, None, self.on_fetch_user_complete, None)

    def on_fetch_user_complete(self, session, result, data):
        try:
            bytes_data = session.send_and_read_finish(result)
            raw_data = bytes_data.get_data()
            user_data = msgspec.json.decode(raw_data, type=GitHubUser)
            self.current_user = user_data.login or 'Unknown'
            log.info('Authenticated as: {}', self.current_user)
        except (GLib.Error, msgspec.DecodeError) as e:
            log.error('Error fetching user: {}', e)

    def fetch_activities(
        self,
        repo_name: str,
        since_date: datetime,
    ):
        """
        Fetch issues and PRs updated since date.
        This is an async method wrapper.
        Emits 'repo-activities-fetched' (repo_name, activity_list, error_message)
        """
        # GitHub API ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ
        base_url = f'https://api.github.com/repos/{quote(repo_name)}/issues'
        params = {
            'since': f'{since_date:%Y-%m-%dT%H:%M:%S%z}',
            'state': 'all',
        }
        url = f'{base_url}?{urlencode(params)}'

        msg = Soup.Message.new(HTTPMethod.GET, url)
        msg.get_request_headers().append('User-Agent', self.user_agent)
        if self.token:
            msg.get_request_headers().append('Authorization', f'token {self.token}')

        log.info('Fetching activities for {} since {}', repo_name, since_date)
        self.session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            None,
            self.on_fetch_complete,
            repo_name,
        )

    def on_fetch_complete(self, session: Soup.Session, result: Gio.AsyncResult, repo_name: str):
        try:
            bytes_data = session.send_and_read_finish(result)
        except GLib.Error as e:
            log.error('Network error during fetch: {}', e)
            self.emit('repo-activities-fetched', repo_name, [], str(e))
            return

        raw_data = bytes_data.get_data()

        try:
            # Let's inspect first byte? '[' for list, '{' for dict.
            first_byte = raw_data.strip()[0:1]
            if first_byte == b'{':
                err_resp = msgspec.json.decode(raw_data, type=GitHubError)
                error_message = err_resp.message or 'Unknown error'
                log.error('GitHub API Error: {}', error_message)
                self.emit('repo-activities-fetched', repo_name, [], f'GitHub API Error: {error_message}')
                return

            items_data = msgspec.json.decode(raw_data, type=tuple[GitHubItem, ...])
        except (msgspec.DecodeError, UnicodeDecodeError) as e:
            log.error('JSON decode error: {}', e)
            self.emit('repo-activities-fetched', repo_name, [], str(e))
            return

        items = [item.to_activity_data(repo_name, self.current_user) for item in items_data]

        self.emit('repo-activities-fetched', repo_name, items, '')
