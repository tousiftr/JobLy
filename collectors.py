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
    """Fetch jobs from Greenhouse boards"""

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in GREENHOUSE_COMPANIES[:50]:  # Use config list
            try:
                url = f"https://boards.greenhouse.io/api/v1/boards/{company}/jobs"
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
    """Fetch jobs from Lever boards"""

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in LEVER_COMPANIES[:50]:  # Use config list
            try:
                # Fixed API endpoint: correct is /v0/postings/{slug}?mode=json not /v0/postings/companies/{slug}
                url = f"https://api.lever.co/v0/postings/{company}?mode=json"
                resp = safe_get(url, self.session)
                if resp is None:
                    continue

                for job in resp.json().get("postings", []):
                    if not self._is_matching_title(job.get("text", "")):
                        continue

                    description = job.get("descriptionPlain", "")
                    locations = job.get("locations", [])
                    location = (
                        ", ".join([l.get("name", "") for l in locations])
                        or "Not specified"
                    )

                    all_jobs.append({
                        "title": job.get("text", ""),
                        "company": job.get("owner", {}).get("name", company),
                        "location": location,
                        "job_url": job.get("urls", {}).get("show", ""),
                        "source": "lever",
                        "description": description,
                        "published_at": job.get("createdAt", ""),
                        "remote": "remote" in location.lower(),
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
    """Fetch jobs from Ashby boards"""

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in ASHBY_COMPANIES[:50]:  # Use config list, skip dummy "company" value
            if company.lower() == "company":
                continue
            try:
                # Fixed endpoint: correct is /posting-api/job-board/{slug} not posting.listByCompanyName
                url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
                resp = safe_get(url, self.session, params={"includeCompanyName": True})
                if resp is None:
                    continue

                for job in resp.json().get("results", []) or resp.json().get("postings", []):
                    title = job.get("title", "")
                    if not self._is_matching_title(title):
                        continue

                    description = job.get("descriptionHtml", "") or job.get("description", "")
                    description = strip_html(description) if isinstance(description, str) else ""
                    location_objs = job.get("locations", [])
                    location = (
                        ", ".join([l.get("name", "") for l in location_objs])
                        or "Not specified"
                    )

                    all_jobs.append({
                        "title": title,
                        "company": job.get("companyName", company),
                        "location": location,
                        "job_url": job.get("url", ""),
                        "source": "ashby",
                        "description": description,
                        "published_at": job.get("createdAt", ""),
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
