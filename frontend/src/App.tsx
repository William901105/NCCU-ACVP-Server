import { useEffect, useMemo, useState } from "react";
import {
  API_BASE_URL,
  ApiError,
  certifyAcvpSession,
  createAcvpSession,
  expectedDeniedView,
  getAcvpExpectedResults,
  getAcvpRequest,
  getAcvpSession,
  getAcvpSessionResults,
  getAcvpSessionVectorSets,
  getAcvpVectorSetPrompt,
  getAcvpVectorSetResults,
  listAcvpSessions,
  submitAcvpVectorSetResults
} from "./api";
import { downloadJson, isAcvpResourceUrl } from "./acvp";
import JsonViewer from "./components/JsonViewer";
import { buildRegistrationAlgorithms } from "./registration";
import { FIPS_REGISTRY, getFipsConfig } from "./registry";
import type {
  AcvpParameterSet,
  AcvpRevision,
  AcvpRequestResource,
  AcvpSessionDetail,
  AcvpSessionRegistration,
  AcvpSessionSummary,
  AcvpVectorSetId,
  AcvpVectorSetSummary,
  CapabilityMode,
  FipsVersionConfig,
  FipsVersionId,
  JsonValue,
  MlKemFunction,
  NormalizedExpectedView,
  NormalizedSessionResultsView,
  NormalizedVectorSetResultView,
  NormalizedVectorSetView
} from "./types";

const DEFAULT_CAMPAIGN_SEED = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF";
const HIDDEN_EXPECTED_MESSAGE = "Expected results are available only for sample vector sets.";
const CERTIFICATION_DISCLAIMER =
  "This server is not connected to an external NIST/CAVP validation authority. The request resource does not represent an issued certificate.";

interface Notice {
  text: string;
  tone: "error" | "success" | "info";
}

