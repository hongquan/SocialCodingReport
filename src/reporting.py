from collections.abc import Sequence
from dataclasses import dataclass

from jinja2 import Environment, FileSystemLoader

from .consts import DATA_DIR, ActivityAction, TaskType
from .models import ReportActivity


@dataclass
class ActivityGrouping:
    repo_shortname: str
    created_prs: list[ReportActivity]
    reviewed_prs: list[ReportActivity]
    created_issues: list[ReportActivity]


def group_activities_by_repo(activities: Sequence[ReportActivity]) -> dict[str, ActivityGrouping]:
    """
    Group activities by:
    - Repo shortname (without owner info)
    - Created pull request
    - Reviewed pull request
    - Created issue
    """
    grouped = {}
    for activity in activities:
        if activity.repo_long_name not in grouped:
            grouped[activity.repo_long_name] = ActivityGrouping(
                repo_shortname=activity.repo_long_name.split('/')[-1],
                created_prs=[],
                reviewed_prs=[],
                created_issues=[],
            )
        if activity.task_type == TaskType.PR:
            if activity.action == ActivityAction.CREATED_PR:
                grouped[activity.repo_long_name].created_prs.append(activity)
            elif activity.action == ActivityAction.REVIEWED_PR:
                grouped[activity.repo_long_name].reviewed_prs.append(activity)
        elif activity.task_type == TaskType.ISSUE:
            if activity.action == ActivityAction.CREATED_ISSUE:
                grouped[activity.repo_long_name].created_issues.append(activity)

    return grouped


def generate_report(
    yesterday_activities: Sequence[ReportActivity], today_activities: Sequence[ReportActivity] = ()
) -> str:
    env = Environment(loader=FileSystemLoader(str(DATA_DIR)))
    template = env.get_template('report.html.jinja')
    yesterday = group_activities_by_repo(yesterday_activities)
    today = group_activities_by_repo(today_activities)
    return template.render(yesterday=yesterday, today=today)
