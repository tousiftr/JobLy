import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Job:
    title:            str
    company:          str
    location:         str
    url:              str
    ats_source:       str
    description:      str             = ""
    posted_date:      str             = ""
    posted_timestamp: Optional[float] = None
    has_visa:         bool            = False
    has_relocation:   bool            = False
    salary:           str             = ""
    job_type:         str             = ""
    remote:           bool            = False
    department:       str             = ""
    scraped_at:       str             = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    job_id: str = ""

    def __post_init__(self):
        if not self.job_id:
            raw = self.url.strip() if self.url.strip() else f"{self.title}|{self.company}|{self.location}"
            self.job_id = hashlib.md5(raw.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        known = set(cls.__dataclass_fields__)   # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})
