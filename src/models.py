from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from gi.repository import GLib, GObject

from .consts import ActivityAction, Host, TaskType


@dataclass
class RepoInfo:
    name: str
    owner: str
    host: Host = Host.GITHUB


@dataclass
class Account:
    host: Host
    username: str


@dataclass
class InvolvementActivity:
    title: str
    url: str
    task_type: TaskType
    author: str
    created_at: datetime
    repo_info: RepoInfo

    @property
    def repo_name(self) -> str:
        return f'{self.repo_info.owner}/{self.repo_info.name}' if self.repo_info.owner else self.repo_info.name


@dataclass
class ReportActivity(InvolvementActivity):
    action: ActivityAction


class RepoItem(GObject.Object):
    __gtype_name__ = 'RepoItem'

    name = GObject.Property(type=str)
    owner = GObject.Property(type=str)
    host = GObject.Property(type=str, default='github')
    logo = GObject.Property(type=str, default='github')
    is_loading = GObject.Property(type=bool, default=False)
    display_name = GObject.Property(type=str)

    def __init__(self, owner: str, name: str, host: Host = Host.GITHUB, logo: str = 'github', **kwargs: Any):
        super().__init__(**kwargs)
        self.owner = owner
        self.name = name
        self.host = host
        self.logo = logo
        self.is_loading = False
        self.display_name = f'{owner}/{name}'


class AccountItem(GObject.Object):
    __gtype_name__ = 'AccountItem'

    username = GObject.Property(type=str)
    host = GObject.Property(type=str, default='github')

    def __init__(self, username: str, host: Host = Host.GITHUB, **kwargs: Any):
        super().__init__(**kwargs)
        self.username = username
        self.host = host


class ActivityItem(GObject.Object):
    __gtype_name__ = 'ActivityItem'

    title = GObject.Property(type=str)
    url = GObject.Property(type=str)
    task_type = GObject.Property(type=str)  # "issue" or "pr"
    action = GObject.Property(type=str)
    created_at = GObject.Property(type=object)
    repo_name = GObject.Property(type=str)
    selected = GObject.Property(type=bool, default=True)
    display_text = GObject.Property(type=str)
    short_repo_name = GObject.Property(type=str)
    type_char = GObject.Property(type=str)
    author = GObject.Property(type=str)

    def __init__(
        self,
        title: str,
        url: str,
        task_type: str,
        action: str,
        created_at: datetime,
        repo_name: str,
        author: str = '',
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.title = title
        self.url = url
        self.task_type = task_type
        self.action = action
        self.created_at = created_at
        self.repo_name = repo_name
        self.author = author
        self.selected = True
        self.display_text = f'<b>[{repo_name}]</b> {GLib.markup_escape_text(title)}'
        self.short_repo_name = repo_name.split('/')[-1] if '/' in repo_name else repo_name
        self.type_char = 'P' if task_type == 'PR' else 'I'

    @classmethod
    def from_activity_data(cls, data: InvolvementActivity, viewing_username: str) -> Self:
        if data.author == viewing_username:
            action = ActivityAction.CREATED
        else:
            action = ActivityAction.REVIEWED

        return cls(
            title=data.title,
            url=data.url,
            task_type=data.task_type,
            action=action,
            created_at=data.created_at,
            repo_name=data.repo_name,
            author=data.author,
        )
