from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .algorithm_descriptor import AlgorithmDescriptor
from .algorithm_identity import AlgorithmIdentity
from .algorithm_module import AcvpAlgorithmModule


class AlgorithmModuleRegistryError(Exception):
    """Base error for algorithm module registry failures."""


class DuplicateModuleError(AlgorithmModuleRegistryError):
    def __init__(
        self,
        message: str,
        *,
        identity: Optional[AlgorithmIdentity] = None,
        provider_id: Optional[str] = None,
    ):
        self.identity = identity
        self.provider_id = provider_id
        super().__init__(message)


class ModuleNotFoundError(AlgorithmModuleRegistryError):
    def __init__(self, identity: AlgorithmIdentity):
        self.identity = identity
        super().__init__(f"No algorithm module registered for {identity}.")


class AlgorithmModuleRegistry:
    def __init__(self) -> None:
        self._modules: Dict[AlgorithmIdentity, AcvpAlgorithmModule] = {}
        self._provider_ids: Dict[str, AcvpAlgorithmModule] = {}

    def register_module(self, module: AcvpAlgorithmModule) -> None:
        provider_id = module.provider_id
        descriptor = module.descriptor
        if not isinstance(provider_id, str) or not provider_id:
            raise AlgorithmModuleRegistryError("Module provider_id must be a non-empty string.")
        if not isinstance(descriptor, AlgorithmDescriptor):
            raise AlgorithmModuleRegistryError("Module descriptor must be an AlgorithmDescriptor.")
        if descriptor.provider_id != provider_id:
            raise AlgorithmModuleRegistryError("Module provider_id must match descriptor.provider_id.")
        if provider_id in self._provider_ids:
            raise DuplicateModuleError(
                f"Module provider_id already registered: {provider_id}.",
                provider_id=provider_id,
            )

        identities = descriptor.identities()
        for identity in identities:
            if not module.supports(identity):
                raise AlgorithmModuleRegistryError(
                    f"Module {provider_id} does not support descriptor identity {identity}."
                )
            if identity in self._modules:
                raise DuplicateModuleError(
                    f"Algorithm identity already registered: {identity}.",
                    identity=identity,
                )

        self._provider_ids[provider_id] = module
        for identity in identities:
            self._modules[identity] = module

    def get_module(self, identity: AlgorithmIdentity) -> AcvpAlgorithmModule:
        module = self._modules.get(identity)
        if module is None:
            raise ModuleNotFoundError(identity)
        return module

    def list_descriptors(self) -> List[Dict[str, object]]:
        descriptors = sorted(
            (module.descriptor for module in self._provider_ids.values()),
            key=lambda item: (item.algorithm, item.revision, item.provider_id),
        )
        return [descriptor.to_dict() for descriptor in descriptors]

    def identities(self) -> Tuple[AlgorithmIdentity, ...]:
        return tuple(sorted(self._modules, key=lambda item: (item.algorithm, item.revision, item.mode)))

    def __len__(self) -> int:
        return len(self._provider_ids)
