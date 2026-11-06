from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shrike.adapters.persistence.demo import demo_id
from shrike.adapters.persistence.models import ReviewExecution, ReviewFinding

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE installations SET github_id=710001 WHERE github_id=710002",
        "UPDATE installations SET github_id=0",
        "UPDATE installations SET status='unknown'",
        "UPDATE installations SET account_type='invalid'",
        "UPDATE repositories SET github_id=810001 WHERE github_id=810002",
        "UPDATE repositories SET status='unknown'",
        "UPDATE pull_requests SET github_id=910001 WHERE github_id=910002",
        "UPDATE pull_requests SET number=0",
        "UPDATE pull_requests SET head_sha='not-a-sha'",
        "UPDATE review_jobs SET installation_id="
        "(SELECT id FROM installations WHERE github_id=710002) "
        "WHERE id=:job",
        "UPDATE review_jobs SET pull_request_id="
        "(SELECT id FROM pull_requests WHERE github_id=910002) "
        "WHERE id=:job",
        "UPDATE review_jobs SET state='unknown' WHERE id=:job",
        "UPDATE review_jobs SET finished_at=NULL WHERE id=:job",
        "UPDATE review_jobs SET policy_digest='invalid' WHERE id=:job",
        "UPDATE review_jobs SET started_at=created_at - interval '1 second' WHERE id=:job",
        "UPDATE review_findings SET line_start=0",
        "UPDATE review_findings SET line_end=line_start - 1",
        "UPDATE review_findings SET severity='unknown'",
        "UPDATE review_findings SET message=''",
        "UPDATE review_findings SET fingerprint='invalid'",
        "UPDATE review_executions SET attempt=0",
        "UPDATE review_executions SET input_tokens=-1",
        "UPDATE review_executions SET finished_at=NULL WHERE state='completed'",
        "DELETE FROM installations WHERE github_id=710001",
        "DELETE FROM repositories WHERE github_id=810001",
        "DELETE FROM pull_requests WHERE github_id=910001",
    ],
)
def test_database_rejects_invalid_rows_and_cross_owner_links(
    session: Session, statement: str
) -> None:
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(text(statement), {"job": demo_id("completed")})


@pytest.mark.parametrize(
    "path", ["../secret.py", "/etc/passwd", "src/../../x.py", "C:/x.py", "x\\y.py"]
)
def test_unsafe_finding_paths_are_rejected(session: Session, path: str) -> None:
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(text("UPDATE review_findings SET path=:path"), {"path": path})


@pytest.mark.parametrize(
    "table,columns,where",
    [
        (
            "pull_requests",
            "repository_id,github_id,number,state,draft,base_sha,head_sha",
            "github_id=910001",
        ),
        (
            "review_jobs",
            "installation_id,repository_id,pull_request_id,base_sha,head_sha,policy_digest,"
            "state,created_at,started_at,finished_at",
            "id=:job",
        ),
        (
            "review_findings",
            "job_id,fingerprint,source,severity,rule_id,path,line_start,line_end,message",
            "id=:finding",
        ),
        (
            "review_executions",
            "job_id,attempt,state,started_at,finished_at,duration_ms,input_tokens,output_tokens",
            "id=:execution",
        ),
    ],
)
def test_uniqueness_constraints(session: Session, table: str, columns: str, where: str) -> None:
    # All identifiers are trusted test constants. Only parameter values vary.
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(
            text(
                f"INSERT INTO {table} (id,{columns}) SELECT :new_id,{columns} "
                f"FROM {table} WHERE {where}"
            ),
            {
                "new_id": uuid4(),
                "job": demo_id("completed"),
                "finding": demo_id("finding-0"),
                "execution": demo_id("execution-0"),
            },
        )


def test_base_revision_is_part_of_analysis_identity(session: Session) -> None:
    session.execute(
        text(
            "INSERT INTO review_jobs (id,installation_id,repository_id,pull_request_id,"
            "base_sha,head_sha,"
            "policy_digest,state,created_at,started_at,finished_at) "
            "SELECT :new_id,installation_id,repository_id,pull_request_id,"
            ":base,head_sha,policy_digest,"
            "state,created_at,started_at,finished_at FROM review_jobs WHERE id=:job"
        ),
        {"new_id": uuid4(), "base": "e" * 40, "job": demo_id("completed")},
    )


def test_pr_numbers_are_unique_only_within_their_repository(session: Session) -> None:
    session.execute(text("UPDATE pull_requests SET number=42 WHERE github_id=910002"))
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(
            text(
                "INSERT INTO pull_requests (id,repository_id,github_id,number,state,draft,"
                "base_sha,head_sha) "
                "SELECT :id,repository_id,999999,number,state,draft,base_sha,head_sha "
                "FROM pull_requests WHERE github_id=910001"
            ),
            {"id": uuid4()},
        )


def test_deleting_job_cascades_only_its_findings_and_execution_metadata(session: Session) -> None:
    session.execute(text("DELETE FROM review_jobs WHERE id=:job"), {"job": demo_id("completed")})
    assert session.scalar(select(func.count()).select_from(ReviewFinding)) == 0
    assert session.scalar(select(func.count()).select_from(ReviewExecution)) == 3
