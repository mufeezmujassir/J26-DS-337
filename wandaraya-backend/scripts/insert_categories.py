""""
purpose of this script is to insert categories into the database.

usage:
python3 scripts/insert_categories.py
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

from app.models.categories import Category

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

DATA_DIRECTORY = (PROJECT_ROOT / "data" / "categories")

SOURCE_FILES = {
    "categories": DATA_DIRECTORY / "categories.csv",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("wandaraya.category_import")


def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Import Sri Lankan tourist categories and their "
            "boundaries into WANDARAYA Postgres."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        choices=[
            "categories",
        ],
        help="categories dataset to import.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and process data without "
            "committing database changes."
        ),
    )

    return parser.parse_args()


def import_to_database(categories: List[Dict[str, Any]], dry_run: bool = False) -> None:
    logger.info("Starting import of categories into the database.")

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    inserted_count = 0
    updated_count = 0

    try:
        with Session(engine) as session:
            for category_data in categories:
                name = str(category_data["name"]).strip()
                description = category_data.get("description")
                is_active = str(category_data.get("is_active", True)).strip().lower() in {
                    "true", "1", "yes", "y"
                }

                existing = session.scalar(
                    select(Category).where(Category.name == name)
                )

                if existing:
                    logger.info("Category '%s' already exists. Updating existing record.", name)
                    existing.description = description
                    existing.is_active = is_active
                    updated_count += 1
                else:
                    logger.info("Inserting new category '%s'.", name)
                    session.add(Category(
                        name=name,
                        description=description,
                        is_active=is_active,
                    ))
                    inserted_count += 1

            if dry_run:
                logger.warning("DRY RUN enabled. Rolling back all changes.")
                session.rollback()
            else:
                session.commit()
                logger.info(
                    "Import completed. %d categories inserted, %d categories updated.",
                    inserted_count,
                    updated_count,
                )
    except Exception:
        logger.exception("An error occurred during the import process. Rolling back changes.")
        raise
    finally:
        engine.dispose()


    logger.info("Import process finished.")
    logger.info(f"Total categories inserted: {inserted_count}")
    logger.info(f"Total categories updated: {updated_count}")
    logger.info(f"Total categories processed: {inserted_count + updated_count}")


def main()->None:
    args = parse_arguments()
    source = args.source

    file_path = SOURCE_FILES[
        source
    ]

    logger.info(
        "========================================"
    )

    logger.info(
        "WANDARAYA Category Import"
    )

    logger.info(
        "Source: %s",
        source,
    )

    logger.info(
        "========================================"
    )

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------
    logger.info(f"Loading category file: {file_path}")
    if not file_path.exists():
        raise FileNotFoundError(f"Category file not found: {file_path}")

    categories = pd.read_csv(file_path)

    # -----------------------------------------------------
    # Import
    # -----------------------------------------------------     
    import_to_database(
        categories=categories.to_dict(orient="records"),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()