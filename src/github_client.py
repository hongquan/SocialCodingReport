import os
from collections.abc import Callable, Sequence
from datetime import datetime
from http import HTTPMethod
from urllib.parse import quote, urlencode

import gi
import msgspec


gi.require_version('Soup', '3.0')

from gi.repository import Gio, GLib, GObject, Soup
from logbook import Logger

from .models import ActivityData


log = Logger(__name__)


class GitHubError(msgspec.Struct):
    message: str | None = None
    documentation_url: str | None = None


class GitHubPullRequest(msgspec.Struct):
    url: str
    html_url: str


class GitHubItem(msgspec.Struct):
    title: str
    html_url: str
    created_at: datetime
    pull_request: GitHubPullRequest | None = None


class GitHubClient(GObject.Object):
    def __init__(self):
        super().__init__()
        self.session = Soup.Session.new()
        self.token = os.getenv('GITHUB_TOKEN')
        self.user_agent = 'SocialCodingReport/0.1'

    def fetch_activities(
        self,
        repo_name: str,
        since_date: datetime,
        callback: Callable[[Sequence[ActivityData], str | None], None],
    ):
        """
        Fetch issues and PRs updated since date.
        This is an async method wrapper.
        callback(activity_list, error)
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

        self.session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            None,
            self.on_fetch_complete,
            (callback, repo_name),
        )
        log.info('Fetching activities for {} since {}', repo_name, since_date)

    def on_fetch_complete(self, session: Soup.Session, result: Gio.AsyncResult, user_data: tuple[Callable, str]):
        callback, repo_name = user_data
        try:
            bytes_data = session.send_and_read_finish(result)
        except GLib.Error as e:
            log.error('Network error during fetch: {}', e)
            callback([], str(e))
            return

        raw_data = bytes_data.get_data()

        try:
            # Let's inspect first byte? '[' for list, '{' for dict.
            first_byte = raw_data.strip()[0:1]
            if first_byte == b'{':
                err_resp = msgspec.json.decode(raw_data, type=GitHubError)
                error_message = err_resp.message or 'Unknown error'
                log.error('GitHub API Error: {}', error_message)
                callback([], f'GitHub API Error: {error_message}')
                return

            items_data = msgspec.json.decode(raw_data, type=tuple[GitHubItem, ...])
        except (msgspec.DecodeError, UnicodeDecodeError) as e:
            log.error('JSON decode error: {}', e)
            callback([], str(e))
            return

        items = []
        for item in items_data:
            type_str = 'PR' if item.pull_request is not None else 'Issue'

            items.append(
                ActivityData(
                    title=item.title,
                    url=item.html_url,
                    type=type_str,
                    created_at=item.created_at,
                    repo_name=repo_name,
                )
            )

        callback(items, None)
