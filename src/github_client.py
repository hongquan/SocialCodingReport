import os
from datetime import datetime
from http import HTTPMethod
from urllib.parse import quote, urlencode

import gi
import msgspec


gi.require_version('Soup', '3.0')

from gi.repository import Gio, GLib, GObject, Soup
from logbook import Logger

from .consts import Host, TaskType
from .models import InvolvementActivity, RepoInfo


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

    def to_activity_data(self, repo_name: str) -> InvolvementActivity:
        type_enum = TaskType.PR if self.pull_request is not None else TaskType.ISSUE

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
            author=self.user.login or 'Unknown',
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

        items = [item.to_activity_data(repo_name) for item in items_data]

        self.emit('repo-activities-fetched', repo_name, items, '')
