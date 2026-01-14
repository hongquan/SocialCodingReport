from __future__ import annotations

from datetime import datetime
from typing import Any, Self

import msgspec
from gi.repository import GLib, GObject


class ActivityData(msgspec.Struct):
    title: str
    url: str
    type: str
    created_at: datetime
    repo_name: str


class ActivityItem(GObject.Object):
    __gtype_name__ = 'ActivityItem'

    title = GObject.Property(type=str)
    url = GObject.Property(type=str)
    type = GObject.Property(type=str)  # "issue" or "pr"
    created_at = GObject.Property(type=object)
    repo_name = GObject.Property(type=str)
    selected = GObject.Property(type=bool, default=True)
    display_text = GObject.Property(type=str)

    def __init__(
        self,
        title: str,
        url: str,
        type: str,
        created_at: datetime,
        repo_name: str,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.title = title
        self.url = url
        self.type = type
        self.created_at = created_at
        self.repo_name = repo_name
        self.selected = True
        self.display_text = f'<b>[{repo_name}]</b> {GLib.markup_escape_text(title)}'

    @classmethod
    def from_activity_data(cls, data: ActivityData) -> Self:
        return cls(
            title=data.title,
            url=data.url,
            type=data.type,
            created_at=data.created_at,
            repo_name=data.repo_name,
        )


class RepoItem(GObject.Object):
    __gtype_name__ = 'RepoItem'

    name = GObject.Property(type=str)

    def __init__(self, name: str, **kwargs: Any):
        super().__init__(**kwargs)
        self.name = name
