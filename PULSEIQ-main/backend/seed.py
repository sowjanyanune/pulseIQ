"""Seed fictional student records directly into the configured PostgreSQL database."""

from datetime import date, timedelta
import random
from .db import SCHEMAS


def generate(count=1000, reference=None):
    rng = random.Random(42)
    today = reference or date.today()
    periods = [
        (today - timedelta(days=37)).isoformat(),
        (today - timedelta(days=7)).isoformat(),
    ]
    departments = ["Computer Science", "Electronics", "Mechanical", "Business"]
    data = {k: [] for k in SCHEMAS}
    for i in range(1, count + 1):
        sid = f"DEMO{i:04}"
        data["students"].append(
            dict(
                student_id=sid,
                department=departments[(i - 1) % 4],
                semester=4 if i % 2 else 6,
            )
        )
        for period in periods:
            clamp = lambda v: round(max(0, min(100, v)), 1)
            marks = clamp(rng.gauss(70, 16))
            values = {
                "academic": dict(marks_pct=marks, backlog_count=int(marks < 45)),
                "attendance": dict(
                    classes_attended=rng.randint(24, 40), classes_held=40
                ),
                "lms": dict(
                    assignments_completed=rng.randint(5, 10), assignments_assigned=10
                ),
                "placement": dict(
                    aptitude_pct=clamp(rng.gauss(68, 16)),
                    coding_pct=clamp(marks + rng.gauss(-10, 20)),
                    interview_pct=clamp(rng.gauss(70, 15)),
                ),
                "skills": dict(
                    technical_pct=clamp(rng.gauss(70, 15)),
                    communication_pct=clamp(rng.gauss(72, 12)),
                ),
                "engagement": dict(
                    activities_completed=rng.randint(0, 5), activities_available=5
                ),
                "feedback": dict(
                    support_requested=i % 17 == 0,
                    support_category="Academic" if i % 17 == 0 else "None",
                ),
            }
            if i <= 7:
                values = {
                    "academic": dict(marks_pct=80, backlog_count=0),
                    "attendance": dict(classes_attended=36, classes_held=40),
                    "lms": dict(assignments_completed=7, assignments_assigned=10),
                    "placement": dict(aptitude_pct=40, coding_pct=40, interview_pct=40),
                    "skills": dict(technical_pct=60, communication_pct=60),
                    "engagement": dict(activities_completed=1, activities_available=2),
                    "feedback": dict(support_requested=False, support_category="None"),
                }
                if i == 2:
                    values["academic"] = dict(marks_pct=42, backlog_count=1)
                    values["attendance"]["classes_attended"] = 26
                    values["placement"] = dict(
                        aptitude_pct=80, coding_pct=80, interview_pct=80
                    )
                if i == 3:
                    values["academic"] = dict(marks_pct=45, backlog_count=1)
                if i == 4:
                    values["placement"] = dict(
                        aptitude_pct=80, coding_pct=85, interview_pct=80
                    )
                if i == 5:
                    values["placement"] = dict(
                        aptitude_pct=None, coding_pct=None, interview_pct=None
                    )
                if i == 6:
                    values["engagement"] = dict(
                        activities_completed=0, activities_available=0
                    )
                if i == 7:
                    values["feedback"] = dict(
                        support_requested=True, support_category="Other"
                    )
            elif i % 29 == 0:
                values["skills"]["communication_pct"] = None
            for source, fields in values.items():
                data[source].append(dict(student_id=sid, period_end=period, **fields))
    return data
