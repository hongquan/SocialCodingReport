from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from .paths import PKGDATADIR


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
    CREATED_ISSUE = 'created-issue'
    CREATED_PR = 'created-pr'
    REVIEWED_PR = 'reviewed-pr'
    UPDATED_ISSUE = 'updated-issue'


class GHState(StrEnum):
    OPEN = 'open'
    CLOSED = 'closed'


# Ref: https://docs.github.com/en/rest/activity/events?apiVersion=2022-11-28#list-public-events-for-a-user
class GHEventType(StrEnum):
    CREATE = 'CreateEvent'
    DELETE = 'DeleteEvent'
    DISCUSSION = 'DiscussionEvent'
    ISSUES = 'IssuesEvent'
    ISSUE_COMMENT = 'IssueCommentEvent'
    FORK = 'ForkEvent'
    GOLLUM = 'GollumEvent'
    MEMBER = 'MemberEvent'
    PUBLIC = 'PublicEvent'
    PUSH = 'PushEvent'
    PULL_REQUEST = 'PullRequestEvent'
    PULL_REQUEST_REVIEW_COMMENT = 'PullRequestReviewCommentEvent'
    PULL_REQUEST_REVIEW = 'PullRequestReviewEvent'
    COMMIT_COMMENT = 'CommitCommentEvent'
    RELEASE = 'ReleaseEvent'
    WATCH = 'WatchEvent'


class DateNamedRange(StrEnum):
    TODAY = 'today'
    YESTERDAY = 'yesterday'
    LAST_7_DAYS = 'last-7-days'


# Data directory
# Supports both source run and installed layout.
DATA_DIR = Path(PKGDATADIR) / 'data'
