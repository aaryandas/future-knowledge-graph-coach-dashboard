from fastapi import FastAPI

from app.api.graph_view import router as graph_view_router
from app.api.health import router as health_router

app = FastAPI(title="KG Coach Dashboard API")
app.include_router(health_router)
app.include_router(graph_view_router)
