from fastapi import APIRouter

from .health import router as health_router
from .analyses import router as analyses_router
from .matrices import router as matrices_router
from .threads import router as threads_router
from .simulations import router as simulations_router
from .sync import router as sync_router
from .distributions import router as distributions_router
from .users import router as users_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(analyses_router)
api_router.include_router(matrices_router)
api_router.include_router(threads_router)
api_router.include_router(simulations_router)
api_router.include_router(sync_router)
api_router.include_router(distributions_router)
api_router.include_router(users_router)
