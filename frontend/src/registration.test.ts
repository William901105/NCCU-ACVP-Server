import { describe, expect, it } from "vitest";
import { buildRegistrationAlgorithms } from "./registration";
import { getFipsConfig } from "./registry";
import type {
  JsonObject,
  MlKemFunction,
  MlKemParameterSet,
  MldsaParameterSet
} from "./types";

const DSA_ONLY_FIELDS = [
  "deterministic",
  "signatureInterfaces",
  "externalMu",
  "preHash",
  "capabilities"
];

function buildFips204(
  mode: "keyGen" | "sigGen" | "sigVer",
  parameterSets: readonly MldsaParameterSet[] = ["ML-DSA-44"]
) {
  return buildRegistrationAlgorithms({
    config: getFipsConfig("FIPS204"),
    modes: [mode],
    parameterSets: [...parameterSets],
    functions: []
  })[0];
}

function buildFips203(
  modes: ("keyGen" | "encapDecap")[],
  functions: readonly MlKemFunction[] = ["encapsulation", "decapsulation"],
  parameterSets: readonly MlKemParameterSet[] = ["ML-KEM-512"]
) {
  return buildRegistrationAlgorithms({
    config: getFipsConfig("FIPS203"),
    modes,
    parameterSets: [...parameterSets],
    functions: [...functions]
  });
}

describe("registration builder", () => {
  it("builds ML-DSA keyGen without signature fields", () => {
    const registration = buildFips204("keyGen");
    expect(registration).toEqual({
      algorithm: "ML-DSA",
      mode: "keyGen",
      revision: "FIPS204",
      prereqVals: [{ algorithm: "SHA", valValue: "same" }],
      parameterSets: ["ML-DSA-44"]
    });
  });

  it("builds ML-DSA sigGen with deterministic signature capabilities", () => {
    const registration = buildFips204("sigGen");
    expect(registration.deterministic).toEqual([true, false]);
    expect(registration.signatureInterfaces).toEqual(["internal", "external"]);
    expect(registration.externalMu).toEqual([false, true]);
    expect(registration.preHash).toEqual(["pure", "preHash"]);
    expect(registration.capabilities).toEqual([
      {
        parameterSets: ["ML-DSA-44"],
        messageLength: [{ min: 8, max: 128, increment: 8 }],
        contextLength: [{ min: 0, max: 64, increment: 8 }],
        hashAlgs: ["SHA2-256"]
      }
    ]);
  });

  it("builds ML-DSA sigVer without deterministic", () => {
    const registration = buildFips204("sigVer");
    expect(registration.signatureInterfaces).toEqual(["internal", "external"]);
    expect(registration).not.toHaveProperty("deterministic");
  });

  it("builds ML-KEM keyGen without functions", () => {
    const [registration] = buildFips203(["keyGen"]);
    expect(registration).toEqual({
      algorithm: "ML-KEM",
      mode: "keyGen",
      revision: "FIPS203",
      prereqVals: [{ algorithm: "SHA", valValue: "same" }],
      parameterSets: ["ML-KEM-512"]
    });
  });

  it("builds ML-KEM encapDecap with the selected functions", () => {
    const [registration] = buildFips203(["encapDecap"]);
    expect(registration.functions).toEqual(["encapsulation", "decapsulation"]);
    expect(registration.mode).toBe("encapDecap");
  });

  it("builds two ML-KEM mode registrations", () => {
    const registrations = buildFips203(["keyGen", "encapDecap"]);
    expect(registrations.map((item) => item.mode)).toEqual(["keyGen", "encapDecap"]);
    expect(registrations[0]).not.toHaveProperty("functions");
    expect(registrations[1].functions).toEqual(["encapsulation", "decapsulation"]);
  });

  it("rejects an empty encapDecap function selection", () => {
    expect(() => buildFips203(["encapDecap"], [])).toThrow(
      "Select at least one ML-KEM function"
    );
  });

  it("does not leak ML-DSA fields into ML-KEM registrations", () => {
    for (const registration of buildFips203(["keyGen", "encapDecap"])) {
      for (const field of DSA_ONLY_FIELDS) {
        expect(registration).not.toHaveProperty(field);
      }
    }
  });

  it("preserves parameter set selection", () => {
    const [registration] = buildFips203(
      ["keyGen"],
      [],
      ["ML-KEM-768", "ML-KEM-1024"]
    );
    expect(registration.parameterSets).toEqual(["ML-KEM-768", "ML-KEM-1024"]);
  });

  it("preserves a single selected ML-KEM function", () => {
    const [registration] = buildFips203(["encapDecap"], ["decapsulationKeyCheck"]);
    expect(registration.functions).toEqual(["decapsulationKeyCheck"]);
  });

  it("does not share mutable parameter set arrays between registrations", () => {
    const registrations = buildFips203(["keyGen", "encapDecap"]);
    (registrations[0].parameterSets as JsonObject[]).push({ changed: true });
    expect(registrations[1].parameterSets).toEqual(["ML-KEM-512"]);
  });
});
