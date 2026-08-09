import type {
  AcvpParameterSet,
  AcvpRevision,
  CapabilityMode,
  FipsVersionConfig,
  JsonObject,
  MlKemFunction
} from "./types";

export interface BuildRegistrationAlgorithmsInput {
  config: FipsVersionConfig;
  modes: CapabilityMode[];
  parameterSets: AcvpParameterSet[];
  functions: MlKemFunction[];
  revisions?: Partial<Record<CapabilityMode, AcvpRevision>>;
}

const PREREQUISITES = [{ algorithm: "SHA", valValue: "same" }];

export function buildRegistrationAlgorithms({
  config,
  modes,
  parameterSets,
  functions,
  revisions = {}
}: BuildRegistrationAlgorithmsInput): JsonObject[] {
  if (modes.length === 0) {
    throw new Error("Select at least one mode.");
  }
  if (parameterSets.length === 0) {
    throw new Error("Select at least one parameter set.");
  }
  if (config.id === "FIPS203" && modes.includes("encapDecap") && functions.length === 0) {
    throw new Error("Select at least one ML-KEM function for encapDecap.");
  }

  return modes.map((mode) => {
    const modeConfig = config.modes.find((item) => item.id === mode);
    if (!modeConfig) {
      throw new Error(`Unsupported mode ${mode} for ${config.algorithm}.`);
    }
    const revision = revisions[mode] ?? modeConfig.defaultRevision;
    if (!modeConfig.revisions.includes(revision)) {
      throw new Error(`Unsupported revision ${revision} for ${config.algorithm}/${mode}.`);
    }
    const registration: JsonObject = {
      algorithm: config.algorithm,
      mode,
      revision,
      prereqVals: PREREQUISITES,
      parameterSets: [...parameterSets]
    };

    if (config.id === "FIPS203") {
      if (mode === "encapDecap") {
        registration.functions = [...functions];
        if (revision === "FIPS203-tr1") {
          registration.keyFormats = ["expanded", "seed"];
        }
      }
      return registration;
    }

    if (mode !== "keyGen") {
      registration.signatureInterfaces = ["internal", "external"];
      registration.externalMu = [false, true];
      registration.preHash = ["pure", "preHash"];
      registration.capabilities = [
        {
          parameterSets: [...parameterSets],
          messageLength: [{ min: 8, max: 128, increment: 8 }],
          contextLength: [{ min: 0, max: 64, increment: 8 }],
          hashAlgs: config.defaultHashAlgs ?? ["SHA2-256"]
        }
      ];
    }
    if (mode === "sigGen") {
      registration.deterministic = [true, false];
      if (revision === "FIPS204-tr1") {
        registration.keyFormats = ["expanded", "seed"];
      }
    }
    return registration;
  });
}
