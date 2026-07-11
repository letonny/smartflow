import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any

import asyncpg
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("smartflow.backend.main")

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres"
)

class DatabaseManager:
    """
    Manages the lifetime of the PostgreSQL database connection pool.
    Utilizes asyncpg for high-performance concurrent queries.
    """
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Initializes the database connection pool."""
        try:
            logger.info("Initializing asyncpg database connection pool...")
            self.pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=int(os.getenv("DB_MIN_POOL_SIZE", "5")),
                max_size=int(os.getenv("DB_MAX_POOL_SIZE", "20")),
                command_timeout=float(os.getenv("DB_COMMAND_TIMEOUT", "30.0")),
                max_inactive_connection_lifetime=300.0
            )
            logger.info("Database connection pool successfully initialized.")
        except Exception as e:
            logger.critical(f"Failed to initialize database connection pool: {e}", exc_info=True)
            raise RuntimeError("Database connection pool initialization failed.") from e

    async def disconnect(self) -> None:
        """Gracefully closes all connections in the database connection pool."""
        if self.pool:
            logger.info("Closing database connection pool...")
            await self.pool.close()
            logger.info("Database connection pool closed.")
            self.pool = None

# Single instance of the database manager
db_manager = DatabaseManager(dsn=DATABASE_URL)

async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """
    FastAPI dependency injection provider for acquiring a database connection.
    Ensures the connection is returned to the pool after the request is finished.
    """
    if not db_manager.pool:
        logger.critical("Database connection pool is not initialized.")
        raise RuntimeError("Database connection pool is not initialized.")
    
    async with db_manager.pool.acquire() as connection:
        yield connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown lifecycles.
    """
    # Startup actions
    await db_manager.connect()
    yield
    # Shutdown actions
    await db_manager.disconnect()


# Initialize the FastAPI Application
app = FastAPI(
    title="SmartFlow API",
    description="Real-time traffic intelligence and predictive analytics platform API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# CORS Middleware Configuration
# Explicitly allowing Next.js dev server, production origins, and local interfaces
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept"],
    expose_headers=["Content-Length", "X-Response-Time"]
)

# --- Global Exception Handlers ---

@app.exception_handler(asyncpg.PostgresError)
async def postgres_exception_handler(request: Request, exc: asyncpg.PostgresError):
    """Handles low-level PostgreSQL/PostGIS execution failures."""
    logger.error(f"Database query error occurred on path '{request.url.path}': {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "A database operation error occurred.",
            "error_type": "DatabaseError",
            "message": str(exc) if os.getenv("API_DEBUG") == "true" else "Internal server error"
        }
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handles application-level validation or domain constraint violations."""
    logger.warning(f"Validation error on path '{request.url.path}': {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": "Invalid argument or parameter value supplied.",
            "error_type": "ValidationError",
            "message": str(exc)
        }
    )

@app.exception_handler(Exception)
async def global_catch_all_handler(request: Request, exc: Exception):
    """Final fallback error handler for unexpected runtime bugs."""
    logger.critical(f"Unhandled system error on path '{request.url.path}': {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected server error occurred.",
            "error_type": "InternalServerError"
        }
    )


# --- Health & Status Endpoints ---

@app.get("/api/health", response_model=Dict[str, Any], tags=["System"])
async def health_check() -> Dict[str, Any]:
    """
    Performs basic diagnostics on the service and database connection.
    """
    db_ok = False
    db_message = "Not Connected"
    
    if db_manager.pool:
        try:
            # Acquire a connection and run a simple ping query
            async with db_manager.pool.acquire() as conn:
                res = await conn.fetchval("SELECT 1;")
                if res == 1:
                    db_ok = True
                    db_message = "Connected and responding"
        except Exception as e:
            logger.error(f"Database health check failed: {e}", exc_info=True)
            db_message = f"Error: {str(e)}"
            
    status_code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "online" if db_ok else "degraded",
            "environment": os.getenv("APP_ENV", "development"),
            "services": {
                "api": "healthy",
                "database": {
                    "status": "healthy" if db_ok else "unhealthy",
                    "details": db_message
                }
            }
        }
    )

@app.get("/", tags=["System"])
async def root() -> Dict[str, str]:
    """
    Root landing redirect/information point.
    """
    return {
        "message": "Welcome to the SmartFlow API. Head to /api/docs for Swagger documentation.",
        "docs_url": "/api/docs"
    }


# Include Routers (to be created next)
from app.backend.routers import traffic, weather, incidents, analytics

app.include_router(traffic.router, prefix="/api", tags=["Traffic"])
app.include_router(weather.router, prefix="/api", tags=["Weather"])
app.include_router(incidents.router, prefix="/api", tags=["Incidents"])
app.include_router(analytics.router, prefix="/api", tags=["Analytics"])
