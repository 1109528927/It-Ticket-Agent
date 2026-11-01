from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from router.ai import router as ai_router
from router.automation import router as automation_router
from router.kb import router as kb_router
from router.loginuser import router as user_router
from router.ticket import router as ticket_router
from utils.exception import register_exception_handlers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from automation.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="内部 IT 工单台", version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "it-ticket api ok"}


app.include_router(user_router)
app.include_router(ticket_router)
app.include_router(kb_router)
app.include_router(ai_router)
app.include_router(automation_router)
