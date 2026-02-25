from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from gi.repository import GObject

from .consts import ActivityAction, Host, TaskType
from .schemas import GHIssueCommentEvent, GHIssuesEvent, GHPullRequestEvent, GHPullRequestReviewEvent


class ActivityType(StrEnum):
    ISSUE = 'Issue'
    PR = 'PR'


@dataclass
class RepoInfo:
    name: str
    owner: str
    host: Host = Host.GITHUB


@dataclass
class Account:
    host: Host
    username: str
    token: str | None = None


@dataclass
class InvolvementActivity:
    title: str
    api_url: str
    html_url: str
    task_type: TaskType
    action: ActivityAction
    author: str
    created_at: datetime
    repo_info: RepoInfo
    database_id: int | None = None
    number: int | None = None

    @property
    def repo_long_name(self) -> str:
        return f'{self.repo_info.owner}/{self.repo_info.name}' if self.repo_info.owner else self.repo_info.name

    @classmethod
    def from_github_event(
        cls, event: GHIssuesEvent | GHPullRequestEvent | GHPullRequestReviewEvent | GHIssueCommentEvent
    ) -> Self:
        match event:
            case GHPullRequestEvent(payload=p):
                task_type = TaskType.PR
                action = ActivityAction.CREATED_PR
                # This payload doesn't have title directly, so we set empty for now.
                title = ''
                api_url = p.pull_request.url
                html_url = p.pull_request.html_url
                database_id = p.pull_request.id
                number = p.pull_request.number
            case GHPullRequestReviewEvent(payload=p):
                task_type = TaskType.PR
                action = ActivityAction.REVIEWED_PR
                # This payload doesn't have title directly, so we set empty for now.
                title = ''
                api_url = p.pull_request.url
                html_url = p.pull_request.html_url
                database_id = p.pull_request.id
                number = p.pull_request.number
            case GHIssuesEvent(payload=p):
                task_type = TaskType.ISSUE
                action = ActivityAction.CREATED_ISSUE if p.action == 'opened' else ActivityAction.UPDATED_ISSUE
                title = p.issue.title
                api_url = p.issue.url
                html_url = p.issue.html_url
                database_id = p.issue.id
                number = p.issue.number
            case GHIssueCommentEvent(payload=p):
                if p.issue.pull_request:
                    task_type = TaskType.PR
                    action = ActivityAction.REVIEWED_PR
                else:
                    task_type = TaskType.ISSUE
                    action = ActivityAction.UPDATED_ISSUE
                title = p.issue.title
                api_url = p.issue.url
                html_url = p.issue.html_url
                database_id = p.issue.id
                number = p.issue.number
            case _:
                raise ValueError('Unsupported event type for InvolvementActivity')
        return cls(
            title=title,
            api_url=api_url,
            html_url=html_url,
            task_type=task_type,
            action=action,
            author=event.actor.login,
            created_at=event.created_at,
            repo_info=RepoInfo(
                name=event.repo.name,
                owner=event.repo.owner,
                host=Host.GITHUB,
            ),
            database_id=database_id,
            number=number,
        )


@dataclass
class ReportActivity(InvolvementActivity):
    pass


@dataclass
class GraphQLQueryContext:
    items: list[ActivityItem]
    repo_owner: str
    repo_name: str
    is_rate_limit: bool = False


class RepoItem(GObject.Object):
    __gtype_name__ = 'RepoItem'

    name = GObject.Property(type=str)
    owner = GObject.Property(type=str)
    host = GObject.Property(type=str, default='github')
    logo = GObject.Property(type=str, default='github')
    is_loading = GObject.Property(type=bool, default=False)
    display_name = GObject.Property(type=str)

    def __init__(self, name: str, owner: str = '', host: Host = Host.GITHUB, logo: str = 'github', **kwargs: Any):
        super().__init__(**kwargs)
        if not owner and '/' in name:
            owner, name = name.split('/', 1)

        self.owner = owner
        self.name = name
        self.host = host
        self.logo = logo
        self.is_loading = False
        self.display_name = f'{owner}/{name}' if owner else name


class AccountItem(GObject.Object):
    __gtype_name__ = 'AccountItem'

    username = GObject.Property(type=str)
    host = GObject.Property(type=str, default='github')
    token = GObject.Property(type=str)

    def __init__(self, username: str, host: Host = Host.GITHUB, token: str | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.username = username
        self.host = host
        self.token = token or ''


class ActivityItem(GObject.Object):
    __gtype_name__ = 'ActivityItem'

    title = GObject.Property(type=str)
    url = GObject.Property(type=str)
    task_type = GObject.Property(type=str)  # "issue" or "pr"
    action = GObject.Property(type=str)
    repo_long_name = GObject.Property(type=str)
    repo_name = GObject.Property(type=str)
    repo_owner = GObject.Property(type=str)
    created_at = GObject.Property(type=object)
    selected = GObject.Property(type=bool, default=True)
    display_text = GObject.Property(type=str)
    type_char = GObject.Property(type=str)
    author = GObject.Property(type=str)
    database_id = GObject.Property(type=GObject.TYPE_INT64)
    number = GObject.Property(type=int)
    api_url = GObject.Property(type=str)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.connect('notify::title', self.on_title_changed)

    def on_title_changed(self, *args):
        self.notify('display-title')

    @GObject.Property(type=str)
    def display_title(self) -> str:
        return self.title if self.title else '(No Title)'

    @GObject.Property(type=str)
    def icon_name(self) -> str:
        return 'checkbox-checked-symbolic' if self.selected else 'checkbox-symbolic'

    @classmethod
    def from_activity_data(cls, data: InvolvementActivity) -> Self:
        type_char = 'I' if data.task_type == TaskType.ISSUE else 'P'
        return cls(
            title=data.title or '',
            url=data.html_url,
            api_url=data.api_url,
            task_type=str(data.task_type),
            type_char=type_char,
            action=data.action.value,
            created_at=data.created_at,
            repo_name=data.repo_info.name,
            repo_long_name=data.repo_long_name,
            repo_owner=data.repo_info.owner,
            author=data.author,
            database_id=data.database_id,
            number=data.number or 0,
        )
