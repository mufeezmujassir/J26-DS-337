"""Offline-only stable ordering preview for experimental context scores."""
from __future__ import annotations
import argparse, asyncio, json
from pathlib import Path
from app.database import AsyncSessionLocal
from app.holiday_event.context_scoring import ContextScoreRequest, HolidayEventContextScoringService

async def main(args):
    ids = [int(item) for item in args.attraction_ids.split(",") if item.strip()]
    interests = [item.strip() for item in args.interests.split(",") if item.strip()]
    async with AsyncSessionLocal() as db:
        response = await HolidayEventContextScoringService(db).score(ContextScoreRequest(travel_date=args.travel_date, attraction_ids=ids, interests=interests))
    original = {value: index for index, value in enumerate(ids)}
    ordered = sorted(response.scores, key=lambda item: (item.context_suitability_score is None, -(item.context_suitability_score or 0), original[item.attraction_id]))
    output = {"mode":"offline_preview","original_order":ids,"preview_order":[item.attraction_id for item in ordered],"scores":[item.model_dump(mode="json") for item in ordered],"production_ranking_changed":False,"postgresql_writes":False,"qdrant_writes":False}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True); Path(args.output).write_text(json.dumps(output, indent=2)+"\n",encoding="utf-8"); print(json.dumps(output,indent=2))

if __name__ == "__main__":
    from datetime import date
    parser=argparse.ArgumentParser(); parser.add_argument("--travel-date",type=date.fromisoformat,required=True); parser.add_argument("--attraction-ids",required=True); parser.add_argument("--interests",default=""); parser.add_argument("--output",default="data/reports/stage12_3d3_ranking_preview.json"); args=parser.parse_args(); asyncio.run(main(args))
