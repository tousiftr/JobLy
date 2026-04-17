import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import logging
import threading
from datetime import datetime, timezone
from typing import List, Dict, Callable, Optional

from models import Job
from collectors import ALL_COLLECTORS
from config import JOBS_CACHE_FILE, SCAN_META_FILE

logger = logging.getLogger(__name__)


class JobEngine:
    def __init__(self):
        self._lock     = threading.Lock()
        self._progress: Dict[str, dict] = {}

    def scan(self, on_progress: Optional[Callable] = None) -> List[Job]:
        logger.info("Starting scan across %d collectors", len(ALL_COLLECTORS))
        self._progress.clear()
        raw_jobs: List[Job] = []
        results:  Dict[str, List[Job]] = {}

        def run(cls):
            collector = cls()
            jobs = collector.safe_collect()
            with self._lock:
                results[cls.name] = jobs
                self._progress[cls.name] = {"done": True, "count": len(jobs)}
            if on_progress:
                on_progress(cls.name, len(jobs))

        threads = [threading.Thread(target=run, args=(cls,), daemon=True)
                   for cls in ALL_COLLECTORS]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

        for jobs in results.values():
            raw_jobs.extend(jobs)

        unique      = self._dedup(raw_jobs)
        sorted_jobs = sorted(unique, key=lambda j: j.posted_timestamp or 0, reverse=True)
        self._save(sorted_jobs)
        logger.info("Scan complete — %d unique jobs", len(sorted_jobs))
        return sorted_jobs

    def load_cache(self) -> List[Job]:
        try:
            with open(JOBS_CACHE_FILE, encoding="utf-8") as f:
                return [Job.from_dict(d) for d in json.load(f)]
        except Exception:
            return []

    def load_meta(self) -> Optional[dict]:
        try:
            with open(SCAN_META_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_progress(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._progress)

    @staticmethod
    def _dedup(jobs: List[Job]) -> List[Job]:
        seen: Dict[str, Job] = {}
        for j in jobs:
            if j.job_id not in seen:
                seen[j.job_id] = j
        return list(seen.values())

    @staticmethod
    def _save(jobs: List[Job]):
        try:
            with open(JOBS_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump([j.to_dict() for j in jobs], f, default=str, indent=2)
            meta = {
                "timestamp":  datetime.now(tz=timezone.utc).isoformat(),
                "count":      len(jobs),
                "collectors": len(ALL_COLLECTORS),
            }
            with open(SCAN_META_FILE, "w", encoding="utf-8") as f:
                json.dump(meta, f)
        except Exception as e:
            logger.error("Cache save failed: %s", e)


engine = JobEngine()
