"""
Background scheduler for daily job scraping at 6 PM.
Uses APScheduler for reliable cron-based scheduling.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from job_engine import engine


def store_jobs_in_db(jobs: list[dict[str, Any]], db_path: str) -> int:
    """Store scraped jobs into raw_jobs table"""
    stored_count = 0

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        now = datetime.now(tz=timezone.utc).isoformat()

        for job in jobs:
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO raw_jobs (
                        job_id, title, company, location, job_url, source,
                        description, remote, visa_sponsorship, relocation_support,
                        ats_score, ats_category, role_match, matched_skills,
                        top_keywords, published_at, scraped_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.get("job_id", ""),
                        job.get("title", ""),
                        job.get("company", ""),
                        job.get("location", ""),
                        job.get("job_url", ""),
                        job.get("source", ""),
                        job.get("description", ""),
                        1 if job.get("remote") else 0,
                        1 if job.get("visa_sponsorship") else 0,
                        1 if job.get("relocation_support") else 0,
                        job.get("ats_score"),
                        job.get("ats_category"),
                        job.get("role_match", ""),
                        json.dumps(job.get("matched_skills", [])),
                        json.dumps(job.get("top_keywords", [])),
                        job.get("published_at", ""),
                        now,
                        now,
                        now,
                    ),
                )
                stored_count += 1
            except Exception as e:
                print(f"Error storing job {job.get('title')}: {e}")
                continue

        conn.commit()
        conn.close()
        print(f"Stored {stored_count} jobs in database")
    except Exception as e:
        print(f"Database error: {e}")

    return stored_count


def scrape_jobs_daily(db_path: str) -> None:
    """
    Daily scraping task.
    Fetches jobs from all collectors and stores in database.
    """
    print(f"\n{'=' * 60}")
    print(f"Starting daily job scrape at {datetime.now(tz=timezone.utc).isoformat()}")
    print(f"{'=' * 60}")

    try:
        # Run scrape
        jobs = engine.scan()
        print(f"\nCollected {len(jobs)} unique jobs")

        # Store in database
        stored = store_jobs_in_db(jobs, db_path)
        print(f"Stored {stored} jobs in database")

        # Log progress
        progress = engine.get_progress()
        print(f"\nCollector Progress:")
        for source, info in progress.items():
            status = "SUCCESS" if info.get("success") else "FAILED"
            count = info.get("count", 0)
            print(f"  {source}: {count} jobs ({status})")

        print(f"{'=' * 60}\n")

    except Exception as e:
        print(f"Error during scrape: {e}")
        print(f"{'=' * 60}\n")


def start_scheduler(db_path: str, hour: int = 18, minute: int = 0) -> BackgroundScheduler:
    """
    Start the background scheduler for daily 6 PM (18:00) scraping.

    Args:
        db_path: Path to JobLy database
        hour: Hour of day to run (default 18 = 6 PM)
        minute: Minute of hour (default 0)

    Returns:
        BackgroundScheduler instance
    """
    scheduler = BackgroundScheduler()

    # Schedule daily job scraping at specified time
    scheduler.add_job(
        scrape_jobs_daily,
        "cron",
        hour=hour,
        minute=minute,
        args=[db_path],
        id="daily_job_scrape",
        name="Daily job scrape",
        replace_existing=True,
    )

    scheduler.start()
    print(f"Scheduler started: Daily scrape at {hour:02d}:{minute:02d} UTC")

    return scheduler


def stop_scheduler(scheduler: Optional[BackgroundScheduler]) -> None:
    """Stop the background scheduler"""
    if scheduler and scheduler.running:
        scheduler.shutdown()
        print("Scheduler stopped")
