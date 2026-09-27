"""
feedback_log.py
-----------------
Captures whether the farmer followed a recommendation and what happened.
This is the seed of field-calibration: over time, comparing "system said X,
farmer did Y, outcome was Z" across many farmers is what turns generic ICAR
thresholds into locally-calibrated ones — directly closing the gap named
in the original problem statement.

For the hackathon prototype this logs to a local CSV. In production this
would write to a proper database and feed a recalibration job.
"""

import csv
import os
from datetime import datetime

LOG_PATH = "feedback_log.csv"

FIELDNAMES = ["timestamp", "crop", "stage", "category", "recommendation",
              "followed", "outcome_note"]


def log_feedback(crop: str, stage: str, category: str, recommendation: str,
                  followed: bool, outcome_note: str = "") -> None:
    file_exists = os.path.isfile(LOG_PATH)
    with open(LOG_PATH, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "crop": crop, "stage": stage, "category": category,
            "recommendation": recommendation, "followed": followed,
            "outcome_note": outcome_note,
        })


def get_follow_rate(category: str) -> float:
    """Simple stand-in for a recalibration signal: what fraction of past
    recommendations in this category were actually followed? A production
    system would use this to widen/tighten thresholds per region/crop."""
    if not os.path.isfile(LOG_PATH):
        return 1.0  # no history yet — assume full trust
    total, followed_count = 0, 0
    with open(LOG_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["category"] == category:
                total += 1
                if row["followed"] == "True":
                    followed_count += 1
    return round(followed_count / total, 2) if total else 1.0