"""
Job collectors for various ATS platforms.
Each collector fetches jobs from a specific source and returns standardized job objects.
"""

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from utils import safe_get, has_visa, has_relocation, strip_html
from config import GREENHOUSE_COMPANIES, LEVER_COMPANIES, ASHBY_COMPANIES


class JobCollector(ABC):
    """Base class for all job collectors"""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "JobLy/1.0"})

    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """
        Collect jobs from this source.
        Must return list of dicts with keys:
        title, company, location, job_url, description, published_at, remote, visa_sponsorship
        """
        pass

    def _is_recent(self, date_str: Optional[str], days: int = 7) -> bool:
        """Check if date is within N days"""
        if not date_str:
            return True
        try:
            if isinstance(date_str, str):
                # Try ISO format
                if "T" in date_str:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    # Try common date formats
                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                        try:
                            dt = datetime.strptime(date_str, fmt)
                            break
                        except:
                            continue
                    else:
                        return True

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
            return dt >= cutoff
        except Exception:
            return True

    def _contains_keywords(self, text: str, keywords: list[str]) -> bool:
        """Case-insensitive substring search"""
        lower = text.lower()
        return any(kw.lower() in lower for kw in keywords)


class RemotiveCollector(JobCollector):
    """Fetch jobs from Remotive API"""

    def collect(self) -> list[dict[str, Any]]:
        try:
            resp = safe_get("https://remotive.com/api/remote-jobs", self.session)
            if resp is None:
                return []

            jobs = []
            for row in resp.json().get("jobs", []):
                if not self._is_matching_title(row.get("title", "")):
                    continue

                description = strip_html(row.get("description", ""))
                jobs.append({
                    "title": row.get("title", ""),
                    "company": row.get("company_name", ""),
                    "location": row.get("candidate_required_location", "Remote"),
                    "job_url": row.get("url") or row.get("job_url") or "",
                    "source": "remotive",
                    "description": description,
                    "published_at": row.get("publication_date", ""),
                    "remote": True,
                    "visa_sponsorship": has_visa(description),
                    "relocation_support": has_relocation(description),
                })
                if len(jobs) >= 100:
                    break
            return jobs
        except Exception as e:
            print(f"RemotiveCollector error: {e}")
            return []

    def _is_matching_title(self, title: str) -> bool:
        terms = [
            "analyst",
            "engineer",
            "data",
            "analytics",
            "bi",
            "business intelligence",
        ]
        return any(t in title.lower() for t in terms)


class ArbeitnowCollector(JobCollector):
    """Fetch jobs from Arbeitnow API"""

    def collect(self) -> list[dict[str, Any]]:
        try:
            resp = safe_get("https://www.arbeitnow.com/api/job-board-api", self.session)
            if resp is None:
                return []

            jobs = []
            for row in resp.json().get("data", []):
                if not self._is_matching_title(row.get("title", "")):
                    continue

                description = strip_html(row.get("description", ""))
                location = row.get("location", "Not specified")
                jobs.append({
                    "title": row.get("title", ""),
                    "company": row.get("company_name", ""),
                    "location": location,
                    "job_url": row.get("url", ""),
                    "source": "arbeitnow",
                    "description": description,
                    "published_at": row.get("created_at", ""),
                    "remote": self._contains_keywords(
                        f"{location} {description}", ["remote", "anywhere", "global", "worldwide"]
                    ),
                    "visa_sponsorship": has_visa(description),
                    "relocation_support": has_relocation(description),
                })
                if len(jobs) >= 100:
                    break
            return jobs
        except Exception as e:
            print(f"ArbeitnowCollector error: {e}")
            return []

    def _is_matching_title(self, title: str) -> bool:
        terms = [
            "analyst",
            "engineer",
            "data",
            "analytics",
            "bi",
            "business intelligence",
        ]
        return any(t in title.lower() for t in terms)


class GreenhouseCollector(JobCollector):
    """Fetch jobs from Greenhouse boards via the official boards-api host."""

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in GREENHOUSE_COMPANIES[:50]:  # Use config list
            try:
                # Correct endpoint: boards-api.greenhouse.io (not boards.greenhouse.io/api)
                url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
                resp = safe_get(url, self.session)
                if resp is None:
                    continue

                for job in resp.json().get("jobs", []):
                    if not self._is_matching_title(job.get("title", "")):
                        continue

                    # Extract location from locations array
                    locations = job.get("offices", [])
                    location = (
                        ", ".join([l.get("name", "") for l in locations])
                        or "Not specified"
                    )
                    # content is a string with HTML, not a list
                    content = job.get("content", "")
                    description = strip_html(content) if isinstance(content, str) else ""

                    all_jobs.append({
                        "title": job.get("title", ""),
                        "company": company.replace("-", " ").title(),
                        "location": location,
                        "job_url": job.get("absolute_url", ""),
                        "source": "greenhouse",
                        "description": description,
                        "published_at": job.get("updated_at", ""),
                        "remote": "remote" in location.lower(),
                        "visa_sponsorship": has_visa(description),
                        "relocation_support": has_relocation(description),
                    })
                    if len(all_jobs) >= 100:
                        return all_jobs
            except Exception as e:
                print(f"GreenhouseCollector error for {company}: {e}")
                continue

        return all_jobs

    def _is_matching_title(self, title: str) -> bool:
        terms = [
            "analyst",
            "engineer",
            "data",
            "analytics",
            "bi",
            "business intelligence",
        ]
        return any(t in title.lower() for t in terms)


