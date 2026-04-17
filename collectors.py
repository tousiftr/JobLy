"""
Job collectors for various ATS platforms.
Each collector fetches jobs from a specific source and returns standardized job objects.
"""

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, list, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


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
            resp = self.session.get(
                "https://remotive.com/api/remote-jobs", timeout=self.timeout
            )
            resp.raise_for_status()
            jobs = []
            for row in resp.json().get("jobs", []):
                if not self._is_matching_title(row.get("title", "")):
                    continue

                description = BeautifulSoup(
                    row.get("description", ""), "lxml"
                ).get_text(" ", strip=True)
                jobs.append({
                    "title": row.get("title", ""),
                    "company": row.get("company_name", ""),
                    "location": row.get("candidate_required_location", "Remote"),
                    "job_url": row.get("url") or row.get("job_url") or "",
                    "source": "remotive",
                    "description": description,
                    "published_at": row.get("publication_date", ""),
                    "remote": True,
                    "visa_sponsorship": self._contains_keywords(
                        description, ["visa", "sponsor", "work permit"]
                    ),
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
            resp = self.session.get(
                "https://www.arbeitnow.com/api/job-board-api", timeout=self.timeout
            )
            resp.raise_for_status()
            jobs = []
            for row in resp.json().get("data", []):
                if not self._is_matching_title(row.get("title", "")):
                    continue

                description = BeautifulSoup(
                    row.get("description", ""), "lxml"
                ).get_text(" ", strip=True)
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
                        f"{location} {description}", ["remote", "anywhere", "global"]
                    ),
                    "visa_sponsorship": self._contains_keywords(
                        description, ["visa", "sponsor", "work permit"]
                    ),
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

    COMPANIES = [
        "aircall",
        "airbnb",
        "amazon",
        "anthropic",
        "braintrust",
        "candela",
        "clay",
        "figma",
        "generic",
        "github",
        "gitlab",
        "google",
        "guidepoint",
        "hugging-face",
        "intercom",
        "loom",
        "maker",
        "merge",
        "metabase",
        "netflix",
        "notion",
        "openai",
        "paddle",
        "panther",
        "reddit",
        "retool",
        "roboflow",
        "segment",
        "notion",
        "slack",
        "snowflake",
        "stripe",
        "supabase",
        "vercel",
    ]

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in self.COMPANIES[:10]:  # Start with 10 companies
            try:
                url = f"https://boards.greenhouse.io/api/v1/boards/{company}/jobs"
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 404:
                    continue

                resp.raise_for_status()
                for job in resp.json().get("jobs", []):
                    if not self._is_matching_title(job.get("title", "")):
                        continue

                    # Extract location from locations array
                    locations = job.get("offices", [])
                    location = (
                        ", ".join([l.get("name", "") for l in locations])
                        or "Not specified"
                    )
                    description = "\n".join(
                        [req.get("description", "") for req in job.get("content", [])]
                    )

                    all_jobs.append({
                        "title": job.get("title", ""),
                        "company": company.replace("-", " ").title(),
                        "location": location,
                        "job_url": job.get("absolute_url", ""),
                        "source": "greenhouse",
                        "description": description,
                        "published_at": job.get("updated_at", ""),
                        "remote": "remote" in location.lower(),
                        "visa_sponsorship": self._contains_keywords(
                            description, ["visa", "sponsor", "work permit"]
                        ),
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

    COMPANIES = [
        "a16z",
        "airbnb",
        "amazon",
        "anthropic",
        "github",
        "gitlab",
        "google",
        "hugging-face",
        "loom",
        "notion",
        "openai",
        "retool",
        "stripe",
        "vercel",
    ]

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in self.COMPANIES[:8]:  # Start with 8 companies
            try:
                url = f"https://api.lever.co/v0/postings/companies/{company}"
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 404:
                    continue

                resp.raise_for_status()
                for job in resp.json():
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
                        "visa_sponsorship": self._contains_keywords(
                            description, ["visa", "sponsor", "work permit"]
                        ),
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

    COMPANIES = ["company", "anthropic", "vercel", "stripe", "figma"]

    def collect(self) -> list[dict[str, Any]]:
        all_jobs = []
        for company in self.COMPANIES[:5]:
            try:
                url = f"https://api.ashbyhq.com/posting.listByCompanyName"
                payload = {"companyName": company, "includeCompanyName": True}
                resp = self.session.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()

                for job in resp.json().get("results", []):
                    title = job.get("title", "")
                    if not self._is_matching_title(title):
                        continue

                    description = job.get("descriptionHtml", "")
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
                        "visa_sponsorship": self._contains_keywords(
                            description, ["visa", "sponsor", "work permit"]
                        ),
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
