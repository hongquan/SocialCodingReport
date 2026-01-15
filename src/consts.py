from __future__ import annotations

from enum import StrEnum


SHORT_NAME = 'socialcodingreport'
APP_ID = 'vn.ququ.SocialCodingReport'


class Host(StrEnum):
    GITHUB = 'github'
    GITLAB = 'gitlab'


class TaskType(StrEnum):
    ISSUE = 'Issue'
    PR = 'PR'


class ActivityAction(StrEnum):
    CREATED = 'Created'
    REVIEWED = 'Reviewed'