class LeverCollector(JobCollector):
    """Fetch jobs from Lever boards.

    The Lever public API returns a JSON array at the root — NOT a dict with a
    `postings` key. Fields per posting: text, hostedUrl, applyUrl, categories
    (team/location/commitment), createdAt, description, descriptionPlain.
    """

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in LEVER_COMPANIES[:50]:
            try:
                url = f"https://api.lever.co/v0/postings/{company}?mode=json"
                resp = safe_get(url, self.session)
                if resp is None:
                    continue

                data = resp.json()
                postings = data if isinstance(data, list) else data.get("postings", [])

                for job in postings:
                    title = job.get("text", "")
                    if not self._is_matching_title(title):
                        continue

                    description = job.get("descriptionPlain") or strip_html(job.get("description", ""))
                    categories = job.get("categories", {}) or {}
                    location = categories.get("location") or "Not specified"

                    all_jobs.append({
                        "title": title,
                        "company": company.replace("-", " ").title(),
                        "location": location,
                        "job_url": job.get("hostedUrl") or job.get("applyUrl", ""),
                        "source": "lever",
                        "description": description,
                        "published_at": job.get("createdAt", ""),
                        "remote": "remote" in str(location).lower(),
                        "visa_sponsorship": has_visa(description),
                        "relocation_support": has_relocation(description),
                    })
                    if len(all_jobs) >= 100:
                        return all_jobs
            except Exception as e:
                print(f"LeverCollector error for {company}: {e}")
                continue

        return all_jobs

    def _is_matching_title(self, title: str) -> bool:
        terms = [
            "analyst",
            "engineer",
            "data",
            "analytics",
            "bi",
            "business intelligence",
        ]
        return any(t in title.lower() for t in terms)


class AshbyCollector(JobCollector):
    """Fetch jobs from Ashby boards via GraphQL.

    The REST `posting-api` endpoint is flaky / locked behind a feature flag; the
    board frontend hits a GraphQL endpoint at `jobs.ashbyhq.com/api/non-user-graphql`
    which works for any public-facing Ashby board.
    """

    GRAPHQL_URL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
    GRAPHQL_QUERY = """
        query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
          jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
            jobPostings {
              id
              title
              locationName
              employmentType
              secondaryLocations { locationName }
            }
          }
        }
    """

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in ASHBY_COMPANIES[:50]:
            if company.lower() == "company":
                continue
            try:
                payload = {
                    "operationName": "ApiJobBoardWithTeams",
                    "variables": {"organizationHostedJobsPageName": company},
                    "query": self.GRAPHQL_QUERY,
                }
                resp = self.session.post(
                    self.GRAPHQL_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                board = (data.get("data") or {}).get("jobBoard") or {}
                postings = board.get("jobPostings") or []

                for job in postings:
                    title = job.get("title", "")
                    if not self._is_matching_title(title):
                        continue

                    job_id = job.get("id", "")
                    primary_loc = job.get("locationName") or ""
                    secondary = job.get("secondaryLocations") or []
                    extra_locs = [l.get("locationName", "") for l in secondary if l.get("locationName")]
                    location = ", ".join([primary_loc] + extra_locs) if primary_loc else "Not specified"

                    # Public job URL convention
                    job_url = f"https://jobs.ashbyhq.com/{company}/{job_id}" if job_id else ""

                    # GraphQL payload doesn't include description; title-only scoring
                    description = title

                    all_jobs.append({
                        "title": title,
                        "company": company.replace("-", " ").title(),
                        "location": location,
                        "job_url": job_url,
                        "source": "ashby",
                        "description": description,
                        "published_at": "",
                        "remote": "remote" in location.lower(),
                        "visa_sponsorship": has_visa(description),
                        "relocation_support": has_relocation(description),
                    })
                    if len(all_jobs) >= 100:
                        return all_jobs
            except Exception as e:
                print(f"AshbyCollector error for {company}: {e}")
                continue

        return all_jobs

    def _is_matching_title(self, title: str) -> bool:
        terms = [
            "analyst",
            "engineer",
            "data",
            "analytics",
            "bi",
            "business intelligence",
        ]
        return any(t in title.lower() for t in terms)


# Registry of all collectors
ALL_COLLECTORS = [
    RemotiveCollector(),
    ArbeitnowCollector(),
    GreenhouseCollector(),
    LeverCollector(),
    AshbyCollector(),
]
