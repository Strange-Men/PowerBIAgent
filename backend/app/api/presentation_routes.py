"""Local presentation API. ENTRA_BFF remains denied by the existing boundary."""
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,ConfigDict,Field

from backend.app.memory.models import RuntimeDataMode
from backend.app.presentation.projection import project_snapshot,PresentationUnavailableError
from backend.app.presentation.localization import JsonDisplayLocalizationRegistry

router=APIRouter()


class LocalPresentationRequest(BaseModel):
    locale: str=Field(max_length=32)
    runtime_mode: RuntimeDataMode
    model_config=ConfigDict(extra='forbid')


@router.post('/api/v1/presentations/{request_id}')
async def presentation(request_id:str,body:LocalPresentationRequest,request:Request):
    service=request.app.state.turn_service
    snapshot=await service.pipeline.snapshot_store.get(request_id,body.runtime_mode)
    if snapshot is None: raise HTTPException(404,'resource_not_found')
    registry=JsonDisplayLocalizationRegistry(request.app.state.settings.presentation_localization_registry_path)
    try: return await project_snapshot(snapshot,body.locale,registry=registry)
    except PresentationUnavailableError: raise HTTPException(404,'presentation_recipe_unavailable') from None


async def local_report_projection(request,artifact,locale):
    from backend.app.presentation.projection import render_snapshot_report
    if locale is None: return None
    snapshot=await request.app.state.turn_service.pipeline.snapshot_store.get(
        artifact.request_id,RuntimeDataMode(artifact.source_mode))
    if snapshot is None: raise HTTPException(404,'presentation_recipe_unavailable')
    try: return await render_snapshot_report(snapshot,artifact,locale,request.app.state.turn_service.report_renderer)
    except PresentationUnavailableError: raise HTTPException(404,'presentation_recipe_unavailable') from None
