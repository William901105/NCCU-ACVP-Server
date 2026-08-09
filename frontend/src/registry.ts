import type { FipsVersionConfig, FipsVersionId, MlKemFunction } from "./types";

export const ML_KEM_FUNCTIONS: MlKemFunction[] = [
  "encapsulation",
  "decapsulation",
  "encapsulationKeyCheck",
  "decapsulationKeyCheck"
];

export const FIPS_REGISTRY: FipsVersionConfig[] = [
  {
    id: "FIPS204",
    label: "FIPS 204 / ML-DSA",
    algorithm: "ML-DSA",
    revision: "FIPS204",
    enabled: true,
    status: "available",
    modes: [
      {
        id: "keyGen", label: "keyGen", enabled: true,
        revisions: ["FIPS204"], defaultRevision: "FIPS204"
      },
      {
        id: "sigGen", label: "sigGen", enabled: true,
        revisions: ["FIPS204", "FIPS204-tr1"], defaultRevision: "FIPS204-tr1"
      },
      {
        id: "sigVer", label: "sigVer", enabled: true,
        revisions: ["FIPS204"], defaultRevision: "FIPS204"
      }
    ],
    defaultModes: ["keyGen"],
    parameterSets: ["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"],
    defaultParameterSets: ["ML-DSA-44"],
    defaultHashAlgs: ["SHA2-256"]
  },
  {
    id: "FIPS203",
    label: "FIPS 203 / ML-KEM",
    algorithm: "ML-KEM",
    revision: "FIPS203",
    enabled: true,
    status: "available",
    modes: [
      {
        id: "keyGen", label: "keyGen", enabled: true,
        revisions: ["FIPS203"], defaultRevision: "FIPS203"
      },
      {
        id: "encapDecap", label: "encapDecap", enabled: true,
        revisions: ["FIPS203", "FIPS203-tr1"], defaultRevision: "FIPS203-tr1"
      }
    ],
    defaultModes: ["keyGen"],
    parameterSets: ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"],
    defaultParameterSets: ["ML-KEM-512"],
    functions: [...ML_KEM_FUNCTIONS],
    defaultFunctions: [...ML_KEM_FUNCTIONS]
  }
];

export function getFipsConfig(id: FipsVersionId | string): FipsVersionConfig {
  return FIPS_REGISTRY.find((item) => item.id === id) ?? FIPS_REGISTRY[0];
}
