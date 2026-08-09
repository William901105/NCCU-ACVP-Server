from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple, Union

from .algorithm_identity import AlgorithmIdentity


FrozenJson = Union[None, bool, int, float, str, Tuple[str, Any]]


@dataclass(frozen=True)
class AlgorithmDescriptor:
    provider_id: str
    algorithm: str
    revision: str
    display_name: str
    enabled: bool
    modes: Tuple[str, ...]
    parameter_sets: Tuple[str, ...]
    registration_schema_version: str
    response_schema_version: str
    execution_backend: str
    nist_references: Tuple[str, ...]
    capability_metadata: Any = ()
    supported_identities: Tuple[AlgorithmIdentity, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "provider_id",
            "algorithm",
            "revision",
            "display_name",
            "registration_schema_version",
            "response_schema_version",
            "execution_backend",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.execution_backend != "nist-genval":
            raise ValueError("execution_backend must be nist-genval")
        object.__setattr__(self, "modes", _non_empty_strings(self.modes, "modes"))
        object.__setattr__(self, "parameter_sets", _non_empty_strings(self.parameter_sets, "parameter_sets"))
        object.__setattr__(self, "nist_references", tuple(self.nist_references))
        object.__setattr__(self, "capability_metadata", _freeze_mapping(self.capability_metadata))
        identities = tuple(self.supported_identities)
        if identities:
            if any(not isinstance(identity, AlgorithmIdentity) for identity in identities):
                raise TypeError("supported_identities must contain AlgorithmIdentity values")
            if any(identity.algorithm != self.algorithm for identity in identities):
                raise ValueError("supported_identities must use descriptor.algorithm")
            if len(set(identities)) != len(identities):
                raise ValueError("supported_identities must not contain duplicates")
        object.__setattr__(self, "supported_identities", identities)

    def identities(self) -> Tuple[AlgorithmIdentity, ...]:
        if self.supported_identities:
            return self.supported_identities
        return tuple(
            AlgorithmIdentity(self.algorithm, mode, self.revision)
            for mode in self.modes
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "providerId": self.provider_id,
            "algorithm": self.algorithm,
            "revision": self.revision,
            "displayName": self.display_name,
            "enabled": self.enabled,
            "modes": list(self.modes),
            "parameterSets": list(self.parameter_sets),
            "registrationSchemaVersion": self.registration_schema_version,
            "responseSchemaVersion": self.response_schema_version,
            "workflowPolicy": "strict",
            "executionBackend": self.execution_backend,
            "nistReferences": list(self.nist_references),
            "identities": [
                {
                    "algorithm": identity.algorithm,
                    "mode": identity.mode,
                    "revision": identity.revision,
                }
                for identity in self.identities()
            ],
        }
        for key, value in self.capability_metadata:
            result[key] = _thaw(value)
        return result


def _non_empty_strings(values: Any, field_name: str) -> Tuple[str, ...]:
    normalized = tuple(values)
    if not normalized or any(not isinstance(value, str) or not value for value in normalized):
        raise ValueError(f"{field_name} must contain non-empty strings")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _freeze_mapping(value: Any) -> Tuple[Tuple[str, FrozenJson], ...]:
    if value in (None, ()):
        return ()
    items = value.items() if isinstance(value, Mapping) else value
    frozen = []
    for key, item in items:
        if not isinstance(key, str) or not key:
            raise ValueError("capability metadata keys must be non-empty strings")
        frozen.append((key, _freeze(item)))
    return tuple(frozen)


def _freeze(value: Any) -> FrozenJson:
    if isinstance(value, Mapping):
        return ("mapping", tuple((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(_freeze(item) for item in value))
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"Unsupported descriptor metadata value: {type(value).__name__}")


def _thaw(value: FrozenJson) -> Any:
    if isinstance(value, tuple) and len(value) == 2:
        kind, items = value
        if kind == "mapping":
            return {item[0]: _thaw(item[1]) for item in items}
        if kind == "sequence":
            return [_thaw(item) for item in items]
    return value
