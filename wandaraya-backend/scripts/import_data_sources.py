""" purpose of this script is to import data sources into the database.
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

from app.models.data_sources import DataSource

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

DATA_DIRECTORY = (PROJECT_ROOT / "data" / "sources")

SOURCE_FILES = {
    "data_sources": DATA_DIRECTORY / "data_sources.csv",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",   
)

logger = logging.getLogger("wandaraya.data_source_import")

def parse_arguments() -> argparse.Namespace:
    
    parser = argparse.ArgumentParser(
        description=(
            "Import data sources into WANDARAYA Postgres."
        )
    )

    parser.add_argument(
        "--source",
        type=str,
        choices=SOURCE_FILES.keys(),
        default="data_sources",
        help="Source file to import (default: data_sources)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without committing changes to the database.",
    )

    return parser.parse_args()  

def import_to_database(sources:List[Dict[str, Any]], dry_run: bool = False) -> None:
    logger.info(f"Importing {len(sources)} data sources into the database.")
    engine=create_engine(DATABASE_URL)
    inserted_count = 0
    updated_count = 0


    try:
        with Session(engine) as session:
            for source_data in sources:
                source_name=source_data.get("name")

                if not source_name:
                    logger.warning("Skipping sources missing name")
                    continue

                existing_sources=session.execute(
                    select(DataSource).where(DataSource.name== source_name)
                ).scalar_one_or_none()

                if existing_sources:
                    logger.info(f"updating existing sources:{source_name}")
                    existing_sources.name=source_name
                    updated_count+=1
                else:
                    new_source=DataSource(
                        name=source_name,
                        source_type=source_data.get("source_type"),
                        base_url=source_data.get("base_url"),
                        api_endpoint=source_data.get("api_endpoint"),
                        trust_score=float(source_data.get("trust_score", 0.0)),
                        is_active=source_data.get("is_active", True),

                    )
                    session.add(new_source)
                    inserted_count+=1

            if dry_run:
                logger.info("Dry run enabled, rolling back changes.")
                session.rollback()
            else:
                session.commit()
                logger.info(f"Inserted {inserted_count} new data sources.")
                logger.info(f"Updated {updated_count} existing data sources.")

    except Exception as e:
        logger.error(f"Error occurred during import: {e}")
        session.rollback()
        raise

    finally:
        session.close()

    logger.info("Data sources import completed.")   
    logger.info(f"Total data sources processed: {len(sources)}")
    logger.info(f"Total data sources inserted: {inserted_count}")
    logger.info(f"Total data sources updated: {updated_count}")


def main() -> None:
    args=parse_arguments()
    source=args.source
    file_path=SOURCE_FILES.get(source)

    logger.info("========================================")

    logger.info(f"Importing data sources from: {file_path}")

    logger.info("========================================") 

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------
    logger.info(f"Loading data sources file: {file_path}")
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    sources=pd.read_csv(file_path).to_dict(orient="records")

    import_to_database(sources, dry_run=args.dry_run)

    logger.info("Data sources import process completed.")

    logger.info("========================================")

if __name__ == "__main__":
    main()