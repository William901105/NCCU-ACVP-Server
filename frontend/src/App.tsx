import { useEffect, useMemo, useState } from "react";
import {
  API_BASE_URL,
  ApiError,
  clearDemoData,
  createAcvpSession,
  expectedDeniedView,
  getAcvpExpectedResults,
  getAcvpSession,
  getAcvpSessionResults,
  getAcvpSessionVectorSets,
  getAcvpVectorSetPrompt,
  getAcvpVectorSetResults,
  listAcvpSessions,
  submitAcvpVectorSetResults
} from "./api";
import JsonViewer from "./components/JsonViewer";
import { FIPS_REGISTRY, getFipsConfig } from "./registry";
import type {
  AcvpGenerationProfile,
  AcvpSessionDetail,
  AcvpSessionSummary,
  AcvpVectorSetSummary,
  AcvpWorkflowProfile,
  CapabilityMode,
  FipsVersionConfig,
  FipsVersionId,
  JsonObject,
  JsonValue,
  NormalizedExpectedView,
  NormalizedSessionResultsView,
  NormalizedVectorSetResultView,
  NormalizedVectorSetView,
  Report
} from "./types";

const DEFAULT_TESTS_PER_GROUP = 1;
const DEFAULT_CAMPAIGN_SEED = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF";
const STRICT_EXPECTED_HIDDEN_MESSAGE =
  "Hidden expectedResults: non-sample strict sessions cannot download expected results. Server-side validation still uses hidden expectedResults.";

type IutResponseStatus = "waiting" | "loaded" | "ready" | "error";
type ServerStatus = "checking" | "online" | "offline";
type RawTab = "session" | "prompt" | "expected" | "uploaded" | "vector-results" | "session-results";

