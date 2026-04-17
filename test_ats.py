#!/usr/bin/env python
import json
from app import app, calculate_ats_match_score

# Test the function directly
print("Testing calculate_ats_match_score directly:")
score, cat, strong = calculate_ats_match_score(
    "Data Analyst SQL Python Tableau Power BI Remote visa sponsorship",
    "Data Analyst",
    []
)
print(f"  Result: score={score}, category={cat}, strong={strong}")

# Test via Flask test client
print("\nTesting via Flask client:")
with app.test_client() as client:
    response = client.post(
        '/api/analyze',
        data=json.dumps({
            "job_text": "Data Analyst SQL Python Tableau Power BI Remote visa sponsorship",
            "target_role": "Data Analyst",
            "user_skills": ""
        }),
        content_type='application/json'
    )
    data = response.get_json()
    print(f"  Response keys: {sorted(data.keys())}")
    print(f"  Has ats_score: {'ats_score' in data}")
    if 'ats_score' in data:
        print(f"  ATS Score: {data['ats_score']}")
    else:
        print(f"  Keys present: {list(data.keys())[:5]}...")
