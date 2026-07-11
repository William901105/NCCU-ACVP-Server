import { useEffect, useMemo, useState } from "react";
import {
  API_BASE_URL,
  ApiError,
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
import { getFipsConfig } from "./registry";
import type {
  AcvpSessionDetail,
  AcvpSessionSummary,
  AcvpVectorSetSummary,
  CapabilityMode,
  FipsVersionConfig,
  JsonObject,
  JsonValue,
  NormalizedExpectedView,
  NormalizedSessionResultsView,
  NormalizedVectorSetResultView,
  NormalizedVectorSetView
} from "./types";

const CONFIG = getFipsConfig("FIPS204");
const DEFAULT_CAMPAIGN_SEED = "00112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF";
const HIDDEN_EXPECTED_MESSAGE = "Expected results are available only for sample vector sets.";

export default function App() {
  const [isSample, setIsSample] = useState(false);
  const [selectedModes, setSelectedModes] = useState<CapabilityMode[]>(["keyGen"]);
  const [selectedParameterSets, setSelectedParameterSets] = useState<string[]>(["ML-DSA-44"]);
  const [campaignSeed, setCampaignSeed] = useState(DEFAULT_CAMPAIGN_SEED);
  const [label, setLabel] = useState("ML-DSA registration");
  const [sessions, setSessions] = useState<AcvpSessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<AcvpSessionDetail | null>(null);
  const [vectorSets, setVectorSets] = useState<AcvpVectorSetSummary[]>([]);
  const [activeVectorSetId, setActiveVectorSetId] = useState<string | null>(null);
  const [activeVectorSet, setActiveVectorSet] = useState<NormalizedVectorSetView | null>(null);
  const [expectedView, setExpectedView] = useState<NormalizedExpectedView | null>(null);
  const [uploadedResponse, setUploadedResponse] = useState<JsonValue | null>(null);
  const [uploadedResponseName, setUploadedResponseName] = useState("");
  const [vectorResult, setVectorResult] = useState<NormalizedVectorSetResultView | null>(null);
  const [sessionResults, setSessionResults] = useState<NormalizedSessionResultsView | null>(null);
  const [message, setMessage] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const activeVectorSummary = vectorSets.find((vector) => vector.vectorSetId === activeVectorSetId) ?? null;
  const activeVectorIsSample = vectorIsSample(activeVectorSet, activeSession, isSample);
  const seedError = validateCampaignSeed(campaignSeed);

  useEffect(() => {
    refreshSessions().catch(showError);
  }, []);

  async function refreshSessions() {
    const items = await listAcvpSessions();
    setSessions(items);
  }

  async function createSession() {
    if (selectedModes.length === 0 || selectedParameterSets.length === 0) {
      setMessage("Select at least one mode and parameter set.");
      return;
    }
    if (seedError) {
      setMessage(seedError);
      return;
    }
    await runBusy(async () => {
      const payload: JsonObject = {
        algorithms: buildRegistrationAlgorithms(CONFIG, selectedModes, selectedParameterSets),
        label,
        isSample,
        autoGenerateVectorSets: true,
        testsPerGroup: 1
      };
      if (campaignSeed.trim()) {
        payload.campaignSeed = campaignSeed.trim();
      }
      const created = await createAcvpSession(payload, { isSample });
      await refreshSessions();
      await activateSession(created.testSessionId);
      setMessage("Strict NIST GenVal test session created.");
    });
  }

  async function activateSession(sessionId: string) {
    await runBusy(async () => {
      const [session, vectors] = await Promise.all([
        getAcvpSession(sessionId),
        getAcvpSessionVectorSets(sessionId)
      ]);
      setActiveSession(session);
      setVectorSets(vectors);
      setActiveVectorSet(null);
      setExpectedView(null);
      setUploadedResponse(null);
      setUploadedResponseName("");
      setVectorResult(null);
      setSessionResults(null);
      const vectorSetId = vectors[0]?.vectorSetId ?? null;
      setActiveVectorSetId(vectorSetId);
      if (vectorSetId) {
        await openVectorSet(session.testSessionId, vectorSetId, session);
      }
    });
  }

  async function openVectorSet(sessionId: string, vectorSetId: string, session = activeSession) {
    const vector = await getAcvpVectorSetPrompt(sessionId, vectorSetId);
    setActiveVectorSetId(vectorSetId);
    setActiveVectorSet(vector);
    setExpectedView(null);
    setUploadedResponse(null);
    setUploadedResponseName("");
    setVectorResult(null);
    setSessionResults(null);
    if (!vectorIsSample(vector, session, isSample)) {
      setExpectedView(expectedDeniedView(HIDDEN_EXPECTED_MESSAGE));
    }
    setVectorSets(await getAcvpSessionVectorSets(sessionId));
  }

  async function loadExpected() {
    if (!activeSession || !activeVectorSetId) {
      return;
    }
    if (!activeVectorIsSample) {
      setExpectedView(expectedDeniedView(HIDDEN_EXPECTED_MESSAGE));
      return;
    }
    await runBusy(async () => {
      try {
        setExpectedView(await getAcvpExpectedResults(activeSession.testSessionId, activeVectorSetId));
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
    try {
      setUploadedResponse(JSON.parse(await file.text()) as JsonValue);
      setUploadedResponseName(file.name);
      setVectorResult(null);
      setSessionResults(null);
    } catch {
      setMessage("The selected response file is not valid JSON.");
    }
  }

  async function submitResponse() {
    if (!activeSession || !activeVectorSetId || uploadedResponse === null) {
      setMessage("Select a vector set and response file first.");
      return;
    }
    await runBusy(async () => {
      await submitAcvpVectorSetResults(activeSession.testSessionId, activeVectorSetId, uploadedResponse);
      await refreshResults(activeSession.testSessionId, activeVectorSetId);
      setMessage("Response accepted. NIST GenVal disposition has been refreshed.");
    });
  }

  async function refreshResults(sessionId = activeSession?.testSessionId, vectorSetId = activeVectorSetId) {
    if (!sessionId || !vectorSetId) {
      return;
    }
    const [result, results, session, vectors] = await Promise.all([
      getAcvpVectorSetResults(sessionId, vectorSetId),
      getAcvpSessionResults(sessionId),
      getAcvpSession(sessionId),
      getAcvpSessionVectorSets(sessionId)
    ]);
    setVectorResult(result);
    setSessionResults(results);
    setActiveSession(session);
    setVectorSets(vectors);
  }

  function resetWorkspace() {
    setActiveSession(null);
    setVectorSets([]);
    setActiveVectorSetId(null);
    setActiveVectorSet(null);
    setExpectedView(null);
    setUploadedResponse(null);
    setUploadedResponseName("");
    setVectorResult(null);
    setSessionResults(null);
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
    setMessage(error instanceof Error ? error.message : "Operation failed.");
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">NCCU ACVP Server</p>
          <h1>ML-DSA ACVP Test Sessions</h1>
          <p className="topbar-detail">{API_BASE_URL}</p>
        </div>
        <div className="status-cluster">
          <StatusChip label="Workflow: Strict" tone="strict" />
          <StatusChip label="Execution: NIST GenVal" tone="ready" />
          <button type="button" onClick={() => refreshSessions().catch(showError)} disabled={isBusy}>Refresh</button>
          <button type="button" className="secondary" onClick={resetWorkspace} disabled={isBusy}>Clear</button>
        </div>
      </header>

      {message ? <div className="notice">{message}</div> : null}

      <section className="workflow-grid">
        <section className="panel stack">
          <div className="panel-header"><h2>Registration</h2><StatusChip label="ML-DSA / FIPS 204" tone="info" /></div>
          <CapabilityControls
            config={CONFIG}
            selectedModes={selectedModes}
            selectedParameterSets={selectedParameterSets}
            disabled={isBusy}
            onToggleMode={(mode) => setSelectedModes(toggleValue(selectedModes, mode))}
            onToggleParameterSet={(value) => setSelectedParameterSets(toggleValue(selectedParameterSets, value))}
          />
          <label className="field"><span>Label</span><input value={label} onChange={(event) => setLabel(event.target.value)} disabled={isBusy} /></label>
          <label className="field"><span>Campaign seed</span><input value={campaignSeed} onChange={(event) => setCampaignSeed(event.target.value)} disabled={isBusy} /></label>
          <label className="checkbox-field"><input type="checkbox" checked={isSample} onChange={(event) => setIsSample(event.target.checked)} disabled={isBusy} /> <span>Sample session</span></label>
          <button type="button" onClick={createSession} disabled={isBusy || Boolean(seedError)}>Create test session</button>
        </section>

        <section className="panel stack">
          <div className="panel-header"><h2>Test Sessions</h2><StatusChip label={String(sessions.length)} tone="info" /></div>
          <div className="session-list">
            {sessions.map((session) => (
              <button key={session.testSessionId} type="button" className={activeSession?.testSessionId === session.testSessionId ? "active" : "secondary"} onClick={() => activateSession(session.testSessionId)} disabled={isBusy}>
                {session.label || session.testSessionId} ({session.status})
              </button>
            ))}
            {sessions.length === 0 ? <p className="empty-state">No test sessions.</p> : null}
          </div>
        </section>

        <section className="panel stack wide-panel">
          <div className="panel-header"><h2>Vector Sets</h2><StatusChip label={activeSession?.status ?? "none"} tone="info" /></div>
          <div className="vector-toolbar">
            {vectorSets.map((vector) => <button key={vector.vectorSetId} type="button" className={activeVectorSetId === vector.vectorSetId ? "active" : "secondary"} onClick={() => activeSession && openVectorSet(activeSession.testSessionId, vector.vectorSetId)} disabled={isBusy}>{vector.mode || "vector"} ({vector.status})</button>)}
          </div>
          <MetadataGrid items={[["Workflow", activeSession?.workflowPolicy ?? "strict"], ["Execution", activeSession?.executionBackend ?? "nist-genval"], ["Provider", activeVectorSummary?.provider ?? "nist-genval"], ["Sample", activeVectorIsSample ? "yes" : "no"]]} />
          <JsonPane title="Prompt" value={activeVectorSet?.prompt ?? null} />
        </section>

        <section className="panel stack">
          <div className="panel-header"><h2>Expected Results</h2><StatusChip label={expectedView?.denied ? "hidden" : expectedView?.available ? "available" : "not loaded"} tone={expectedView?.denied ? "warning" : "info"} /></div>
          <p className="subtle">{activeVectorIsSample ? "Sample vector sets may retrieve expected results." : HIDDEN_EXPECTED_MESSAGE}</p>
          <button type="button" onClick={loadExpected} disabled={!activeVectorSet || !activeVectorIsSample || isBusy}>Load expected</button>
          <JsonPane title="Expected" value={expectedView?.expectedResults ?? null} />
        </section>

        <section className="panel stack">
          <div className="panel-header"><h2>IUT Response</h2><StatusChip label={uploadedResponseName || "not loaded"} tone="info" /></div>
          <label className="file-button"><span>Upload response JSON</span><input type="file" accept="application/json,.json" disabled={!activeVectorSet || isBusy} onChange={(event) => { void loadResponse(event.currentTarget.files?.[0] ?? null); event.currentTarget.value = ""; }} /></label>
          <button type="button" onClick={submitResponse} disabled={!uploadedResponse || !activeVectorSet || isBusy}>Submit response</button>
          <JsonPane title="Uploaded response" value={uploadedResponse} />
        </section>

        <section className="panel stack wide-panel">
          <div className="panel-header"><h2>Validation Results</h2><StatusChip label={vectorResult?.disposition ?? "unreceived"} tone="info" /></div>
          <div className="actions"><button type="button" onClick={() => activeSession && activeVectorSetId && runBusy(() => refreshResults(activeSession.testSessionId, activeVectorSetId))} disabled={!activeSession || !activeVectorSetId || isBusy}>Refresh results</button></div>
          <ResultList result={vectorResult} sessionResults={sessionResults} />
          <JsonPane title="Vector set results" value={vectorResult?.raw ?? null} />
          <JsonPane title="Test session results" value={sessionResults?.raw ?? null} />
        </section>
      </section>
    </main>
  );
}

function CapabilityControls({ config, selectedModes, selectedParameterSets, disabled, onToggleMode, onToggleParameterSet }: { config: FipsVersionConfig; selectedModes: CapabilityMode[]; selectedParameterSets: string[]; disabled: boolean; onToggleMode: (mode: CapabilityMode) => void; onToggleParameterSet: (value: string) => void }) {
  return <><div className="control-group"><span>Modes</span><div className="segmented">{config.modes.filter((mode) => mode.enabled).map((mode) => <button key={mode.id} type="button" className={selectedModes.includes(mode.id) ? "active" : "secondary"} onClick={() => onToggleMode(mode.id)} disabled={disabled}>{mode.label}</button>)}</div></div><div className="control-group"><span>Parameter sets</span><div className="segmented">{config.parameterSets.map((value) => <button key={value} type="button" className={selectedParameterSets.includes(value) ? "active" : "secondary"} onClick={() => onToggleParameterSet(value)} disabled={disabled}>{value}</button>)}</div></div></>;
}

function MetadataGrid({ items }: { items: [string, string][] }) {
  return <dl className="metadata-grid">{items.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>;
}

function StatusChip({ label, tone }: { label: string; tone: string }) {
  return <span className={`state-chip ${tone}`}>{label}</span>;
}

function JsonPane({ title, value }: { title: string; value: unknown }) {
  return <div className="json-pane"><h3>{title}</h3>{value === null || value === undefined ? <p className="empty-state">No JSON.</p> : <JsonViewer value={value} />}</div>;
}

function ResultList({ result, sessionResults }: { result: NormalizedVectorSetResultView | null; sessionResults: NormalizedSessionResultsView | null }) {
  if (!result && !sessionResults) return <p className="empty-state">No results loaded.</p>;
  return <div className="session-results-list"><strong>Vector disposition: {result?.disposition ?? "unreceived"}</strong>{sessionResults?.results.map((item, index) => <div className="session-result-item" key={`${item.vectorSetUrl}-${index}`}><span>{item.vectorSetUrl}</span><strong>{item.disposition ?? item.status}</strong></div>)}</div>;
}

function buildRegistrationAlgorithms(config: FipsVersionConfig, modes: CapabilityMode[], parameterSets: string[]): JsonObject[] {
  return modes.map((mode) => {
    const registration: JsonObject = { algorithm: config.algorithm, mode, revision: config.revision, prereqVals: [{ algorithm: "SHA", valValue: "same" }], parameterSets };
    if (mode !== "keyGen") {
      registration.signatureInterfaces = ["internal", "external"];
      registration.externalMu = [false, true];
      registration.preHash = ["pure", "preHash"];
      registration.capabilities = [{ parameterSets, messageLength: [{ min: 8, max: 128, increment: 8 }], contextLength: [{ min: 0, max: 64, increment: 8 }], hashAlgs: config.defaultHashAlgs ?? ["SHA2-256"] }];
    }
    if (mode === "sigGen") registration.deterministic = [true, false];
    return registration;
  });
}

function vectorIsSample(vector: NormalizedVectorSetView | null, session: AcvpSessionDetail | null, fallback: boolean): boolean {
  return typeof vector?.prompt.isSample === "boolean" ? vector.prompt.isSample : typeof session?.isSample === "boolean" ? session.isSample : fallback;
}

function validateCampaignSeed(value: string): string | null {
  if (!value) return null;
  if (!/^[0-9a-fA-F]+$/.test(value) || value.length % 2 !== 0 || value.length < 32 || value.length > 128) return "Campaign seed must be 32-128 hexadecimal characters.";
  return null;
}

function toggleValue<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}
