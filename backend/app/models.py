from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


JsonObject = Union[Dict[str, Any], List[Any]]


class ImportRequest(BaseModel):
    prompt: JsonObject
    expectedResults: JsonObject
    response: JsonObject
    label: Optional[str] = None


class GeneratedKeygenImportRequest(BaseModel):
    prompt: JsonObject
    response: JsonObject
    label: Optional[str] = None


class GeneratedMldsaImportRequest(BaseModel):
    prompt: JsonObject
    response: JsonObject
    label: Optional[str] = None


class ValidateRequest(BaseModel):
    importId: str


class LoadSampleRequest(BaseModel):
    sampleName: str
    responseVariant: Literal["pass", "fail"] = "pass"


class ImportSummary(BaseModel):
    importId: str
    label: Optional[str] = None
    vsId: Any = None
    algorithm: Optional[str] = None
    mode: Optional[str] = None
    revision: Optional[str] = None
    testGroupCount: int = 0
    testCaseCount: int = 0


class ApiError(BaseModel):
    detail: str = Field(..., examples=["Unknown importId"])


class DemoAcvpSessionCreateRequest(BaseModel):
    prompt: JsonObject
    label: Optional[str] = None
    autoGenerateExpectedResults: bool = True


class DemoAcvpResponseSubmitRequest(BaseModel):
    response: JsonObject
    validateImmediately: bool = True


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


class MldsaKeygenRequest(BaseModel):
    parameterSet: str
    seed: str


class MldsaKeygenResponse(BaseModel):
    algorithm: Literal["ML-DSA"] = "ML-DSA"
    mode: Literal["keyGen"] = "keyGen"
    revision: Literal["FIPS204"] = "FIPS204"
    parameterSet: str
    seed: str
    pk: str
    sk: str


class MldsaKeygenExpectedResultsRequest(BaseModel):
    prompt: JsonObject


class MldsaKeygenExpectedResultsResponse(BaseModel):
    algorithm: Literal["ML-DSA"] = "ML-DSA"
    mode: Literal["keyGen"] = "keyGen"
    revision: Literal["FIPS204"] = "FIPS204"
    expectedResults: JsonObject


class MldsaExpectedResultsRequest(BaseModel):
    prompt: JsonObject


class MldsaExpectedResultsResponse(BaseModel):
    algorithm: Literal["ML-DSA"] = "ML-DSA"
    mode: str
    revision: Literal["FIPS204"] = "FIPS204"
    expectedResults: JsonObject


class MldsaSigGenRequest(BaseModel):
    parameterSet: Literal["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]
    signatureInterface: Literal["internal", "external"] = "internal"
    externalMu: bool = False
    deterministic: bool = True
    sk: str
    message: Optional[str] = None
    mu: Optional[str] = None
    rnd: Optional[str] = None
    preHash: Optional[Literal["pure", "preHash"]] = None
    context: Optional[str] = None
    hashAlg: Optional[str] = None

    @model_validator(mode="after")
    def validate_siggen_inputs(self) -> "MldsaSigGenRequest":
        if self.signatureInterface == "external":
            if self.externalMu:
                raise ValueError("externalMu is not allowed when signatureInterface=external")
            if self.mu is not None:
                raise ValueError("mu is not allowed when signatureInterface=external")
            if self.message is None:
                raise ValueError("message is required when signatureInterface=external")
            if self.preHash is None:
                raise ValueError("preHash is required when signatureInterface=external")
            if self.context is None:
                raise ValueError("context is required when signatureInterface=external")
            if self.preHash == "pure" and self.hashAlg is not None:
                raise ValueError("hashAlg is not allowed when preHash=pure")
            if self.preHash == "preHash" and self.hashAlg is None:
                raise ValueError("hashAlg is required when preHash=preHash")
        else:
            if self.preHash is not None:
                raise ValueError("preHash is not allowed when signatureInterface=internal")
            if self.context is not None:
                raise ValueError("context is not allowed when signatureInterface=internal")
            if self.hashAlg is not None:
                raise ValueError("hashAlg is not allowed when signatureInterface=internal")
            if self.externalMu:
                if self.mu is None:
                    raise ValueError("mu is required when externalMu=true")
                if self.message is not None:
                    raise ValueError("message is not allowed when externalMu=true")
            else:
                if self.message is None:
                    raise ValueError("message is required when externalMu=false")
                if self.mu is not None:
                    raise ValueError("mu is not allowed when externalMu=false")

        if self.deterministic:
            if self.rnd is not None:
                raise ValueError("rnd is not allowed when deterministic=true")
        elif self.rnd is None:
            raise ValueError("rnd is required when deterministic=false")

        return self


class MldsaSigGenResponse(BaseModel):
    algorithm: Literal["ML-DSA"] = "ML-DSA"
    mode: Literal["sigGen"] = "sigGen"
    revision: Literal["FIPS204"] = "FIPS204"
    parameterSet: str
    signatureInterface: Literal["internal", "external"] = "internal"
    externalMu: bool
    deterministic: bool
    preHash: Optional[Literal["pure", "preHash"]] = None
    context: Optional[str] = None
    hashAlg: Optional[str] = None
    signature: str


class MldsaSigVerRequest(BaseModel):
    parameterSet: Literal["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]
    signatureInterface: Literal["internal", "external"] = "internal"
    externalMu: bool = False
    pk: str
    message: Optional[str] = None
    mu: Optional[str] = None
    signature: str
    preHash: Optional[Literal["pure", "preHash"]] = None
    context: Optional[str] = None
    hashAlg: Optional[str] = None

    @model_validator(mode="after")
    def validate_sigver_inputs(self) -> "MldsaSigVerRequest":
        if self.signatureInterface == "external":
            if self.externalMu:
                raise ValueError("externalMu is not allowed when signatureInterface=external")
            if self.mu is not None:
                raise ValueError("mu is not allowed when signatureInterface=external")
            if self.message is None:
                raise ValueError("message is required when signatureInterface=external")
            if self.preHash is None:
                raise ValueError("preHash is required when signatureInterface=external")
            if self.context is None:
                raise ValueError("context is required when signatureInterface=external")
            if self.preHash == "pure" and self.hashAlg is not None:
                raise ValueError("hashAlg is not allowed when preHash=pure")
            if self.preHash == "preHash" and self.hashAlg is None:
                raise ValueError("hashAlg is required when preHash=preHash")
        else:
            if self.preHash is not None:
                raise ValueError("preHash is not allowed when signatureInterface=internal")
            if self.context is not None:
                raise ValueError("context is not allowed when signatureInterface=internal")
            if self.hashAlg is not None:
                raise ValueError("hashAlg is not allowed when signatureInterface=internal")
            if self.externalMu:
                if self.mu is None:
                    raise ValueError("mu is required when externalMu=true")
                if self.message is not None:
                    raise ValueError("message is not allowed when externalMu=true")
            else:
                if self.message is None:
                    raise ValueError("message is required when externalMu=false")
                if self.mu is not None:
                    raise ValueError("mu is not allowed when externalMu=false")
        return self


class MldsaSigVerResponse(BaseModel):
    algorithm: Literal["ML-DSA"] = "ML-DSA"
    mode: Literal["sigVer"] = "sigVer"
    revision: Literal["FIPS204"] = "FIPS204"
    parameterSet: str
    signatureInterface: Literal["internal", "external"] = "internal"
    externalMu: bool
    preHash: Optional[Literal["pure", "preHash"]] = None
    context: Optional[str] = None
    hashAlg: Optional[str] = None
    testPassed: bool