export default function App() {
  const [fipsId, setFipsId] = useState<FipsVersionId>("FIPS204");
  const config = useMemo(() => getFipsConfig(fipsId), [fipsId]);
  const [workflowProfile, setWorkflowProfile] = useState<AcvpWorkflowProfile>("strict");
  const [isSample, setIsSample] = useState(false);
  const [selectedModes, setSelectedModes] = useState<CapabilityMode[]>(["keyGen"]);
  const [selectedParameterSets, setSelectedParameterSets] = useState<string[]>(["ML-DSA-44"]);
  const [campaignSeed, setCampaignSeed] = useState(DEFAULT_CAMPAIGN_SEED);
  const [testsPerGroup, setTestsPerGroup] = useState(DEFAULT_TESTS_PER_GROUP);
  const [label, setLabel] = useState("strict ML-DSA registration");
  const [sessions, setSessions] = useState<AcvpSessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<AcvpSessionDetail | null>(null);
  const [vectorSets, setVectorSets] = useState<AcvpVectorSetSummary[]>([]);
  const [activeVectorSetId, setActiveVectorSetId] = useState<string | null>(null);
  const [activeVectorSet, setActiveVectorSet] = useState<NormalizedVectorSetView | null>(null);
  const [expectedView, setExpectedView] = useState<NormalizedExpectedView | null>(null);
  const [uploadedResponse, setUploadedResponse] = useState<JsonValue | null>(null);
  const [uploadedResponseName, setUploadedResponseName] = useState("");
  const [iutResponseStatus, setIutResponseStatus] = useState<IutResponseStatus>("waiting");
  const [iutResponseErrorDetail, setIutResponseErrorDetail] = useState("");
  const [promptImportName, setPromptImportName] = useState("");
  const [vectorResult, setVectorResult] = useState<NormalizedVectorSetResultView | null>(null);
  const [sessionResults, setSessionResults] = useState<NormalizedSessionResultsView | null>(null);
  const [message, setMessage] = useState("");
  const [serverStatus, setServerStatus] = useState<ServerStatus>("checking");
  const [rawTab, setRawTab] = useState<RawTab>("prompt");
  const [isBusy, setIsBusy] = useState(false);

  const isEnabled = config.enabled;
  const isStrict = workflowProfile === "strict";
  const generationProfile: AcvpGenerationProfile = isStrict ? "nist-conformance" : "local-debug";
  const activeVectorSummary = vectorSets.find((item) => item.vectorSetId === activeVectorSetId) ?? null;
  const activeReport = vectorResult?.report ?? null;
  const policyWorkflowProfile = activeVectorSet ? workflowProfileForVectorSet(activeVectorSet) : "strict";
  const requestWorkflowProfile = activeVectorSet ? policyWorkflowProfile : workflowProfile;
  const policyIsStrict = policyWorkflowProfile === "strict";
  const canUploadResponse = Boolean(activeSession && activeVectorSetId) && !isBusy;
  const campaignSeedValidation = useMemo(() => validateCampaignSeed(campaignSeed), [campaignSeed]);
  const campaignSeedInvalid = isEnabled && !campaignSeedValidation.valid;
  const iutResponseLabel = responseStatusLabel(iutResponseStatus);
  const canSubmitResponse = Boolean(activeVectorSetId && uploadedResponse != null && iutResponseStatus === "ready") && !isBusy;
  const activeVectorIsSample = vectorSetIsSample(activeVectorSet, activeSession, isSample);
  const activeProviderLabel = providerShortLabel(activeVectorSummary, activeSession);
  const activeExpectedDebugOnly = vectorExpectedDebugOnly(activeVectorSummary, activeSession);
  const rawInspectorValue = rawValueForTab(rawTab, activeSession, activeVectorSet, expectedView, uploadedResponse, vectorResult, sessionResults);

  useEffect(() => {
    setSelectedModes(config.modes.filter((mode) => mode.enabled).slice(0, 1).map((mode) => mode.id));
    setSelectedParameterSets(config.defaultParameterSets);
    clearWorkspace();
    if (config.enabled) {
      refreshSessions().catch((error: Error) => setMessage(error.message));
    } else {
      setSessions([]);
      setServerStatus("online");
    }
  }, [config.id, workflowProfile]);

  async function refreshSessions() {
    if (!config.enabled) {
      return;
    }
    setServerStatus("checking");
    try {
      const items = await listAcvpSessions({ workflowProfile });
      setSessions(items);
      setServerStatus("online");
    } catch (error) {
      setServerStatus("offline");
      throw error;
    }
  }

  function applyWorkflowProfile(profile: AcvpWorkflowProfile) {
    setWorkflowProfile(profile);
    if (profile === "strict") {
      setIsSample(false);
      setLabel("strict ML-DSA registration");
    } else {
      setIsSample(true);
      setLabel("local ML-DSA registration");
    }
    clearWorkspace();
  }

  async function createRegistrationSession() {
    if (!isEnabled) {
      return;
    }
    if (selectedModes.length === 0 || selectedParameterSets.length === 0) {
      setMessage("Select at least one mode and one parameter set.");
      return;
    }
    if (!campaignSeedValidation.valid) {
      setMessage(campaignSeedValidation.message);
      return;
    }
    await runBusy(async () => {
      const trimmedCampaignSeed = campaignSeed.trim();
      const payload: JsonObject = {
        algorithms: buildRegistrationAlgorithms(config, selectedModes, selectedParameterSets),
        label,
        generationProfile,
        isSample,
        autoGenerateVectorSets: true
      };
      if (trimmedCampaignSeed) {
        payload.campaignSeed = trimmedCampaignSeed;
      }
      if (!isStrict) {
        payload.testsPerGroup = testsPerGroup;
      }
      const created = await createAcvpSession(payload as JsonValue, {
        workflowProfile,
        generationProfile,
        isSample
      });
      await refreshSessions();
      await activateSession(created.testSessionId);
      setMessage("Test session created.");
    });
  }

  async function importPrompt(file: File | null) {
    if (!file || !isEnabled) {
      return;
    }
    await runBusy(async () => {
      const prompt = await readJsonFile(file);
      const created = await createAcvpSession(
        {
          prompt,
          label: `prompt:${file.name}`,
          autoGenerateExpectedResults: true,
          isSample
        } as JsonValue,
        {
          workflowProfile,
          isSample
        }
      );
      setPromptImportName(file.name);
      await refreshSessions();
      await activateSession(created.testSessionId);
      setMessage("Prompt imported.");
    });
  }

  async function activateSession(sessionId: string) {
    await runBusy(async () => {
      const detail = await getAcvpSession(sessionId, { workflowProfile });
      const vectors = await getAcvpSessionVectorSets(sessionId, { workflowProfile });
      setActiveSession(detail);
      setVectorSets(vectors);
      setSessionResults(null);
      setVectorResult(null);
      setUploadedResponse(null);
      setUploadedResponseName("");
      setIutResponseStatus("waiting");
      setIutResponseErrorDetail("");
      const firstVectorId = vectors[0]?.vectorSetId ?? null;
      setActiveVectorSetId(firstVectorId);
      if (firstVectorId) {
        await loadVectorSet(firstVectorId, detail.testSessionId, detail);
      } else {
        setActiveVectorSet(null);
        setExpectedView(null);
      }
    });
  }

  async function activateVectorSet(vectorSetId: string) {
    const sessionId = activeSession?.testSessionId;
    if (!sessionId) {
      setMessage("Select a Test Session before opening a vector set.");
      return;
    }
    await runBusy(async () => {
      await loadVectorSet(vectorSetId, sessionId, activeSession);
    });
  }

  async function loadVectorSet(vectorSetId: string, sessionId: string, session: AcvpSessionDetail | null) {
    const vector = await getAcvpVectorSetPrompt(sessionId, vectorSetId, { workflowProfile });
    const vectorSample = vectorSetIsSample(vector, session, isSample);
    setActiveVectorSetId(vectorSetId);
    setActiveVectorSet(vector);
    setVectorResult(null);
    setSessionResults(null);
    setUploadedResponse(null);
    setUploadedResponseName("");
    setIutResponseStatus("waiting");
    setIutResponseErrorDetail("");
    setRawTab("prompt");

    const vectorWorkflowProfile = workflowProfileForVectorSet(vector);
    if (vectorWorkflowProfile === "strict" && !vectorSample) {
      setExpectedView(expectedDeniedView(STRICT_EXPECTED_HIDDEN_MESSAGE));
    } else {
      await loadExpectedResults(sessionId, vectorSetId, false, vectorWorkflowProfile, vectorSample);
    }

    setVectorSets(await getAcvpSessionVectorSets(sessionId, { workflowProfile }));
  }

  async function loadExpectedResults(
    sessionId?: string,
    vectorSetId?: string,
    automatic = false,
    profileOverride?: AcvpWorkflowProfile,
    sampleOverride?: boolean
  ) {
    const resolvedSessionId = sessionId ?? activeSession?.testSessionId;
    const resolvedVectorSetId = vectorSetId ?? activeVectorSetId;
    const expectedWorkflowProfile = profileOverride ?? requestWorkflowProfile;
    const expectedIsSample = sampleOverride ?? activeVectorIsSample;
    if (!resolvedSessionId || !resolvedVectorSetId) {
      setMessage("Select a Test Session and Vector Set before requesting expected results.");
      return;
    }
    if (automatic && expectedWorkflowProfile === "strict" && !expectedIsSample) {
      setExpectedView(expectedDeniedView(STRICT_EXPECTED_HIDDEN_MESSAGE));
      return;
    }
    try {
      const expected = await getAcvpExpectedResults(resolvedSessionId, resolvedVectorSetId, { workflowProfile: expectedWorkflowProfile });
      setExpectedView(expected);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setExpectedView(expectedDeniedView(error.message));
        return;
      }
      throw error;
    }
  }

  async function loadResponseFile(file: File | null) {
    if (!file) {
      return;
    }
    try {
      setUploadedResponse(await readJsonFile(file));
      setUploadedResponseName(file.name);
      setIutResponseStatus("ready");
      setIutResponseErrorDetail("");
      setVectorResult(null);
      setSessionResults(null);
      setRawTab("uploaded");
      setMessage("Browser JSON syntax check passed. Backend validates ACVP schema on submit.");
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Invalid response JSON.";
      setIutResponseStatus("error");
      setIutResponseErrorDetail(errorMessage);
      setMessage(errorMessage);
    }
  }

  async function submitResponse() {
    if (!activeSession || !activeVectorSetId || uploadedResponse == null) {
      setMessage("Select a vector set and upload a response JSON.");
      return;
    }
    await runBusy(async () => {
      setIutResponseStatus("loaded");
      setIutResponseErrorDetail("");
      const immediateResult = await submitAcvpVectorSetResults(
        activeSession.testSessionId,
        activeVectorSetId,
        uploadedResponse,
        { workflowProfile: policyWorkflowProfile }
      );
      const result = policyIsStrict
        ? await getAcvpVectorSetResults(activeSession.testSessionId, activeVectorSetId, { workflowProfile: policyWorkflowProfile })
        : immediateResult ?? (await getAcvpVectorSetResults(activeSession.testSessionId, activeVectorSetId, { workflowProfile: policyWorkflowProfile }));
      setVectorResult(result);
      setIutResponseStatus("ready");
      setIutResponseErrorDetail("");
      setActiveSession(await getAcvpSession(activeSession.testSessionId, { workflowProfile: policyWorkflowProfile }));
      setVectorSets(await getAcvpSessionVectorSets(activeSession.testSessionId, { workflowProfile: policyWorkflowProfile }));
      setSessionResults(await getAcvpSessionResults(activeSession.testSessionId, { workflowProfile: policyWorkflowProfile }));
      setRawTab("vector-results");
      setMessage(policyIsStrict ? "Response accepted with 204 No Content. Disposition loaded from GET results." : "Response validated.");
    }, (errorMessage) => {
      setIutResponseStatus("error");
      setIutResponseErrorDetail(errorMessage);
    });
  }

  async function refreshSessionResults() {
    if (!activeSession) {
      setMessage("Select a Test Session before requesting session results.");
      return;
    }
    await runBusy(async () => {
      setSessionResults(await getAcvpSessionResults(activeSession.testSessionId, { workflowProfile: requestWorkflowProfile }));
      setRawTab("session-results");
    });
  }

  async function cleanAllData() {
    const confirmed = window.confirm(
      "This deletes all local demo database records for sessions, vector sets, prompts, responses, reports, and the current SQLite file. Continue?"
    );
    if (!confirmed) {
      return;
    }
    await runBusy(async () => {
      const result = await clearDemoData();
      clearWorkspace();
      setSessions([]);
      setMessage(`${result.message} Deleted files: ${result.deletedFiles.length}.`);
      await refreshSessions();
    });
  }

  function clearWorkspace() {
    setActiveSession(null);
    setVectorSets([]);
    setActiveVectorSetId(null);
    setActiveVectorSet(null);
    setExpectedView(null);
    setUploadedResponse(null);
    setUploadedResponseName("");
    setIutResponseStatus("waiting");
    setIutResponseErrorDetail("");
    setPromptImportName("");
    setVectorResult(null);
    setSessionResults(null);
    setMessage("");
  }

  async function runBusy(work: () => Promise<void>, onError?: (message: string) => void) {
    setIsBusy(true);
    setMessage("");
    try {
      await work();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Operation failed.";
      setMessage(errorMessage);
      onError?.(errorMessage);
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">NCCU ACVP Server</p>
          <h1>Strict workflow-aware ACVP client</h1>
          <p className="topbar-detail">Backend {API_BASE_URL}</p>
        </div>
        {activeVectorSet ? (
          <div className="status-cluster">
            <StatusChip label={serverStatus} tone={serverStatus} />
            <StatusChip label={policyWorkflowProfile} tone={policyWorkflowProfile} />
            <StatusChip label={activeProviderLabel} tone="info" />
            <StatusChip label={activeVectorIsSample ? "sample" : "non-sample"} tone={activeVectorIsSample ? "sample" : "non-sample"} />
            <StatusChip label="not production ACVP" tone="warning" />
          </div>
        ) : null}
        <div className="actions">
          <button type="button" onClick={() => refreshSessions().catch((error: Error) => setMessage(error.message))} disabled={!isEnabled || isBusy}>
            Refresh
          </button>
          <button type="button" className="secondary" onClick={clearWorkspace} disabled={isBusy}>
            Clear
          </button>
          <button type="button" className="danger" onClick={cleanAllData} disabled={isBusy}>
            Clean
          </button>
        </div>
      </header>

      {message ? <div className="notice">{message}</div> : null}

      <section className="workflow-grid">
        <section className="panel stack">
          <div className="panel-header">
            <h2>Algorithm registry</h2>
            <StatusChip label={config.status} tone={config.enabled ? "ready" : "in-development"} />
          </div>
          <label className="field">
            <span>FIPS version</span>
            <select value={fipsId} onChange={(event) => setFipsId(event.target.value as FipsVersionId)}>
              {FIPS_REGISTRY.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <MetadataGrid
            items={[
              ["algorithm", config.algorithm],
              ["revision", config.revision],
              ["status", config.status],
              ["enabled", config.enabled ? "yes" : "no"]
            ]}
          />
          {!isEnabled ? <div className="development-banner">{config.disabledReason ?? "Backend is not available."}</div> : null}

          <CapabilityControls
            config={config}
            selectedModes={selectedModes}
            selectedParameterSets={selectedParameterSets}
            disabled={!isEnabled || isBusy}
            onToggleMode={(mode) => setSelectedModes((current) => toggleValue(current, mode))}
            onToggleParameterSet={(parameterSet) => setSelectedParameterSets((current) => toggleValue(current, parameterSet))}
          />
        </section>

        <section className="panel stack">
          <div className="panel-header">
            <h2>Workflow controls</h2>
            <StatusChip label={workflowProfile} tone={workflowProfile} />
          </div>
          <div className="control-group">
            <span>workflowProfile</span>
            <div className="segmented fixed">
              <button type="button" className={isStrict ? "active" : "secondary"} onClick={() => applyWorkflowProfile("strict")} disabled={isBusy}>
                Strict
              </button>
              <button type="button" className={!isStrict ? "active" : "secondary"} onClick={() => applyWorkflowProfile("local")} disabled={isBusy}>
                Local
              </button>
            </div>
            <p className="subtle">
              {isStrict
                ? "Canonical nested routes, direct ACVP payloads, 204 result submission, GET results for disposition."
                : "Local skeleton wrappers, expectedResults download, immediate validation body for demo/debug."}
            </p>
          </div>

          <div className="control-group">
            <span>isSample</span>
            <div className="segmented fixed">
              <button type="button" className={isSample ? "active" : "secondary"} onClick={() => setIsSample(true)} disabled={!isEnabled || isBusy}>
                Sample
              </button>
              <button type="button" className={!isSample ? "active" : "secondary"} onClick={() => setIsSample(false)} disabled={!isEnabled || isBusy}>
                Non-sample
              </button>
            </div>
            <p className="subtle">
              {isStrict && !isSample ? STRICT_EXPECTED_HIDDEN_MESSAGE : "Sample sessions may download expected results from the UI."}
            </p>
          </div>

          <button type="button" className="secondary" onClick={() => applyWorkflowProfile("local")} disabled={isBusy}>
            Quick local demo preset
          </button>
        </section>

        <section className="panel stack">
          <div className="panel-header">
            <h2>Create Test Session</h2>
            <StatusChip label={isEnabled ? "ready" : "disabled"} tone={isEnabled ? "ready" : "pending"} />
          </div>
          <label className="field">
            <span>Label</span>
            <input value={label} onChange={(event) => setLabel(event.target.value)} disabled={!isEnabled || isBusy} />
          </label>
          <label className={`field ${campaignSeedInvalid ? "invalid" : ""}`}>
            <span>Campaign seed</span>
            <input
              value={campaignSeed}
              onChange={(event) => setCampaignSeed(event.target.value)}
              disabled={!isEnabled || isBusy}
              aria-invalid={campaignSeedInvalid}
              aria-describedby="campaign-seed-hint"
            />
            <small id="campaign-seed-hint" className={campaignSeedInvalid ? "field-error" : "field-hint"}>
              {campaignSeedValidation.message}
            </small>
          </label>
          {!isStrict ? (
            <label className="field short">
              <span>Tests per group</span>
              <input
                type="number"
                min={1}
                max={10}
                value={testsPerGroup}
                onChange={(event) => setTestsPerGroup(Number(event.target.value))}
                disabled={!isEnabled || isBusy}
              />
            </label>
          ) : null}
          <button type="button" onClick={createRegistrationSession} disabled={!isEnabled || isBusy || campaignSeedInvalid}>
            Create session
          </button>
          <label className={`file-button ${isEnabled && !isBusy ? "" : "disabled"}`} aria-disabled={!isEnabled || isBusy}>
            <span>Import prompt JSON</span>
            <input
              type="file"
              accept="application/json,.json"
              disabled={!isEnabled || isBusy}
              onChange={(event) => {
                const file = event.currentTarget.files?.[0] ?? null;
                void importPrompt(file);
                event.currentTarget.value = "";
              }}
            />
          </label>
          {promptImportName ? <p className="subtle">{promptImportName}</p> : null}
        </section>

        <section className="panel stack">
          <div className="panel-header">
            <h2>Vector Set list</h2>
            <span className="count-pill">{vectorSets.length}</span>
          </div>
          <div className="session-list">
            {sessions.map((session) => (
              <button
                type="button"
                key={session.testSessionId}
                className={`session-row ${session.testSessionId === activeSession?.testSessionId ? "active-row" : ""}`}
                onClick={() => activateSession(session.testSessionId)}
                disabled={!isEnabled || isBusy}
              >
                <span>{session.label ?? session.testSessionId}</span>
                <strong>{session.status}</strong>
                <small>{session.vectorSetCount} vector sets</small>
              </button>
            ))}
            {sessions.length === 0 ? <p className="empty-state">No sessions.</p> : null}
          </div>
          <div className="vector-toolbar">
            {vectorSets.map((vector) => (
              <button
                type="button"
                key={vector.vectorSetId}
                className={vector.vectorSetId === activeVectorSetId ? "active" : "secondary"}
                onClick={() => activateVectorSet(vector.vectorSetId)}
                disabled={!isEnabled || isBusy}
              >
                {vector.mode ?? "vector"} / {vector.status}
              </button>
            ))}
          </div>
          <SessionVectorMetadata session={activeSession} vector={activeVectorSummary} />
        </section>

        <section className="panel stack wide-panel">
          <div className="panel-header">
            <h2>Prompt download / preview</h2>
            <StatusChip label={activeVectorSet?.sourceShape ?? "not loaded"} tone={activeVectorSet?.sourceShape === "strict-payload" ? "strict" : "local"} />
          </div>
          <div className="actions">
            <button
              type="button"
              onClick={() => activeVectorSet && downloadJson(`prompt-${activeVectorSet.vectorSetId ?? activeVectorSetId ?? "vector"}.json`, activeVectorSet.prompt)}
              disabled={!activeVectorSet}
            >
              Download prompt
            </button>
          </div>
          <JsonPane title="Prompt" value={activeVectorSet?.prompt ?? null} />
        </section>

        <section className="panel stack">
          <div className="panel-header">
            <h2>ExpectedResults policy</h2>
            <StatusChip label={expectedStatusLabel(expectedView)} tone={expectedTone(expectedView)} />
          </div>
          <p className="subtle">
            {expectedView?.reason ??
              (activeExpectedDebugOnly
                ? "NIST expectedResults are retained for debug/sample inspection only. Validation uses internalProjection.json."
                : policyIsStrict
                ? "Strict sample vector sets return direct expected payloads. Strict non-sample vector sets hide expected results."
                : "Local mode preserves the local expectedResults wrapper behavior.")}
          </p>
          <div className="actions">
            <button
              type="button"
              onClick={() => loadExpectedResults().catch((error: Error) => setMessage(error.message))}
              disabled={!activeVectorSet || (policyIsStrict && !activeVectorIsSample) || isBusy}
            >
              Load expected
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => expectedView?.expectedResults && downloadJson(`expectedResults-${activeVectorSetId ?? "vector"}.json`, expectedView.expectedResults)}
              disabled={!expectedView?.expectedResults}
            >
              Download expected
            </button>
          </div>
          <JsonPane title="Expected" value={expectedView?.expectedResults ?? null} />
        </section>

        <section className="panel stack">
          <div className="panel-header">
            <h2>IUT response upload</h2>
            <StatusChip label={iutResponseLabel} tone={iutResponseStatus} />
          </div>
          <label className={`file-button ${canUploadResponse ? "" : "disabled"}`} aria-disabled={!canUploadResponse}>
            <span>Upload response JSON</span>
            <input
              type="file"
              accept="application/json,.json"
              disabled={!canUploadResponse}
              onChange={(event) => {
                const file = event.currentTarget.files?.[0] ?? null;
                void loadResponseFile(file);
                event.currentTarget.value = "";
              }}
            />
          </label>
          <p className="subtle">Browser only checks JSON syntax. Backend validates ACVP schema.</p>
          {!activeSession ? (
            <p className="subtle">Select a Test Session before uploading a response JSON.</p>
          ) : !activeVectorSetId ? (
            <p className="subtle">Select a Vector Set before uploading a response JSON.</p>
          ) : null}
          {uploadedResponseName ? <p className="subtle">{uploadedResponseName}</p> : null}
          {iutResponseStatus === "error" && iutResponseErrorDetail ? (
            <p className="response-error-detail">{iutResponseErrorDetail}</p>
          ) : null}
          <button type="button" onClick={submitResponse} disabled={!canSubmitResponse}>
            Submit response
          </button>
          <JsonPane title="Uploaded response" value={uploadedResponse} />
        </section>

        <section className="panel stack wide-panel">
          <div className="panel-header">
            <h2>VectorSet results</h2>
            <StatusChip label={vectorResult?.disposition ?? "unreceived"} tone={vectorResult?.disposition ?? "unreceived"} />
          </div>
          <SummaryStrip result={vectorResult} sessionResults={sessionResults} />
          <div className="actions">
            <button
              type="button"
              onClick={() =>
                activeSession &&
                activeVectorSetId &&
                getAcvpVectorSetResults(activeSession.testSessionId, activeVectorSetId, { workflowProfile: requestWorkflowProfile })
                  .then((result) => {
                    setVectorResult(result);
                    setRawTab("vector-results");
                  })
                  .catch((error: Error) => setMessage(error.message))
              }
              disabled={!activeSession || !activeVectorSetId || isBusy}
            >
              GET vectorSet results
            </button>
            <button type="button" className="secondary" onClick={refreshSessionResults} disabled={!activeSession || isBusy}>
              GET session results
            </button>
            {policyIsStrict ? (
              <>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => vectorResult && downloadJson(`vectorSet-results-${activeVectorSetId ?? "vector"}.json`, vectorResult.raw ?? vectorResult)}
                  disabled={!activeVectorSet || !vectorResult}
                >
                  Export vectorSet results JSON
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => sessionResults && downloadJson(`session-results-${activeSession?.testSessionId ?? "session"}.json`, sessionResults.raw ?? sessionResults)}
                  disabled={!activeVectorSet || !sessionResults}
                >
                  Export session results JSON
                </button>
              </>
            ) : (
              <button type="button" className="secondary" onClick={() => activeReport && downloadJson(`report-${activeReport.importId}.json`, activeReport)} disabled={!activeReport}>
                Export local report JSON
              </button>
            )}
          </div>
          <ResultTable result={vectorResult} />
          <ReportPane report={activeReport} />
        </section>

        <section className="panel stack">
          <div className="panel-header">
            <h2>TestSession results</h2>
            <StatusChip label={sessionResults?.passed === true ? "passed" : sessionResults?.passed === false ? "fail" : "not loaded"} tone={sessionResults?.passed === true ? "passed" : sessionResults?.passed === false ? "fail" : "pending"} />
          </div>
          <SessionResultsList results={sessionResults} />
        </section>

        <section className="panel stack wide-panel">
          <div className="panel-header">
            <h2>Raw JSON inspector</h2>
            <StatusChip label={rawTab} tone="info" />
          </div>
          <div className="segmented raw-tabs">
            {RAW_TABS.map((tab) => (
              <button key={tab.id} type="button" className={rawTab === tab.id ? "active" : "secondary"} onClick={() => setRawTab(tab.id)}>
                {tab.label}
              </button>
            ))}
          </div>
          <JsonPane title={RAW_TABS.find((tab) => tab.id === rawTab)?.label ?? "Raw"} value={rawInspectorValue} />
        </section>

        <section className="panel stack">
          <div className="panel-header">
            <h2>Warnings / remaining gaps</h2>
            <StatusChip label="demo" tone="warning" />
          </div>
          <ul className="warning-list">
            <li>This UI is not a production ACVP client.</li>
            <li>Auth, JWT, mTLS, `/large`, and async validation are not implemented.</li>
            <li>Strict ML-DSA generation and validation use the NIST GenVal adapter when the .NET runner is built.</li>
            <li>FIPS203 / ML-KEM backend is not merged yet.</li>
            <li>HTTP 204 only means the response was accepted; disposition comes from GET results.</li>
          </ul>
        </section>
      </section>
    </main>
  );
}

