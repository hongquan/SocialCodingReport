from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, with_config

from .consts import GHEventType, GHState


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHMiniUser:
    __slots__ = ('login', 'avatar_url')
    login: str
    avatar_url: str


class GHMiniRepo(BaseModel):
    # Long name of the repository, e.g. `fossasia/eventyay`
    long_name: Annotated[str, Field(validation_alias='name')]

    @property
    def name(self):
        return self.long_name.split('/')[-1]

    @property
    def owner(self):
        return self.long_name.split('/')[0]


class GHUserEventCommon(BaseModel):
    actor: GHMiniUser
    repo: GHMiniRepo
    created_at: datetime

    @field_validator('created_at', mode='after')
    @classmethod
    def convert_to_vietnam_tz(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=ZoneInfo('UTC'))
            return v.astimezone(ZoneInfo('Asia/Ho_Chi_Minh'))
        return v


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHPushPayload:
    repository_id: int
    push_id: int
    ref: str


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHInPayloadPullRequest:
    url: str
    id: int
    number: int

    @property
    def html_url(self) -> str:
        # Convert from "https://api.github.com/repos/fossasia/eventyay/pulls/1823"
        # to "https://github.com/fossasia/eventyay/pull/1823"
        return self.url.replace('api.github.com/repos', 'github.com').replace('/pulls/', '/pull/')


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHPullRequestCreationPayload:
    action: str
    number: int
    pull_request: GHInPayloadPullRequest


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHPullRequestReviewPayload:
    pull_request: GHInPayloadPullRequest
    # We don't care review content, so we don't define more fields.


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHInPayloadIssue:
    url: str
    id: int
    number: int
    title: str
    state: GHState
    html_url: str
    pull_request: dict[str, Any] | None = None


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHIssueCommentPayload:
    action: str
    issue: GHInPayloadIssue


# Response from GitHub API


class GHPushEvent(GHUserEventCommon):
    type: Literal[GHEventType.PUSH]
    payload: GHPushPayload


class GHPullRequestEvent(GHUserEventCommon):
    type: Literal[GHEventType.PULL_REQUEST]
    payload: GHPullRequestCreationPayload


class GHPullRequestReviewEvent(GHUserEventCommon):
    type: Literal[GHEventType.PULL_REQUEST_REVIEW]
    payload: GHPullRequestReviewPayload


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHIssuePayload:
    action: str
    issue: GHInPayloadIssue


class GHIssuesEvent(GHUserEventCommon):
    type: Literal[GHEventType.ISSUES]
    payload: GHIssuePayload


class GHIssueCommentEvent(GHUserEventCommon):
    type: Literal[GHEventType.ISSUE_COMMENT]
    payload: GHIssueCommentPayload


class GHUncaredEvent(GHUserEventCommon):
    type: Literal[
        GHEventType.CREATE,
        GHEventType.DELETE,
        GHEventType.DISCUSSION,
        GHEventType.FORK,
        GHEventType.GOLLUM,
        GHEventType.MEMBER,
        GHEventType.PUBLIC,
        GHEventType.PULL_REQUEST_REVIEW_COMMENT,
        GHEventType.RELEASE,
        GHEventType.WATCH,
    ]


GHUserEvent = Annotated[
    GHPushEvent | GHPullRequestEvent | GHPullRequestReviewEvent | GHIssuesEvent | GHIssueCommentEvent | GHUncaredEvent,
    Field(discriminator='type'),
]


@dataclass
class GHGraphQLDatabaseIdNode:
    id: str  # GraphQL ID (node_id)
    databaseId: int
    number: int
    title: str | None = None


@dataclass
class GHGraphQLPageInfo:
    hasNextPage: bool
    startCursor: str | None = None
    endCursor: str | None = None


@dataclass
class GHGraphQLConnection:
    nodes: tuple[GHGraphQLDatabaseIdNode, ...]
    pageInfo: GHGraphQLPageInfo


@dataclass
class GHGraphQLRepository:
    issues: GHGraphQLConnection
    pullRequests: GHGraphQLConnection


@dataclass
class GHGraphQLRepositoryWrapper:
    repository: GHGraphQLRepository


@dataclass
@with_config(ConfigDict(extra='ignore'))
class GHSearchIssue:
    title: str
    html_url: str
    number: int
    id: int
    state: str
    repository_url: str  # e.g. "https://api.github.com/repos/owner/repo"
    draft: bool = False

    @property
    def repo_name(self) -> str:
        return self.repository_url.split('/')[-1]

    @property
    def repo_owner(self) -> str:
        return self.repository_url.split('/')[-2]

    @property
    def repo_long_name(self) -> str:
        return f'{self.repo_owner}/{self.repo_name}'


class GHSearchResponse(BaseModel):
    total_count: int
    incomplete_results: bool
    items: list[GHSearchIssue]


class GHGraphQLResponse(BaseModel):
    data: GHGraphQLRepositoryWrapper
