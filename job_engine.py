import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from collectors import ALL_COLLECTORS
from utils import calculate_ats_match_score, extract_keywords, infer_role_scores


class JobEngine:
    """Orchestrates job collection from multiple sources"""

    def __init__(self):
        self._lock = threading.Lock()
        self._progress: Dict[str, dict] = {}

    def scan(self, on_progress: Optional[callable] = None) -> List[Dict[str, Any]]:
        """
        Scan all collectors in parallel and return deduplicated jobs.
        Returns list of dicts ready to store in raw_jobs table.
        """
        print(f"Starting scan across {len(ALL_COLLECTORS)} collectors")
        self._progress.clear()
        all_jobs: List[Dict[str, Any]] = []
        results: Dict[str, List[Dict[str, Any]]] = {}

        def collect_from_source(collector):
            """Run a single collector in thread"""
            try:
                source_name = collector.__class__.__name__
                jobs = collector.collect()

                with self._lock:
                    results[source_name] = jobs
                    self._progress[source_name] = {"done": True, "count": len(jobs), "success": True}

                if on_progress:
                    on_progress(source_name, len(jobs), True)

                print(f"  {source_name}: {len(jobs)} jobs")
            except Exception as e:
                with self._lock:
                    self._progress[collector.__class__.__name__] = {"done": True, "count": 0, "success": False, "error": str(e)}
                print(f"  {collector.__class__.__name__}: ERROR - {e}")

        # Run all collectors in parallel
        threads = [
            threading.Thread(target=collect_from_source, args=(collector,), daemon=True)
            for collector in ALL_COLLECTORS
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=120)

        # Aggregate results
        for jobs in results.values():
            all_jobs.extend(jobs)

        # Deduplicate by (title, company, location)
        unique_jobs = self._dedup(all_jobs)

        # Sort by published date (newest first)
        sorted_jobs = sorted(
            unique_jobs,
            key=lambda j: j.get("published_at", ""),
            reverse=True
        )

        # Calculate ATS scores for each job (against all 3 roles, pick best)
        for job in sorted_jobs:
            description = job.get("description", "")
            if description:
                try:
                    scores = {}
                    for role in ["Data Analyst", "Analytics Engineer", "Data Engineer"]:
                        score, category, is_strong = calculate_ats_match_score(description, role, [])
                        scores[role] = (score, category, is_strong)

                    best_role = max(scores, key=lambda r: scores[r][0])
                    best_score, best_category, best_strong = scores[best_role]

                    job["ats_score"] = best_score
                    job["ats_category"] = best_category
                    job["role_match"] = best_role
                    job["matched_skills"] = extract_keywords(description, top_n=15)
                    job["top_keywords"] = extract_keywords(description, top_n=30)
                except Exception as e:
                    job["ats_score"] = None
                    job["ats_category"] = None
                    job["role_match"] = ""
                    job["matched_skills"] = []
                    job["top_keywords"] = []
                    print(f"  ATS scoring failed for {job.get('title')}: {e}")
            else:
                job["ats_score"] = None
                job["ats_category"] = None
                job["role_match"] = ""
                job["matched_skills"] = []
                job["top_keywords"] = []

        print(f"Scan complete: {len(sorted_jobs)} unique jobs from {len(all_jobs)} total")
        return sorted_jobs

    def get_progress(self) -> Dict[str, dict]:
        """Get current scan progress"""
        with self._lock:
            return dict(self._progress)

    @staticmethod
    def _dedup(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate jobs by content hash"""
        seen: Dict[str, Dict[str, Any]] = {}

        for job in jobs:
            # Create a unique ID from title + company + location
            job_id = hashlib.md5(
                f"{job.get('title', '')}|{job.get('company', '')}|{job.get('location', '')}"
                .encode()
            ).hexdigest()

            if job_id not in seen:
                job["job_id"] = job_id
                seen[job_id] = job

        return list(seen.values())


# Global engine instance
engine = JobEngine()
