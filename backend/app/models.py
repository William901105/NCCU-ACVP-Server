from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


JsonObject = Union[Dict[str, Any], List[Any]]
_ACVP_RESOURCE_URL_PATTERN = re.compile(
    r"^/acvp/v1/(?P<collection>[^/?#]+)/(?P<identifier>[^/?#]+)$"
)


def _validate_acvp_resource_url(value: str, *, collection: str) -> str:
    match = _ACVP_RESOURCE_URL_PATTERN.fullmatch(value)
    if match is None or match.group("collection") != collection:
        raise ValueError(
            f"must identify an /acvp/v1/{collection}/{{id}} resource"
        )
    return value


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


class AcvpV1CertificationPrerequisite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str
    validationId: str

    @field_validator("algorithm", "validationId")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class AcvpV1CertificationAlgorithmPrerequisites(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str
    mode: Optional[str] = None
    prerequisites: List[AcvpV1CertificationPrerequisite]

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class AcvpV1TestSessionCertificationRequest(BaseModel):
    """Reference-form certification request from the ACVP core protocol."""

    model_config = ConfigDict(extra="forbid")

    moduleUrl: str
    oeUrl: str
    algorithmPrerequisites: List[AcvpV1CertificationAlgorithmPrerequisites] = Field(
        default_factory=list
    )

    @field_validator("moduleUrl")
    @classmethod
    def validate_module_url(cls, value: str) -> str:
        return _validate_acvp_resource_url(value, collection="modules")

    @field_validator("oeUrl")
    @classmethod
    def validate_oe_url(cls, value: str) -> str:
        return _validate_acvp_resource_url(value, collection="oes")