const RAW_TABS: { id: RawTab; label: string }[] = [
  { id: "session", label: "session" },
  { id: "prompt", label: "vectorSet prompt" },
  { id: "expected", label: "expected" },
  { id: "uploaded", label: "uploaded response" },
  { id: "vector-results", label: "vectorSet results" },
  { id: "session-results", label: "session results" }
];

function CapabilityControls({
  config,
  selectedModes,
  selectedParameterSets,
  disabled,
  onToggleMode,
  onToggleParameterSet
}: {
  config: FipsVersionConfig;
  selectedModes: CapabilityMode[];
  selectedParameterSets: string[];
  disabled: boolean;
  onToggleMode: (mode: CapabilityMode) => void;
  onToggleParameterSet: (parameterSet: string) => void;
}) {
  return (
    <>
      <div className="control-group">
        <span>Modes</span>
        <div className="segmented">
          {config.modes.length === 0 ? <p className="subtle">No backend modes are available.</p> : null}
          {config.modes.map((mode) => (
            <button
              type="button"
              key={mode.id}
              className={selectedModes.includes(mode.id) ? "active" : "secondary"}
              onClick={() => onToggleMode(mode.id)}
              disabled={disabled || !mode.enabled}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>
      <div className="control-group">
        <span>Parameter sets</span>
        <div className="segmented">
          {config.parameterSets.length === 0 ? <p className="subtle">No backend parameter sets are available.</p> : null}
          {config.parameterSets.map((parameterSet) => (
            <button
              type="button"
              key={parameterSet}
              className={selectedParameterSets.includes(parameterSet) ? "active" : "secondary"}
              onClick={() => onToggleParameterSet(parameterSet)}
              disabled={disabled}
            >
              {parameterSet}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

function MetadataGrid({ items }: { items: [string, string | number][] }) {
  return (
    <dl className="metadata-grid">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function SessionVectorMetadata({ session, vector }: { session: AcvpSessionDetail | null; vector: AcvpVectorSetSummary | null }) {
  const generation = vectorGenerationMetadata(session);
  const expectedDebugOnly = booleanValue(vector?.expectedResultsDebugOnly) ?? booleanValue(generation?.expectedResultsDebugOnly) ?? false;
  const hasInternalProjection = booleanValue(vector?.hasInternalProjection) ?? booleanValue(generation?.hasInternalProjection) ?? false;
  return (
    <MetadataGrid
      items={[
        ["session", session?.status ?? "none"],
        ["vector", vector?.status ?? "none"],
        ["provider", providerLabel(vector, session)],
        ["projection", hasInternalProjection ? "internalProjection" : "none"],
        ["expected", expectedDebugOnly ? "debug/sample only" : "standard"],
        ["mode", vector?.mode ?? session?.mode ?? "n/a"],
        ["cases", vector?.testCaseCount ?? session?.testCaseCount ?? 0]
      ]}
    />
  );
}

function providerLabel(vector: AcvpVectorSetSummary | null, session: AcvpSessionDetail | null): string {
  const generation = vectorGenerationMetadata(session);
  return (
    textValue(vector?.providerName) ??
    textValue(vector?.provider) ??
    textValue(generation?.providerName) ??
    textValue(generation?.provider) ??
    "provider n/a"
  );
}

function providerShortLabel(vector: AcvpVectorSetSummary | null, session: AcvpSessionDetail | null): string {
  const generation = vectorGenerationMetadata(session);
  return textValue(vector?.provider) ?? textValue(generation?.provider) ?? providerLabel(vector, session);
}

function vectorExpectedDebugOnly(vector: AcvpVectorSetSummary | null, session: AcvpSessionDetail | null): boolean {
  const generation = vectorGenerationMetadata(session);
  return booleanValue(vector?.expectedResultsDebugOnly) ?? booleanValue(generation?.expectedResultsDebugOnly) ?? false;
}

function vectorGenerationMetadata(session: AcvpSessionDetail | null): Record<string, unknown> | null {
  const value = session?.vectorGeneration;
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function booleanValue(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function SummaryStrip({ result, sessionResults }: { result: NormalizedVectorSetResultView | null; sessionResults: NormalizedSessionResultsView | null }) {
  const validationSummary = result?.validationResult?.summary;
  const tests = result?.tests ?? [];
  const passed = validationSummary?.passed ?? tests.filter((test) => test.result === "passed").length;
  const failed = validationSummary?.failed ?? tests.filter((test) => test.result === "fail" || test.result === "failed").length;
  const missing = validationSummary?.missing ?? tests.filter((test) => test.result === "missing").length;
  const malformed = validationSummary?.malformed ?? tests.filter((test) => test.result === "malformed").length;
  const pending = sessionResults?.results.filter((item) => item.disposition !== "passed" && item.status !== "passed").length ?? 0;
  return (
    <div className="summary-strip">
      <Metric label="passed" value={passed} tone="pass" />
      <Metric label="failed" value={failed} tone="fail" />
      <Metric label="missing" value={missing} tone="warn" />
      <Metric label="malformed" value={malformed} tone="info" />
      <Metric label="session pending" value={pending} tone="neutral" />
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function JsonPane({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="json-pane">
      <h3>{title}</h3>
      {value !== null && value !== undefined ? <JsonViewer value={value} /> : <p className="empty-state">No JSON.</p>}
    </div>
  );
}

function ResultTable({ result }: { result: NormalizedVectorSetResultView | null }) {
  if (!result) {
    return <p className="empty-state">No vectorSet result loaded.</p>;
  }
  if (result.tests.length === 0) {
    return <p className="subtle">Disposition: {result.disposition}. Local validation details are available in the report if present.</p>;
  }
  return (
    <div className="result-table" role="table" aria-label="Vector set result tests">
      <div className="result-row result-head" role="row">
        <span>tcId</span>
        <span>result</span>
        <span>reason</span>
      </div>
      {result.tests.slice(0, 50).map((test, index) => (
        <div className="result-row" role="row" key={`${test.tcId ?? index}-${index}`}>
          <span>{test.tcId ?? "n/a"}</span>
          <span>{test.result ?? "n/a"}</span>
          <span>{test.reason ?? ""}</span>
        </div>
      ))}
      {result.tests.length > 50 ? <p className="subtle">Showing first 50 of {result.tests.length} tests.</p> : null}
    </div>
  );
}

function SessionResultsList({ results }: { results: NormalizedSessionResultsView | null }) {
  if (!results) {
    return <p className="empty-state">No session results loaded.</p>;
  }
  return (
    <div className="session-results-list">
      {results.results.length === 0 ? <p className="empty-state">No vectorSet results.</p> : null}
      {results.results.map((item, index) => (
        <div className="session-result-item" key={`${item.vectorSetUrl}-${index}`}>
          <span>{item.vectorSetUrl}</span>
          <strong>{item.disposition ?? item.status}</strong>
        </div>
      ))}
    </div>
  );
}

function ReportPane({ report }: { report: Report | null }) {
  if (!report) {
    return <p className="empty-state">No local validation report.</p>;
  }
  return <pre className="markdown-preview">{report.markdown}</pre>;
}

function StatusChip({ label, tone }: { label: string; tone: string }) {
  return <span className={`state-chip ${tone}`}>{label}</span>;
}

function responseStatusLabel(status: IutResponseStatus): string {
  if (status === "ready") {
    return "ready";
  }
  if (status === "error") {
    return "error";
  }
  return status;
}

function expectedStatusLabel(view: NormalizedExpectedView | null): string {
  if (!view) {
    return "not loaded";
  }
  if (view.denied) {
    return "denied";
  }
  if (view.available) {
    return "available";
  }
  return "unavailable";
}

function expectedTone(view: NormalizedExpectedView | null): string {
  if (!view) {
    return "pending";
  }
  if (view.denied) {
    return "denied";
  }
  return view.available ? "ready" : "warning";
}

function validateCampaignSeed(value: string): { valid: boolean; message: string } {
  if (!value) {
    return {
      valid: true,
      message: "Leave empty to use the deterministic fallback seed, or enter 32-128 hex characters."
    };
  }
  if (/\s/.test(value)) {
    return {
      valid: false,
      message: "Campaign seed must not contain whitespace."
    };
  }
  if (!/^[0-9a-fA-F]+$/.test(value)) {
    return {
      valid: false,
      message: "Campaign seed must contain only hexadecimal characters."
    };
  }
  if (value.length % 2 !== 0) {
    return {
      valid: false,
      message: "Campaign seed must be an even-length hex string."
    };
  }
  if (value.length < 32 || value.length > 128) {
    return {
      valid: false,
      message: "Campaign seed must be between 32 and 128 hex characters."
    };
  }
  return {
    valid: true,
    message: "Valid seed. Use 32-128 hex characters."
  };
}

function buildRegistrationAlgorithms(config: FipsVersionConfig, modes: CapabilityMode[], parameterSets: string[]): JsonObject[] {
  return modes.map((mode) => {
    if (mode === "keyGen") {
      return {
        algorithm: config.algorithm,
        mode,
        revision: config.revision,
        prereqVals: [{ algorithm: "SHA", valValue: "same" }],
        parameterSets
      };
    }
    const registration: JsonObject = {
      algorithm: config.algorithm,
      mode,
      revision: config.revision,
      prereqVals: [{ algorithm: "SHA", valValue: "same" }],
      signatureInterfaces: ["internal", "external"],
      externalMu: [false, true],
      preHash: ["pure", "preHash"],
      capabilities: [
        {
          parameterSets,
          messageLength: [{ min: 8, max: 128, increment: 8 }],
          contextLength: [{ min: 0, max: 64, increment: 8 }],
          hashAlgs: config.defaultHashAlgs ?? ["SHA2-256"]
        }
      ]
    };
    if (mode === "sigGen") {
      registration.deterministic = [true, false];
    }
    return registration;
  });
}

function vectorSetIsSample(
  vector: NormalizedVectorSetView | null,
  session: AcvpSessionDetail | null,
  fallback: boolean
): boolean {
  const promptSample = vector?.prompt.isSample;
  if (typeof promptSample === "boolean") {
    return promptSample;
  }
  if (typeof session?.isSample === "boolean") {
    return session.isSample;
  }
  return fallback;
}

function workflowProfileForVectorSet(vector: NormalizedVectorSetView): AcvpWorkflowProfile {
  return vector.sourceShape === "strict-payload" ? "strict" : "local";
}

function rawValueForTab(
  tab: RawTab,
  session: AcvpSessionDetail | null,
  vector: NormalizedVectorSetView | null,
  expected: NormalizedExpectedView | null,
  uploaded: JsonValue | null,
  vectorResult: NormalizedVectorSetResultView | null,
  sessionResults: NormalizedSessionResultsView | null
): unknown {
  if (tab === "session") {
    return session;
  }
  if (tab === "prompt") {
    return vector?.raw ?? vector?.prompt ?? null;
  }
  if (tab === "expected") {
    return expected?.raw ?? expected?.expectedResults ?? null;
  }
  if (tab === "uploaded") {
    return uploaded;
  }
  if (tab === "vector-results") {
    return vectorResult?.raw ?? null;
  }
  return sessionResults?.raw ?? null;
}

function toggleValue<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

async function readJsonFile(file: File): Promise<JsonValue> {
  return JSON.parse(await file.text()) as JsonValue;
}

function downloadJson(fileName: string, value: unknown) {
  downloadText(fileName, JSON.stringify(value, null, 2));
}

function downloadText(fileName: string, value: string) {
  const blob = new Blob([value], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}
