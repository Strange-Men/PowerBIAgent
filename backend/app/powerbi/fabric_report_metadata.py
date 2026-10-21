"""Report metadata identity only; never consumes visuals, filters or facts."""
import json

from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.powerbi.fabric_iq_normalization import guid, safe_normalization, _reject_errors


@safe_normalization
def report_model_id(raw, expected_report):
    """Pinned Microsoft Report text payload and separate Report citation.

    Report citations identify the report, whereas schema/query citations identify
    the model. Keep this contract separate from factual envelope normalization.
    """
    if hasattr(raw, 'model_dump'):
        raw = raw.model_dump(mode='json', by_alias=True, exclude_none=True)
    _reject_errors(raw, 'MODEL_RESOLUTION_FAILED')
    if 'content' in raw:
        content = raw['content']
        structured = raw.get('structuredContent')
        if (not isinstance(content, list) or len(content) != 1
                or not isinstance(content[0], dict) or content[0].get('type') != 'text'
                or not isinstance(structured, dict)):
            raise fail('CONTRACT_DRIFT')
        _reject_errors(structured, 'MODEL_RESOLUTION_FAILED')
        citation = structured.get('artifact_citation')
        if not isinstance(citation, dict) or guid(citation.get('ArtifactId')) != expected_report:
            raise fail('CONTRACT_DRIFT')
        _reject_errors(citation, 'MODEL_RESOLUTION_FAILED')
        body = json.loads(content[0]['text'])
    else:
        body = raw  # Plain deterministic fixture DTO.
    _reject_errors(body, 'MODEL_RESOLUTION_FAILED')
    report, model = body.get('ReportMetadata'), body.get('SemanticModel')
    if (not isinstance(report, dict) or not isinstance(model, dict)
            or guid(report.get('Id')) != expected_report):
        raise fail('CONTRACT_DRIFT')
    _reject_errors(report, 'MODEL_RESOLUTION_FAILED')
    _reject_errors(model, 'MODEL_RESOLUTION_FAILED')
    return guid(model.get('Id'))
