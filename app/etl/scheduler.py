import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.etl.collectors.traffic import TrafficCollector
from app.etl.collectors.weather import WeatherCollector
from app.etl.collectors.incidents import IncidentCollector
from app.etl.collectors.construction import ConstructionCollector

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("smartflow.etl.scheduler")

async def run_collector(collector_instance: any, name: str):
    """Wrapper to run a collector and catch top-level exceptions."""
    logger.info(f"Triggering scheduled job: {name}")
    try:
        await collector_instance.run()
        logger.info(f"Completed scheduled job: {name}")
    except Exception as e:
        logger.error(f"Scheduled job {name} failed with error: {e}", exc_info=True)

async def main():
    """
    Main entry point for the SmartFlow ETL scheduler.
    Orchestrates periodic polling of all external traffic intelligence feeds.
    """
    logger.info("Initializing SmartFlow ETL Scheduler...")

    # Initialize collectors
    traffic = TrafficCollector()
    weather = WeatherCollector()
    incidents = IncidentCollector()
    construction = ConstructionCollector()

    scheduler = AsyncIOScheduler()

    # 1. Traffic Telemetry: High frequency (Every 5 minutes)
    scheduler.add_job(
        run_collector, 
        'interval', 
        minutes=5, 
        args=[traffic, "Traffic"],
        id="traffic_ingestion",
        next_run_time=datetime.now() # Run immediately on start
    )

    # 2. Weather Snapshots: Medium frequency (Every 15 minutes)
    scheduler.add_job(
        run_collector, 
        'interval', 
        minutes=15, 
        args=[weather, "Weather"],
        id="weather_ingestion",
        next_run_time=datetime.now()
    )

    # 3. Incidents: Medium frequency (Every 10 minutes)
    scheduler.add_job(
        run_collector, 
        'interval', 
        minutes=10, 
        args=[incidents, "Incidents"],
        id="incident_ingestion",
        next_run_time=datetime.now()
    )

    # 4. Construction: Low frequency (Every 60 minutes)
    scheduler.add_job(
        run_collector, 
        'interval', 
        minutes=60, 
        args=[construction, "Construction"],
        id="construction_ingestion",
        next_run_time=datetime.now()
    )

    scheduler.start()
    logger.info("Scheduler started. Press Ctrl+C to exit.")

    try:
        # Keep the event loop running indefinitely
        while True:
            await asyncio.sleep(1000)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
