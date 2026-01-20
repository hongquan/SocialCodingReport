import os
from datetime import datetime
from http import HTTPMethod
from urllib.parse import quote

import gi


gi.require_version('Soup', '3.0')

from gi.repository import Gio, GLib, GObject, Soup
from logbook import Logger
from pydantic import TypeAdapter

from .models import InvolvementActivity
from .schemas import GHIssuesEvent, GHPullRequestEvent, GHPullRequestReviewEvent, GHUserEvent


log = Logger(__name__)


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
                case GHPullRequestEvent() | GHPullRequestReviewEvent() | GHIssuesEvent():
                    item = InvolvementActivity.from_github_event(gh_event)
                    items.append(item)
                case _:
                    # Ignore other event types
                    log.debug('Ignoring event type: {}', gh_event.type)
        self.emit('user-activities-fetched', username, items, '')
        log.info('Processed {} involvement activities for {}', len(items), username)
