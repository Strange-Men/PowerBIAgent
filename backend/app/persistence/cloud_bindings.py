"""Exact resource identity metadata, immutable and owner scoped."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from backend.app.auth.models import AuthFailure
from backend.app.persistence.models import CloudConversationBindingModel


class CloudConversationBinding(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    model_key: str = Field(min_length=1, max_length=128)
    workspace_id: UUID
    model_id: UUID
    schema_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_mode: str = Field(pattern=r'^(mock|real)$')
    model_config = ConfigDict(extra='forbid', frozen=True)


class CloudBindingRepository:
    def __init__(self, sessions, owner_id):
        self._sessions, self._owner = sessions, owner_id

    async def get(self, conversation_id):
        async with self._sessions() as session:
            row = (await session.execute(select(CloudConversationBindingModel).where(
                CloudConversationBindingModel.owner_id == self._owner,
                CloudConversationBindingModel.conversation_id == conversation_id))).scalar_one_or_none()
            if row is None: return None
            return CloudConversationBinding(**{name:getattr(row, name) for name in CloudConversationBinding.model_fields})

    async def save(self, binding):
        if not isinstance(binding, CloudConversationBinding): raise AuthFailure('AUTH_FORBIDDEN',403)
        binding=CloudConversationBinding.model_validate(binding.model_dump())
        values = binding.model_dump(mode='json')
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(insert(CloudConversationBindingModel).values(owner_id=self._owner,
                    **values).on_conflict_do_nothing())
                row = (await session.execute(select(CloudConversationBindingModel).where(
                    CloudConversationBindingModel.owner_id == self._owner,
                    CloudConversationBindingModel.conversation_id == binding.conversation_id))).scalar_one()
                if any(getattr(row,k) != v for k,v in values.items()): raise AuthFailure('AUTH_FORBIDDEN',403)
