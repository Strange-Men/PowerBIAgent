"""Read-only projection of an already authorized terminal snapshot."""
from backend.app.presentation.locale import normalize_locale
from backend.app.presentation.recipe import project_recipe
from backend.app.presentation.builder import StructuredPresentationBuilder


class PresentationUnavailableError(LookupError):
    pass


async def project_snapshot(snapshot, locale, *, registry=None):
    if snapshot.presentation_recipe is None:
        raise PresentationUnavailableError('presentation_recipe_unavailable')
    projected=await project_recipe(snapshot.presentation_recipe,locale,registry=registry)
    if snapshot.report is not None:
        projected=projected.model_copy(update={'presentation':StructuredPresentationBuilder.build_report(
            snapshot.report.report_id,locale=normalize_locale(locale).value)})
    return projected


async def render_snapshot_report(snapshot, artifact, locale, renderer):
    from backend.app.presentation.locale import presentation_locale
    recipe=snapshot.presentation_recipe
    spec=recipe.report_spec if recipe is not None else None
    if spec is None:
        raise PresentationUnavailableError('presentation_recipe_unavailable')
    if (snapshot.report is None or snapshot.report.report_id!=artifact.report_id
        or (spec.request_id,spec.conversation_id,spec.semantic_model_key,spec.schema_fingerprint,
            spec.template_key,spec.query_result_ids,spec.verified_fact_set_ids)!=(
            artifact.request_id,artifact.conversation_id,artifact.semantic_model_key,artifact.schema_fingerprint,
            artifact.template_key,artifact.query_result_ids,artifact.verified_fact_set_ids)):
        raise ValueError('presentation_report_binding_mismatch')
    with presentation_locale(locale):
        return await renderer.render(spec)
