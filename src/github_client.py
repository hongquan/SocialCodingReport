import json
import os
from datetime import datetime
from http import HTTPMethod
from typing import Any
from urllib.parse import quote

import gi


gi.require_version('Soup', '3.0')

from gi.repository import Gio, GLib, GObject, Soup
from logbook import Logger
from pydantic import TypeAdapter

from .models import InvolvementActivity
from .schemas import (
    GHIssueCommentEvent,
    GHIssuesEvent,
    GHPullRequestEvent,
    GHPullRequestReviewEvent,
    GHSearchResponse,
    GHUserEvent,
)


log = Logger(__name__)


class GitHubClient(GObject.Object):
    __gsignals__ = {
        'user-activities-fetched': (GObject.SignalFlags.RUN_FIRST, None, (str, object, str)),
        'graphql-query-done': (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
        'authored-prs-fetched': (GObject.SignalFlags.RUN_FIRST, None, (str, object, str)),
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
        until_date: datetime,
        token: str | None = None,
    ):
        """
        Fetch public events for a user.
        Emits 'user-activities-fetched' (username, activity_list, error_message)
        """
        url = f'https://api.github.com/users/{quote(username)}/events'

        msg = Soup.Message.new(HTTPMethod.GET, url)
        msg.get_request_headers().append('User-Agent', self.user_agent)

        # Priority: explicit token > env var > none
        auth_token = token or self.token
        if auth_token:
            msg.get_request_headers().append('Authorization', f'Bearer {auth_token}')

        log.info('Fetching events for {} since {} until {}', username, since_date, until_date)
        self.session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            None,
            self.on_events_fetching_done,
            (username, since_date, until_date),
        )

    def on_events_fetching_done(
        self, session: Soup.Session, result: Gio.AsyncResult, user_data: tuple[str, datetime, datetime]
    ):
        username, since_date, until_date = user_data
        # Call `send_and_read_finish` first because it lets us know if there is a network error
        try:
            bytes_data = session.send_and_read_finish(result)
        except GLib.Error as e:
            log.error('Network error during fetch: {}', e)
            self.emit('user-activities-fetched', username, [], str(e))
            return
        # Call `get_async_result_message` to get the HTTP status code
        msg = session.get_async_result_message(result)
        status_code = msg.get_status()
        if status_code != Soup.Status.OK:
            log.error('GitHub API returned status code: {}', status_code)
            self.emit('user-activities-fetched', username, [], f'GitHub API Error: Status {status_code}')
            return

        raw_data = bytes_data.get_data()
        gh_events = TypeAdapter(list[GHUserEvent]).validate_json(raw_data)
        log.info('Fetched {} events for {}', len(gh_events), username)

        items = []
        for gh_event in gh_events:
            if gh_event.created_at < since_date:
                log.debug(
                    'Skipping event {} before since_date: {} < {}', gh_event.type, gh_event.created_at, since_date
                )
                continue
            if gh_event.created_at > until_date:
                log.debug('Skipping event {} after until_date: {} > {}', gh_event.type, gh_event.created_at, until_date)
                continue
            match gh_event:
                case GHPullRequestEvent() | GHPullRequestReviewEvent() | GHIssuesEvent() | GHIssueCommentEvent():
                    item = InvolvementActivity.from_github_event(gh_event)
                    items.append(item)
                case _:
                    # Ignore other event types
                    log.debug('Ignoring event type: {}', gh_event.type)
        self.emit('user-activities-fetched', username, items, '')
        log.info('Processed {} involvement activities for {}', len(items), username)

    def run_graphql_query(self, query: str, variables: dict[str, Any], token: str | None = None, user_data: Any = None):
        url = 'https://api.github.com/graphql'
        msg = Soup.Message.new(HTTPMethod.POST, url)
        msg.get_request_headers().append('User-Agent', self.user_agent)

        # Priority: explicit token > env var > none
        auth_token = token or self.token
        if auth_token:
            msg.get_request_headers().append('Authorization', f'Bearer {auth_token}')

        body = {'query': query, 'variables': variables}
        msg.set_request_body_from_bytes('application/json', GLib.Bytes.new(json.dumps(body).encode('utf-8')))

        log.info('Running GraphQL query...')
        self.session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            None,
            self.on_graphql_query_done,
            user_data,
        )

    def on_graphql_query_done(self, session: Soup.Session, result: Gio.AsyncResult, user_data: Any):
        try:
            bytes_data = session.send_and_read_finish(result)
        except GLib.Error as e:
            log.error('Network error during GraphQL fetch: {}', e)
            self.emit('graphql-query-done', '', user_data)
            return

        msg = session.get_async_result_message(result)
        status_code = msg.get_status()
        if status_code != Soup.Status.OK:
            log.error('GitHub API (GraphQL) returned status code: {}', status_code)
            self.emit('graphql-query-done', '', user_data)
            return

        # Emit raw string data, let receiver handle JSON parsing
        raw_data = bytes_data.get_data()
        if raw_data is None:
            self.emit('graphql-query-done', '', user_data)
        else:
            self.emit('graphql-query-done', raw_data.decode('utf-8'), user_data)

    def fetch_authored_prs(self, username: str, repos: list[str] | None = None, token: str | None = None):
        """
        Fetch open/draft pull requests authored by the user via REST Search API.
        Optionally filters by a list of repositories.
        Emits 'authored-prs-fetched' (username, pr_list, error_message)
        """
        query = f'author:{username} type:pr state:open'
        if repos:
            repo_filters = []
            current_query = query
            for repo in repos:
                repo_filter = f' repo:{repo}'
                # GitHub has a 256 char limit for search queries.
                # We stay conservative at 200 to be safe with URL encoding.
                if len(current_query) + len(repo_filter) < 200:
                    current_query += repo_filter
                    repo_filters.append(repo_filter)
                else:
                    log.debug('Query length limit reached, some repos will be filtered client-side')
                    break
            query = current_query

        url = f'https://api.github.com/search/issues?q={quote(query)}'

        msg = Soup.Message.new(HTTPMethod.GET, url)
        msg.get_request_headers().append('User-Agent', self.user_agent)

        auth_token = token or self.token
        if auth_token:
            msg.get_request_headers().append('Authorization', f'Bearer {auth_token}')

        log.info('Fetching authored PRs for user: {}', username)
        self.session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            None,
            self.on_authored_prs_fetching_done,
            username,
        )

    def on_authored_prs_fetching_done(self, session: Soup.Session, result: Gio.AsyncResult, username: str):
        try:
            bytes_data = session.send_and_read_finish(result)
        except GLib.Error as e:
            log.error('Network error during authored PRs fetch: {}', e)
            self.emit('authored-prs-fetched', username, [], str(e))
            return

        msg = session.get_async_result_message(result)
        status_code = msg.get_status()
        if status_code != Soup.Status.OK:
            log.error('GitHub API (Search) returned status code: {}', status_code)
            self.emit('authored-prs-fetched', username, [], f'GitHub API Error: Status {status_code}')
            return

        raw_data = bytes_data.get_data()
        try:
            response = GHSearchResponse.model_validate_json(raw_data)
            self.emit('authored-prs-fetched', username, response.items, '')
            log.info('Fetched {} authored PRs for {}', len(response.items), username)
        except Exception as e:
            log.error('Error parsing search response: {}', e)
            self.emit('authored-prs-fetched', username, [], str(e))
