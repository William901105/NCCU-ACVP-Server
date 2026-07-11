from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


JsonObject = Union[Dict[str, Any], List[Any]]


class AcvpV1TestSessionCreateRequest(BaseModel):
    """Strict ACVP registration request accepted by production routes."""

    model_config = ConfigDict(extra="forbid")

    algorithms: List[JsonObject]
    label: Optional[str] = None
    autoGenerateVectorSets: bool = True
    campaignSeed: Optional[str] = None
    testsPerGroup: Optional[int] = None
    isSample: Optional[bool] = None
    expiresInSeconds: Optional[int] = Field(default=None, ge=0)
    metadata: Optional[JsonObject] = None


class AcvpV1VectorSetGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaignSeed: Optional[str] = None
    testsPerGroup: Optional[int] = None
    expiresInSeconds: Optional[int] = Field(default=None, ge=0)


class AcvpV1VectorSetResultsSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: JsonObject
