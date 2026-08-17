import { describe, expect, it } from "vitest";
import { FIPS_REGISTRY, ML_KEM_FUNCTIONS, getFipsConfig } from "./registry";

describe("FIPS registry", () => {
  it("enables the complete FIPS 203 configuration", () => {
    const config = getFipsConfig("FIPS203");

    expect(config.enabled).toBe(true);
    expect(config.status).toBe("available");
    expect(config.algorithm).toBe("ML-KEM");
    expect(config.revision).toBe("FIPS203");
    expect(config.modes.map((mode) => mode.id)).toEqual(["keyGen", "encapDecap"]);
    expect(config.modes.find((mode) => mode.id === "keyGen")?.revisions).toEqual(["FIPS203"]);
    expect(config.modes.find((mode) => mode.id === "encapDecap")?.revisions).toEqual([
      "FIPS203"
    ]);
    expect(config.parameterSets).toEqual(["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]);
    expect(config.functions).toEqual(ML_KEM_FUNCTIONS);
    expect(config.functions).toEqual([
      "encapsulation",
      "decapsulation",
      "encapsulationKeyCheck",
      "decapsulationKeyCheck"
    ]);
    expect(config.defaultModes).toEqual(["keyGen"]);
    expect(config.defaultParameterSets).toEqual(["ML-KEM-512"]);
    expect(config.defaultFunctions).toEqual(config.functions);
  });

  it("keeps FIPS 204 available and internally valid", () => {
    const config = getFipsConfig("FIPS204");

    expect(config.enabled).toBe(true);
    expect(config.status).toBe("available");
    expect(config.algorithm).toBe("ML-DSA");
    expect(config.modes.map((mode) => mode.id)).toEqual(["keyGen", "sigGen", "sigVer"]);
    expect(config.modes.find((mode) => mode.id === "sigGen")?.revisions).toEqual([
      "FIPS204", "FIPS204-tr1"
    ]);
    expect(config.parameterSets).toEqual(["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]);
    expect(config.defaultModes.every((mode) => config.modes.some((item) => item.id === mode))).toBe(true);
    expect(config.defaultParameterSets.every((set) => config.parameterSets.includes(set))).toBe(true);
    expect(FIPS_REGISTRY).toHaveLength(2);
  });
});
