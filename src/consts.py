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


# Actions:
# - Created PR: If current user is the author of the PR.
# - Reviewed PR: If current user has reviewed or commented on the PR.
# - Created Issue: If current user is the author of the issue.
# We don't care about other actions.
class ActivityAction(StrEnum):
    CREATED = 'Created'
    REVIEWED = 'Reviewed'