export default function App() {
  const [activeFipsId, setActiveFipsId] = useState<FipsVersionId>("FIPS204");
  const config = useMemo(() => getFipsConfig(activeFipsId), [activeFipsId]);
  const [isSample, setIsSample] = useState(false);
  const [selectedModes, setSelectedModes] = useState<CapabilityMode[]>(["keyGen"]);
  const [selectedRevisions, setSelectedRevisions] = useState<
    Partial<Record<CapabilityMode, AcvpRevision>>
  >({ keyGen: "FIPS204" });
  const [selectedParameterSets, setSelectedParameterSets] = useState<AcvpParameterSet[]>([
    "ML-DSA-44"
  ]);
  const [selectedFunctions, setSelectedFunctions] = useState<MlKemFunction[]>([]);
  const [campaignSeed, setCampaignSeed] = useState(DEFAULT_CAMPAIGN_SEED);
  const [label, setLabel] = useState("ML-DSA registration");
  const [sessions, setSessions] = useState<AcvpSessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<AcvpSessionDetail | null>(null);
  const [vectorSets, setVectorSets] = useState<AcvpVectorSetSummary[]>([]);
  const [activeVectorSetId, setActiveVectorSetId] = useState<AcvpVectorSetId | null>(null);
  const [activeVectorSet, setActiveVectorSet] = useState<NormalizedVectorSetView | null>(null);
  const [expectedView, setExpectedView] = useState<NormalizedExpectedView | null>(null);
  const [uploadedResponse, setUploadedResponse] = useState<JsonValue | null>(null);
  const [uploadedResponseName, setUploadedResponseName] = useState("");
  const [vectorResult, setVectorResult] = useState<NormalizedVectorSetResultView | null>(null);
  const [sessionResults, setSessionResults] = useState<NormalizedSessionResultsView | null>(null);
  const [moduleUrl, setModuleUrl] = useState("");
  const [oeUrl, setOeUrl] = useState("");
  const [requestResource, setRequestResource] = useState<AcvpRequestResource | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const activeVectorSummary =
    vectorSets.find((vector) => vector.vsId === activeVectorSetId) ?? null;
  const activeVectorIsSample = vectorIsSample(activeVectorSet, activeSession);
  const seedError = validateCampaignSeed(campaignSeed);
  const registrationError = validateRegistration(
    selectedModes,
    selectedParameterSets,
    selectedFunctions,
    config,
    seedError
  );
  const moduleUrlValid = isAcvpResourceUrl(moduleUrl, "modules");
  const oeUrlValid = isAcvpResourceUrl(oeUrl, "oes");
  const canCertify = Boolean(
    activeSession?.passed &&
      activeSession.publishable &&
      moduleUrlValid &&
      oeUrlValid &&
      !isBusy
  );

  useEffect(() => {
    refreshSessions().catch(showError);
  }, []);

  async function refreshSessions() {
    const summaries = await listAcvpSessions();
    const detailed = await Promise.all(
      summaries.map(async (summary) => {
        try {
          return { ...summary, ...(await getAcvpSession(summary.testSessionId)) };
        } catch {
          return summary;
        }
      })
    );
    setSessions(detailed);
  }

  function selectAlgorithm(id: FipsVersionId) {
    const nextConfig = getFipsConfig(id);
    setActiveFipsId(id);
    setSelectedModes([...nextConfig.defaultModes]);
    setSelectedRevisions(defaultRevisions(nextConfig));
    setSelectedParameterSets([...nextConfig.defaultParameterSets]);
    setSelectedFunctions([...(nextConfig.defaultFunctions ?? [])]);
    setLabel(`${nextConfig.algorithm} registration`);
    setNotice(null);
  }

  async function createSession() {
    if (registrationError) {
      setNotice({ text: registrationError, tone: "error" });
      return;
    }
    await runBusy(async () => {
      const payload: AcvpSessionRegistration = {
        algorithms: buildRegistrationAlgorithms({
          config,
          modes: selectedModes,
          parameterSets: selectedParameterSets,
          functions: selectedFunctions,
          revisions: selectedRevisions
        }),
        label,
        isSample,
        autoGenerateVectorSets: true,
        testsPerGroup: 1
      };
      if (campaignSeed.trim()) {
        payload.campaignSeed = campaignSeed.trim();
      }
      const created = await createAcvpSession(payload);
      await refreshSessions();
      await activateSession(created.testSessionId);
      setNotice({ text: "ACVP test session created.", tone: "success" });
    });
  }

  async function activateSession(sessionId: string) {
    setNotice(null);
    await runBusy(async () => {
      const [session, vectors] = await Promise.all([
        getAcvpSession(sessionId),
        getAcvpSessionVectorSets(sessionId)
      ]);
      setActiveSession(session);
      setVectorSets(vectors);
      clearVectorWorkspace();
      setRequestResource(null);
      const vsId = vectors[0]?.vsId ?? null;
      if (vsId !== null) {
        await openVectorSet(session.testSessionId, vsId, session);
      }
    });
  }

  async function openVectorSet(
    sessionId: string,
    vsId: AcvpVectorSetId,
    session = activeSession
  ) {
    setNotice(null);
    const vector = await getAcvpVectorSetPrompt(sessionId, vsId);
    setActiveVectorSetId(vsId);
    setActiveVectorSet(vector);
    setExpectedView(null);
    setUploadedResponse(null);
    setUploadedResponseName("");
    setVectorResult(null);
    setSessionResults(null);
    if (!vectorIsSample(vector, session)) {
      setExpectedView(expectedDeniedView(HIDDEN_EXPECTED_MESSAGE));
    }
    setVectorSets(await getAcvpSessionVectorSets(sessionId));
  }

  async function loadExpected() {
    if (!activeSession || activeVectorSetId === null) {
      return;
    }
    if (!activeVectorIsSample) {
      setExpectedView(expectedDeniedView(HIDDEN_EXPECTED_MESSAGE));
      return;
    }
    await runBusy(async () => {
      try {
        setExpectedView(
          await getAcvpExpectedResults(activeSession.testSessionId, activeVectorSetId)
        );
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          setExpectedView(expectedDeniedView(error.message));
          return;
        }
        throw error;
      }
    });
  }

  async function loadResponse(file: File | null) {
    if (!file) {
      return;
    }
    setNotice(null);
    try {
      setUploadedResponse(JSON.parse(await file.text()) as JsonValue);
      setUploadedResponseName(file.name);
      setVectorResult(null);
      setSessionResults(null);
    } catch {
      setNotice({ text: "The selected response file is not valid JSON.", tone: "error" });
    }
  }

  async function submitResponse() {
    if (!activeSession || activeVectorSetId === null || uploadedResponse === null) {
      setNotice({ text: "Select a vector set and response file first.", tone: "error" });
      return;
    }
    await runBusy(async () => {
      await submitAcvpVectorSetResults(
        activeSession.testSessionId,
        activeVectorSetId,
        uploadedResponse
      );
      await refreshResults(activeSession.testSessionId, activeVectorSetId);
      await refreshSessions();
      setNotice({
        text: "Response accepted. NIST GenVal disposition has been refreshed.",
        tone: "success"
      });
    });
  }

  async function refreshResults(
    sessionId = activeSession?.testSessionId,
    vsId = activeVectorSetId
  ) {
    if (!sessionId || vsId === null) {
      return;
    }
    const [result, results, session, vectors] = await Promise.all([
      getAcvpVectorSetResults(sessionId, vsId),
      getAcvpSessionResults(sessionId),
      getAcvpSession(sessionId),
      getAcvpSessionVectorSets(sessionId)
    ]);
    setVectorResult(result);
    setSessionResults(results);
    setActiveSession(session);
    setVectorSets(vectors);
  }

  async function createCertificationRequest() {
    if (!activeSession || !canCertify) {
      return;
    }
    await runBusy(async () => {
      const resource = await certifyAcvpSession(activeSession.testSessionId, {
        moduleUrl,
        oeUrl,
        algorithmPrerequisites: []
      });
      setRequestResource(resource);
      setNotice({ text: "Certification request resource created.", tone: "success" });
    });
  }

  async function refreshCertificationRequest() {
    if (!requestResource) {
      return;
    }
    await runBusy(async () => {
      setRequestResource(await getAcvpRequest(requestResource.url));
      setNotice({ text: "Request resource status refreshed.", tone: "info" });
    });
  }

  function clearVectorWorkspace() {
    setActiveVectorSetId(null);
    setActiveVectorSet(null);
    setExpectedView(null);
    setUploadedResponse(null);
    setUploadedResponseName("");
    setVectorResult(null);
    setSessionResults(null);
  }

  function resetWorkspace() {
    setNotice(null);
    setActiveSession(null);
    setVectorSets([]);
    clearVectorWorkspace();
    setRequestResource(null);
  }

  function downloadArtifact(kind: "prompt" | "expected" | "results" | "session-results") {
    if (activeVectorSetId === null) {
      return;
    }
    const value =
      kind === "prompt"
        ? activeVectorSet?.raw
        : kind === "expected"
          ? expectedView?.raw
          : kind === "results"
            ? vectorResult?.raw
            : sessionResults?.raw;
    if (value === undefined || value === null) {
      return;
    }
    downloadJson(value, `${artifactStem(activeVectorSet, activeVectorSummary, activeVectorSetId)}-${kind}.json`);
  }

  async function runBusy(work: () => Promise<void>) {
    setIsBusy(true);
    try {
      await work();
    } catch (error) {
      showError(error);
    } finally {
      setIsBusy(false);
    }
  }

  function showError(error: unknown) {
    setNotice({ text: formatError(error), tone: "error" });
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">NCCU ACVP Server</p>
          <h1>ACVP Test Sessions</h1>
          <p className="topbar-detail">{API_BASE_URL}</p>
        </div>
        <div className="status-cluster">
          <StatusChip label="Workflow: Strict" tone="strict" />
          <StatusChip label="Execution: NIST GenVal" tone="ready" />
          <button type="button" onClick={() => refreshSessions().catch(showError)} disabled={isBusy}>
            Refresh
          </button>
          <button type="button" className="secondary" onClick={resetWorkspace} disabled={isBusy}>
            Clear
          </button>
        </div>
      </header>

      {notice ? (
        <div className={`notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>
          {notice.text}
        </div>
      ) : null}

      <section className="workflow-grid">
        <section className="panel stack registration-panel">
          <div className="panel-header">
            <h2>{config.label} Registration</h2>
            <StatusChip
              label={`${config.algorithm} / ${selectedRevisionLabel(
                config,
                selectedModes,
                selectedRevisions
              )}`}
              tone="info"
            />
          </div>
          <div className="control-group">
            <span>Algorithm</span>
            <div className="segmented algorithm-selector" aria-label="Algorithm">
              {FIPS_REGISTRY.filter((item) => item.enabled).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={item.id === activeFipsId ? "active" : "secondary"}
                  aria-pressed={item.id === activeFipsId}
                  onClick={() => selectAlgorithm(item.id)}
                  disabled={isBusy}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <CapabilityControls
            config={config}
            selectedModes={selectedModes}
            selectedRevisions={selectedRevisions}
            selectedParameterSets={selectedParameterSets}
            selectedFunctions={selectedFunctions}
            disabled={isBusy}
            onToggleMode={(mode) => setSelectedModes(toggleValue(selectedModes, mode))}
            onSelectRevision={(mode, revision) =>
              setSelectedRevisions({ ...selectedRevisions, [mode]: revision })
            }
            onToggleParameterSet={(value) =>
              setSelectedParameterSets(toggleValue(selectedParameterSets, value))
            }
            onToggleFunction={(value) =>
              setSelectedFunctions(toggleValue(selectedFunctions, value))
            }
          />
          <label className="field">
            <span>Label</span>
            <input value={label} onChange={(event) => setLabel(event.target.value)} disabled={isBusy} />
          </label>
          <label className={`field ${seedError ? "invalid" : ""}`}>
            <span>Campaign seed</span>
            <input
              value={campaignSeed}
              onChange={(event) => setCampaignSeed(event.target.value)}
              disabled={isBusy}
              aria-invalid={Boolean(seedError)}
            />
            {seedError ? <small className="field-error">{seedError}</small> : null}
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={isSample}
              onChange={(event) => setIsSample(event.target.checked)}
              disabled={isBusy}
            />
            <span>Sample session</span>
          </label>
          {registrationError && registrationError !== seedError ? (
            <p className="field-error">{registrationError}</p>
          ) : null}
          <button type="button" onClick={createSession} disabled={isBusy || Boolean(registrationError)}>
            Create test session
          </button>
        </section>

        <section className="panel stack sessions-panel">
          <div className="panel-header">
            <h2>Test Sessions</h2>
            <StatusChip label={String(sessions.length)} tone="info" />
          </div>
          <div className="session-list">
            {sessions.map((session) => (
              <button
                key={session.testSessionId}
                type="button"
                className={`session-row ${activeSession?.testSessionId === session.testSessionId ? "active-row" : ""}`}
                onClick={() => activateSession(session.testSessionId)}
                disabled={isBusy}
              >
                <span>{session.label || session.testSessionId}</span>
                <strong>{session.status}</strong>
                <small>
                  {session.algorithm ?? "Unknown algorithm"} · {session.vectorSetCount ?? session.vectorSetIds.length} vector(s) · {session.isSample ? "sample" : "non-sample"}
                </small>
              </button>
            ))}
            {sessions.length === 0 ? <p className="empty-state">No test sessions.</p> : null}
          </div>
        </section>

        <section className="panel stack wide-panel vector-panel">
          <div className="panel-header">
            <h2>Vector Sets</h2>
            <StatusChip label={activeSession?.status ?? "none"} tone="info" />
          </div>
          <div className="vector-toolbar">
            {vectorSets.map((vector) => (
              <button
                key={vector.vsId}
                type="button"
                className={activeVectorSetId === vector.vsId ? "active" : "secondary"}
                onClick={() => activeSession && openVectorSet(activeSession.testSessionId, vector.vsId)}
                disabled={isBusy}
              >
                {vector.mode || "vector"} / vsId {vector.vsId} / {vector.status}
              </button>
            ))}
          </div>
          <MetadataGrid
            items={[
              ["Algorithm", activeVectorSet?.prompt.algorithm ?? activeVectorSummary?.algorithm ?? "-"],
              ["Revision", activeVectorSet?.prompt.revision ?? activeVectorSummary?.revision ?? "-"],
              ["Mode", activeVectorSet?.prompt.mode ?? activeVectorSummary?.mode ?? "-"],
              ["vsId", activeVectorSetId === null ? "-" : String(activeVectorSetId)],
              ["Provider", activeVectorSummary?.provider ?? activeVectorSummary?.providerName ?? "nist-genval"],
              ["Sample", activeVectorIsSample ? "yes" : "no"],
              ["Status", activeVectorSummary?.status ?? activeVectorSet?.status ?? "-"]
            ]}
          />
          <div className="actions">
            <button
              type="button"
              className="secondary"
              onClick={() => downloadArtifact("prompt")}
              disabled={!activeVectorSet?.raw}
            >
              Download prompt JSON
            </button>
          </div>
          <JsonPane title="Prompt" value={activeVectorSet?.prompt ?? null} />
        </section>

        <section className="panel stack expected-panel">
          <div className="panel-header">
            <h2>Expected Results</h2>
            <StatusChip
              label={expectedView?.denied ? "hidden" : expectedView?.available ? "available" : "not loaded"}
              tone={expectedView?.denied ? "warning" : "info"}
            />
          </div>
          <p className="subtle">
            {activeVectorIsSample
              ? "Sample vector sets may retrieve expected results."
              : HIDDEN_EXPECTED_MESSAGE}
          </p>
          <div className="actions">
            <button
              type="button"
              onClick={loadExpected}
              disabled={!activeVectorSet || !activeVectorIsSample || isBusy}
            >
              Load expected
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => downloadArtifact("expected")}
              disabled={!activeVectorIsSample || !expectedView?.raw}
            >
              Download expected JSON
            </button>
          </div>
          <JsonPane title="Expected" value={expectedView?.expectedResults ?? null} />
        </section>

        <section className="panel stack response-panel">
          <div className="panel-header">
            <h2>IUT Response</h2>
            <StatusChip label={uploadedResponseName || "not loaded"} tone="info" />
          </div>
          <label className={`file-button ${!activeVectorSet || isBusy ? "disabled" : ""}`}>
            <span>Upload response JSON</span>
            <input
              type="file"
              accept="application/json,.json"
              disabled={!activeVectorSet || isBusy}
              onChange={(event) => {
                void loadResponse(event.currentTarget.files?.[0] ?? null);
                event.currentTarget.value = "";
              }}
            />
          </label>
          <button
            type="button"
            onClick={submitResponse}
            disabled={uploadedResponse === null || !activeVectorSet || isBusy}
          >
            Submit response
          </button>
          <JsonPane title="Uploaded response" value={uploadedResponse} />
        </section>

        <section className="panel stack wide-panel results-panel">
          <div className="panel-header">
            <h2>Validation Results</h2>
            <StatusChip label={vectorResult?.disposition ?? "unreceived"} tone="info" />
          </div>
          <div className="actions">
            <button
              type="button"
              onClick={() =>
                activeSession &&
                activeVectorSetId !== null &&
                runBusy(() => refreshResults(activeSession.testSessionId, activeVectorSetId))
              }
              disabled={!activeSession || activeVectorSetId === null || isBusy}
            >
              Refresh results
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => downloadArtifact("results")}
              disabled={!vectorResult?.raw}
            >
              Download vector results JSON
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => downloadArtifact("session-results")}
              disabled={!sessionResults?.raw}
            >
              Download session results JSON
            </button>
          </div>
          <ResultList result={vectorResult} sessionResults={sessionResults} />
          <JsonPane title="Vector set results" value={vectorResult?.raw ?? null} />
          <JsonPane title="Test session results" value={sessionResults?.raw ?? null} />
        </section>

        <section className="panel stack wide-panel certification-panel">
          <div className="panel-header">
            <h2>Certification Request</h2>
            <StatusChip label={requestResource?.status ?? "not requested"} tone="info" />
          </div>
          <div className="certification-grid">
            <label className={`field ${moduleUrl && !moduleUrlValid ? "invalid" : ""}`}>
              <span>Module URL</span>
              <input
                value={moduleUrl}
                placeholder="/acvp/v1/modules/1"
                onChange={(event) => setModuleUrl(event.target.value)}
                disabled={isBusy}
                aria-invalid={Boolean(moduleUrl && !moduleUrlValid)}
              />
            </label>
            <label className={`field ${oeUrl && !oeUrlValid ? "invalid" : ""}`}>
              <span>OE URL</span>
              <input
                value={oeUrl}
                placeholder="/acvp/v1/oes/1"
                onChange={(event) => setOeUrl(event.target.value)}
                disabled={isBusy}
                aria-invalid={Boolean(oeUrl && !oeUrlValid)}
              />
            </label>
          </div>
          <div className="actions">
            <button type="button" onClick={createCertificationRequest} disabled={!canCertify}>
              Create certification request
            </button>
            <button
              type="button"
              className="secondary"
              onClick={refreshCertificationRequest}
              disabled={!requestResource || isBusy}
            >
              Refresh request status
            </button>
          </div>
          {requestResource ? (
            <MetadataGrid
              items={[
                ["Request URL", requestResource.url],
                ["Status", requestResource.status],
                ["Message", requestResource.message ?? "-"],
                ["Approved URL", requestResource.approvedUrl ?? "-"]
              ]}
            />
          ) : null}
          <p className="certification-disclaimer">{CERTIFICATION_DISCLAIMER}</p>
          <JsonPane title="Request resource" value={requestResource?.raw ?? null} />
        </section>
      </section>
    </main>
  );
}

interface CapabilityControlsProps {
  config: FipsVersionConfig;
  selectedModes: CapabilityMode[];
  selectedRevisions: Partial<Record<CapabilityMode, AcvpRevision>>;
  selectedParameterSets: AcvpParameterSet[];
  selectedFunctions: MlKemFunction[];
  disabled: boolean;
  onToggleMode: (mode: CapabilityMode) => void;
  onSelectRevision: (mode: CapabilityMode, revision: AcvpRevision) => void;
  onToggleParameterSet: (value: AcvpParameterSet) => void;
  onToggleFunction: (value: MlKemFunction) => void;
}

function CapabilityControls({
  config,
  selectedModes,
  selectedRevisions,
  selectedParameterSets,
  selectedFunctions,
  disabled,
  onToggleMode,
  onSelectRevision,
  onToggleParameterSet,
  onToggleFunction
}: CapabilityControlsProps) {
  const showFunctions = config.id === "FIPS203" && selectedModes.includes("encapDecap");
  return (
    <>
      <div className="control-group">
        <span>Modes</span>
        <div className="segmented">
          {config.modes.filter((mode) => mode.enabled).map((mode) => (
            <button
              key={mode.id}
              type="button"
              className={selectedModes.includes(mode.id) ? "active" : "secondary"}
              aria-pressed={selectedModes.includes(mode.id)}
              onClick={() => onToggleMode(mode.id)}
              disabled={disabled}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>
      {selectedModes.map((mode) => {
        const modeConfig = config.modes.find((item) => item.id === mode);
        if (!modeConfig) return null;
        return (
          <label className="field" key={`${mode}-revision`}>
            <span>{mode} revision</span>
            <select
              value={selectedRevisions[mode] ?? modeConfig.defaultRevision}
              onChange={(event) =>
                onSelectRevision(mode, event.target.value as AcvpRevision)
              }
              disabled={disabled || modeConfig.revisions.length === 1}
            >
              {modeConfig.revisions.map((revision) => (
                <option key={revision} value={revision}>{revision}</option>
              ))}
            </select>
          </label>
        );
      })}
      <div className="control-group">
        <span>Parameter sets</span>
        <div className="segmented">
          {config.parameterSets.map((value) => (
            <button
              key={value}
              type="button"
              className={selectedParameterSets.includes(value) ? "active" : "secondary"}
              aria-pressed={selectedParameterSets.includes(value)}
              onClick={() => onToggleParameterSet(value)}
              disabled={disabled}
            >
              {value}
            </button>
          ))}
        </div>
      </div>
      {showFunctions ? (
        <div className="control-group">
          <span>ML-KEM functions</span>
          <div className="function-grid">
            {config.functions?.map((value) => (
              <label className="checkbox-field function-option" key={value}>
                <input
                  type="checkbox"
                  checked={selectedFunctions.includes(value)}
                  onChange={() => onToggleFunction(value)}
                  disabled={disabled}
                />
                <span>{value}</span>
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}

function defaultRevisions(
  config: FipsVersionConfig
): Partial<Record<CapabilityMode, AcvpRevision>> {
  return Object.fromEntries(
    config.modes.map((mode) => [mode.id, mode.defaultRevision])
  ) as Partial<Record<CapabilityMode, AcvpRevision>>;
}

function selectedRevisionLabel(
  config: FipsVersionConfig,
  modes: CapabilityMode[],
  revisions: Partial<Record<CapabilityMode, AcvpRevision>>
): string {
  const values = modes.map((mode) => {
    const modeConfig = config.modes.find((item) => item.id === mode);
    return revisions[mode] ?? modeConfig?.defaultRevision ?? config.revision;
  });
  return [...new Set(values)].join(", ") || config.revision;
}

function MetadataGrid({ items }: { items: [string, string][] }) {
  return (
    <dl className="metadata-grid">
      {items.map(([name, value]) => (
        <div key={name}>
          <dt>{name}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function StatusChip({ label, tone }: { label: string; tone: string }) {
  return <span className={`state-chip ${tone}`}>{label}</span>;
}

function JsonPane({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="json-pane">
      <h3>{title}</h3>
      {value === null || value === undefined ? (
        <p className="empty-state">No JSON.</p>
      ) : (
        <JsonViewer value={value} />
      )}
    </div>
  );
}

function ResultList({
  result,
  sessionResults
}: {
  result: NormalizedVectorSetResultView | null;
  sessionResults: NormalizedSessionResultsView | null;
}) {
  if (!result && !sessionResults) {
    return <p className="empty-state">No results loaded.</p>;
  }
  return (
    <div className="session-results-list">
      <strong>Vector disposition: {result?.disposition ?? "unreceived"}</strong>
      {sessionResults?.results.map((item, index) => (
        <div className="session-result-item" key={`${item.vectorSetUrl}-${index}`}>
          <span>{item.vectorSetUrl}</span>
          <strong>{item.disposition ?? item.status}</strong>
        </div>
      ))}
    </div>
  );
}

function vectorIsSample(
  vector: NormalizedVectorSetView | null,
  session: AcvpSessionDetail | null
): boolean {
  return typeof vector?.prompt.isSample === "boolean"
    ? vector.prompt.isSample
    : typeof session?.isSample === "boolean"
      ? session.isSample
      : false;
}

function validateRegistration(
  modes: CapabilityMode[],
  parameterSets: AcvpParameterSet[],
  functions: MlKemFunction[],
  config: FipsVersionConfig,
  seedError: string | null
): string | null {
  if (modes.length === 0 || parameterSets.length === 0) {
    return "Select at least one mode and parameter set.";
  }
  if (config.id === "FIPS203" && modes.includes("encapDecap") && functions.length === 0) {
    return "Select at least one ML-KEM function for encapDecap.";
  }
  return seedError;
}

function validateCampaignSeed(value: string): string | null {
  if (!value) {
    return null;
  }
  if (
    !/^[0-9a-fA-F]+$/.test(value) ||
    value.length % 2 !== 0 ||
    value.length < 32 ||
    value.length > 128
  ) {
    return "Campaign seed must be 32-128 hexadecimal characters.";
  }
  return null;
}

function artifactStem(
  vector: NormalizedVectorSetView | null,
  summary: AcvpVectorSetSummary | null,
  vsId: AcvpVectorSetId
): string {
  const algorithm = vector?.prompt.algorithm ?? summary?.algorithm ?? "ACVP";
  const mode = vector?.prompt.mode ?? summary?.mode ?? "vector";
  return `${algorithm}-${mode}-vs${vsId}`;
}

function formatError(error: unknown): string {
  if (error instanceof ApiError) {
    const code = error.code ?? "ACVP_ERROR";
    const path = error.path ? `; path: ${error.path}` : "";
    return `${code} — ${error.message} (HTTP ${error.status}${path})`;
  }
  return error instanceof Error ? error.message : "Operation failed.";
}

function toggleValue<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}
