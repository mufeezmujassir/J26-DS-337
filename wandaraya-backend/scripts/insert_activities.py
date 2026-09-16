""" purpose of this script is to insert activities into the database.
"""




from __future__ import annotations
import logging
import os
import sys
from typing import Any, Dict, List
from pathlib import Path
import argparse

import pandas as pd


from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).parent.parent

if PROJECT_ROOT not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.models.activities import Activity

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")
DATA_DIRECTORY = (PROJECT_ROOT / "data" / "activities")

SOURCE_FILES = {
    "activities": DATA_DIRECTORY / "activities.csv",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("wandaraya.activity_import")

def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Import Sri Lankan tourist activities into WANDARAYA Postgres."
        )
    )

    parser.add_argument(
        "--source",
        type=str,
        choices=SOURCE_FILES.keys(),
        default="activities",
        help="Source file to import (default: activities)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without committing changes to the database.",
    )

    return parser.parse_args()

def import_to_database(activities: List[Dict[str, Any]], dry_run: bool = False) -> None:
    logger.info(f"Importing {len(activities)} activities into the database.")
    engine = create_engine(DATABASE_URL)
    inserted_count = 0
    updated_count = 0

    try:
        with Session(engine) as session:
            for activity_data in activities:
                activity_name = activity_data.get("name")
                if not activity_name:
                    logger.warning("Skipping activity with missing name.")
                    continue

                existing_activity = session.execute(
                    select(Activity).where(Activity.name == activity_name)
                ).scalar_one_or_none()

                if existing_activity:
                    # Update existing activity
                    logger.info(f"Updating existing activity: {activity_name}")
                    existing_activity.name = activity_name
                    existing_activity.description = activity_data.get("description")
                    existing_activity.is_active = activity_data.get("is_active", True)
                    updated_count += 1
                else:
                    # Insert new activity
                    new_activity = Activity(
                        name=activity_name,
                        description=activity_data.get("description"),
                        is_active=activity_data.get("is_active", True),
                    )
                    session.add(new_activity)
                    inserted_count += 1

            if dry_run:
                logger.warning("Dry run enabled. Rolling back changes.")
                session.rollback()
            else:
                session.commit()
                logger.info(f"Inserted {inserted_count} new activities.")
                logger.info(f"Updated {updated_count} existing activities.")

    except Exception as e:
        logger.exception("An error occurred while importing activities.")
        raise e
    finally:
        engine.dispose()

    logger.info("Activity import process completed.")
    logger.info(f"Total activities processed: {len(activities)}")
    logger.info(f"Total activities inserted: {inserted_count}")
    logger.info(f"Total activities updated: {updated_count}")   


def main()->None:
    args=parse_arguments()
    source=args.source

    file_path = SOURCE_FILES.get(source)

    logger.info("========================================")

    logger.info("WANDARAYA Activity Import")

    logger.info("Source: %s", source)

    logger.info("========================================")

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------
    logger.info(f"Loading activity file: {file_path}")
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    activities = pd.read_csv(file_path).to_dict(orient="records")

    import_to_database(activities, dry_run=args.dry_run)

    logger.info("Activity import process completed.")
if __name__ == "__main__":
    main()