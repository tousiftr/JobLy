# JobLy — Personal Job Portal + ATS Resume Tailoring Assistant

JobLy is a personal web app for your job search workflow as a **Data Analyst / Analytics Engineer / Data Engineer**, with specific focus on:

- Remote jobs you can do from Bangladesh
- International jobs with visa sponsorship / relocation
- ATS-optimized resume tailoring for each job post
- End-to-end application tracking

## Features

- **Job URL or JD Input**: Paste a job link or full job description
- **Keyword + Requirement Extraction**: Pull key ATS terms, tools, and requirements
- **Role-Specific Tailoring**: Resume guidance for Data Analyst, Analytics Engineer, and Data Engineer roles
- **ATS Action Checklist**: Practical optimization suggestions before applying
- **Job Tracker**: Save jobs, update status (Saved/Applied/Interview/Offer/Rejected), keep notes
- **Search Query Generator**: Built-in Google queries targeting major ATS boards (Ashby, Greenhouse, Lever, Workable, SmartRecruiters, Jobvite, Workday, Recruitee, Personio, BambooHR)

## Tech Stack

- Python + Flask
- SQLite (local persistent tracker DB: `jobly.db`)
- Requests + BeautifulSoup for optional URL content extraction

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open: <http://localhost:5000>

## API Endpoints

- `POST /api/analyze` — Analyze a job description or job URL
- `GET /api/tracker/jobs` — List tracked jobs
- `POST /api/tracker/jobs` — Save a tracked job
- `PATCH /api/tracker/jobs/<id>` — Update tracked job
- `DELETE /api/tracker/jobs/<id>` — Delete tracked job
- `GET /api/tracker/stats` — Tracker dashboard stats
- `GET /api/search-queries` — Generated Google query list

## Notes

- This app is designed for personal use and manual review.
- For best quality, always validate job details (especially visa sponsorship language) directly on the original posting.
