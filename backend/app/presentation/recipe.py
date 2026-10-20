"""Immutable presentation inputs copied from the existing verified boundary.

No provider, parser, planner, Grounding, Memory, or query tool is available here.
"""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from backend.app.facts.verified import VerifiedFactSet, FactBoundedAnswerBuilder, FactOutputValidator
from backend.app.presentation.builder import StructuredPresentationBuilder
from backend.app.presentation.locale import normalize_locale, presentation_locale
from backend.app.presentation.localization import DisplayLocalization, DisplayLocalizationService
from backend.app.presentation.models import PresentationEnvelope
from backend.app.schemas.data_contracts import CanonicalQueryPlan, QueryResult, ReportSpec, AnswerSpec
from backend.app.schemas.factual_context import DataAvailabilityContext


def _encode(value):
    if isinstance(value, Decimal):
        return {'$presentation_decimal':str(value)}
    if isinstance(value, datetime):
        return {'$presentation_datetime':value.isoformat()}
    if isinstance(value, date):
        return {'$presentation_date':value.isoformat()}
    if isinstance(value, dict):
        return {key:_encode(item) for key,item in value.items()}
    if isinstance(value, (tuple,list)):
        return [_encode(item) for item in value]
    return value


def _decode(value):
    if isinstance(value, dict):
        if set(value)=={'$presentation_decimal'}:
            number=Decimal(value['$presentation_decimal'])
            if not number.is_finite(): raise ValueError('presentation_decimal_invalid')
            return number
        if set(value)=={'$presentation_datetime'}:
            return datetime.fromisoformat(value['$presentation_datetime'])
        if set(value)=={'$presentation_date'}:
            return date.fromisoformat(value['$presentation_date'])
        return {key:_decode(item) for key,item in value.items()}
    if isinstance(value,list): return [_decode(item) for item in value]
    return value


class PresentationRecipe(BaseModel):
    version: int = 1
    schema_fingerprint: str = ""
    plan: CanonicalQueryPlan | None = None
    result: QueryResult | None = None
    facts: VerifiedFactSet | None = None
    availability: DataAvailabilityContext | None = None
    display_bindings: dict[str,DisplayLocalization] = Field(default_factory=dict)
    report_spec: ReportSpec | None = None
    causal_boundary: bool = False
    model_config = ConfigDict(extra='forbid', frozen=True)

    @model_validator(mode='before')
    @classmethod
    def decode_typed_values(cls, value):
        return _decode(value)

    @model_serializer
    def serialize_typed_values(self):
        # JSON mode must not erase Decimal/date types inside Any fields.
        payload={key:(value.model_dump(mode='python') if isinstance(value,BaseModel) else value)
                 for key,value in self.__dict__.items()}
        payload['display_bindings']={key:value.model_dump(mode='python') for key,value in self.display_bindings.items()}
        return _encode(payload)

    @model_validator(mode='after')
    def prove_coherence(self):
        if self.version != 1: raise ValueError('presentation_recipe_version_invalid')
        if self.report_spec is None:
            if self.plan is None or self.result is None or self.facts is None:
                raise ValueError('presentation_recipe_facts_required')
            StructuredPresentationBuilder._validate_authority(self.result,self.facts)
            if self.plan.semantic_model_key != self.facts.semantic_model_key:
                raise ValueError('presentation_recipe_model_mismatch')
            if any(f.provenance.plan_semantics != self.plan.model_dump(mode='json') for f in self.facts.facts):
                raise ValueError('presentation_recipe_plan_mismatch')
        elif any(item is not None for item in (self.plan,self.result,self.facts)):
            raise ValueError('presentation_recipe_kind_mismatch')
        return self

    @property
    def factual_hash(self):
        payload = {key:value for key,value in self.serialize_typed_values().items()
                   if key not in {'display_bindings','causal_boundary'}}
        return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class ProjectedPresentation(BaseModel):
    locale: str
    answer: str
    presentation: PresentationEnvelope
    factual_hash: str
    answer_spec: AnswerSpec | None = Field(default=None,exclude=True)
    model_config=ConfigDict(frozen=True)


async def project_recipe(recipe: PresentationRecipe, locale, *, registry=None):
    from backend.app.presentation.messages import message
    selected=normalize_locale(locale).value
    with presentation_locale(selected):
        if recipe.report_spec is not None:
            return ProjectedPresentation(locale=selected,answer=message('display.your_report_is_ready_view_it_or'),
                presentation=PresentationEnvelope(),factual_hash=recipe.factual_hash)
        bindings=DisplayLocalizationService.project_bindings(recipe.display_bindings,locale=selected,registry=registry)
        answer=FactBoundedAnswerBuilder().build(recipe.plan,recipe.result,recipe.facts,
            display_bindings=bindings,locale=selected,data_availability=recipe.availability)
        if recipe.causal_boundary:
            text=answer.answer+message('chat.causal_boundary')
            answer=answer.model_copy(update={'answer':text,'summary':text,
                'evidence':{**answer.evidence,'causal_analysis_boundary':'not_proven'}})
        errors=FactOutputValidator().validate_answer(answer,recipe.facts,locale=selected)
        if errors: raise ValueError('presentation_projection_validation_failed:'+','.join(errors))
        envelope=StructuredPresentationBuilder.build_answer(recipe.plan,recipe.result,recipe.facts,
            answer.answer,display_bindings=bindings or None,locale=selected)
        return ProjectedPresentation(locale=selected,answer=answer.answer,presentation=envelope,
            factual_hash=recipe.factual_hash,answer_spec=answer)
