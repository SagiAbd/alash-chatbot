import logging

from fastapi import FastAPI
from langchain.globals import set_debug, set_verbose

from app.api.api_v1.api import api_router
from app.core.config import settings
from app.core.minio import init_minio
from app.startup.migarate import DatabaseMigrator

set_verbose(settings.AGENT_VERBOSE)
set_debug(False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# Include routers
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def startup_event():
    logger.info(
        "Backend startup | agent_verbose=%s | langchain_verbose=%s",
        settings.AGENT_VERBOSE,
        settings.AGENT_VERBOSE,
    )
    # Initialize MinIO
    init_minio()
    # Run database migrations
    migrator = DatabaseMigrator(settings.get_database_url)
    migrator.run_migrations()
    # Initialize LangGraph agent
    from app.services.agent.graph import init_graph

    init_graph()


@app.get("/")
def root():
    return {"message": "Welcome to RAG Web UI API"}


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
    }
