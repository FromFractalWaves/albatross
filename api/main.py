from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.scenarios import router as scenarios_router
from api.routes.runs import router as runs_router
from api.routes.live import router as live_router
from api.routes.mock import router as mock_router
from api.services.runner import RunManager

app = FastAPI(title="TRM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.run_manager = RunManager()
app.state.mock_processes = []

app.include_router(scenarios_router, prefix="/api")
app.include_router(runs_router)
app.include_router(live_router, prefix="/api")
app.include_router(mock_router, prefix="/api")
