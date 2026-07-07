import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { ApiError, apiClient } from '../api/client';
import type { ErrorDto, ProblemDto, SolveJobDto, SolveResultDto } from '../api/dtos';
import { createEditableProblem, toSolveRequest, type EditableProblem } from '../domain/problemState';

type Notice = {
  title: string;
  message: string;
  details?: string;
  tone?: 'error' | 'info';
};

export function App() {
  const [problem, setProblem] = useState<ProblemDto | null>(null);
  const [editable, setEditable] = useState<EditableProblem | null>(null);
  const [job, setJob] = useState<SolveJobDto | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loading, setLoading] = useState(false);
  const pollCancelRef = useRef(false);
  const pollAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void loadProblem();
    return () => {
      pollCancelRef.current = true;
      pollAbortRef.current?.abort();
    };
  }, []);

  async function loadProblem() {
    setLoading(true);
    setNotice(null);
    try {
      const loaded = await apiClient.getDefaultProblem();
      setProblem(loaded);
      setEditable(createEditableProblem(loaded));
      setJob(null);
    } catch (error) {
      setNotice(toNotice(error, 'Could not load default problem'));
    } finally {
      setLoading(false);
    }
  }

  async function startSolve() {
    if (!editable) return;
    pollCancelRef.current = false;
    pollAbortRef.current?.abort();
    setLoading(true);
    setNotice({
      title: 'Solver queued',
      message: 'Submitting the edited problem.',
      tone: 'info',
    });
    try {
      const queued = await apiClient.startSolve(toSolveRequest(editable));
      setJob({ ...queued, result: null, error: null });
      await pollJob(queued.job_id);
    } catch (error) {
      if (!isAbortError(error) && !pollCancelRef.current) {
        setNotice(toNotice(error, 'Could not start solver'));
      }
    } finally {
      if (!pollCancelRef.current) setLoading(false);
    }
  }

  async function pollJob(jobId: string) {
    while (!pollCancelRef.current) {
      const controller = new AbortController();
      pollAbortRef.current = controller;
      const current = await apiClient.getSolveJob(jobId, { signal: controller.signal });
      if (pollCancelRef.current || controller.signal.aborted) return;
      setJob(current);
      if (current.status === 'succeeded') {
        setNotice({
          title: 'Solve complete',
          message: 'The latest result is shown below.',
          tone: 'info',
        });
        return;
      }
      if (current.status === 'failed') {
        setNotice(errorDtoToNotice(current.error, 'Solver failed'));
        return;
      }
      await delay(1200);
      if (pollCancelRef.current || controller.signal.aborted) return;
    }
  }

  function updateDemand(itemId: string, value: string) {
    setEditable((current) =>
      current
        ? {
            ...current,
            demands: { ...current.demands, [itemId]: value },
          }
        : current,
    );
  }

  function updateExternalInput(
    itemId: string,
    patch: Partial<{ enabled: boolean; cost: string; capacity: string }>,
  ) {
    setEditable((current) =>
      current
        ? {
            ...current,
            externalInputs: current.externalInputs.map((input) =>
              input.item_id === itemId ? { ...input, ...patch } : input,
            ),
          }
        : current,
    );
  }

  const itemNames = new Set(problem?.items.map((item) => item.id) ?? []);

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Factory Plan Optimizer</p>
          <h1>Minimal solver dashboard</h1>
          <p>
            Edit demand and external supply assumptions, submit a solve job, and
            inspect the returned summary.
          </p>
        </div>
        <button type="button" onClick={() => void loadProblem()} disabled={loading}>
          Reload default
        </button>
      </header>

      {notice && <NoticeBox notice={notice} />}

      <section className="grid two">
        <Panel title="Demands" subtitle="Target output amounts by item.">
          {editable ? (
            Object.entries(editable.demands).map(([itemId, amount]) => (
              <label className="row" key={itemId}>
                <span>{itemId}</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={amount}
                  onChange={(event) => updateDemand(itemId, event.target.value)}
                />
              </label>
            ))
          ) : (
            <p>Loading problem…</p>
          )}
        </Panel>

        <Panel
          title="External inputs"
          subtitle="Allow raw purchases/sources, with cost and optional capacity."
        >
          {editable ? (
            editable.externalInputs.map((input) => (
              <div className="input-card" key={input.item_id}>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={input.enabled}
                    onChange={(event) =>
                      updateExternalInput(input.item_id, { enabled: event.target.checked })
                    }
                  />{' '}
                  {input.item_id}
                </label>
                {!itemNames.has(input.item_id) && <small>Not listed in item table</small>}
                <label>
                  Cost
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={input.cost}
                    onChange={(event) =>
                      updateExternalInput(input.item_id, {
                        cost: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Capacity
                  <input
                    type="number"
                    min="0"
                    step="any"
                    placeholder="unlimited"
                    value={input.capacity}
                    onChange={(event) =>
                      updateExternalInput(input.item_id, {
                        capacity: event.target.value,
                      })
                    }
                  />
                </label>
              </div>
            ))
          ) : (
            <p>Loading inputs…</p>
          )}
        </Panel>
      </section>

      <section className="actions">
        <button
          type="button"
          className="primary"
          disabled={!editable || loading}
          onClick={() => void startSolve()}
        >
          Start solver
        </button>
        {job && (
          <span>
            Job {job.job_id}: <strong>{job.status}</strong>
          </span>
        )}
      </section>

      <section className="grid two">
        <Panel title="Problem summary">
          <p>
            {problem?.items.length ?? 0} items · {problem?.recipe_ids.length ?? 0} recipes
          </p>
        </Panel>
        <Panel title="Solution summary">
          {job?.result ? <ResultView result={job.result} /> : <p>No result yet.</p>}
        </Panel>
      </section>
    </main>
  );
}

function ResultView({ result }: { result: SolveResultDto }) {
  return (
    <div className="result">
      <p>
        Status: <strong>{result.solver_status}</strong>
      </p>
      <p>
        Objective: <strong>{result.objective_value ?? 'n/a'}</strong>
      </p>
      {result.message && <p>{result.message}</p>}
      <KeyValueTable title="Objective components" values={result.objective_components} />
      <KeyValueTable title="Recipe rates" values={result.recipe_rates} />
      <KeyValueTable title="External supplies" values={result.external_supplies} />
      <KeyValueTable title="Unmet demand" values={result.unmet_demand} />
      <KeyValueTable title="Surplus" values={result.surplus} />
      <KeyValueTable title="Residuals" values={result.balance_residuals} />
      {result.details && (
        <details>
          <summary>Debug details</summary>
          <pre>{result.details}</pre>
        </details>
      )}
    </div>
  );
}

function KeyValueTable({ title, values }: { title: string; values: Record<string, number> }) {
  const rows = Object.entries(values);
  return (
    <section className="kv">
      <h3>{title}</h3>
      {rows.length ? (
        <table>
          <tbody>
            {rows.map(([key, value]) => (
              <tr key={key}>
                <th>{key}</th>
                <td>{formatNumber(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">None</p>
      )}
    </section>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {subtitle && <p className="muted">{subtitle}</p>}
      {children}
    </section>
  );
}

function NoticeBox({ notice }: { notice: Notice }) {
  return (
    <aside className={`notice ${notice.tone ?? 'error'}`}>
      <strong>{notice.title}</strong>
      <p>{notice.message}</p>
      {notice.details && (
        <details>
          <summary>Technical details</summary>
          <pre>{notice.details}</pre>
        </details>
      )}
    </aside>
  );
}

function toNotice(error: unknown, fallback: string): Notice {
  if (error instanceof ApiError) {
    const title = apiErrorTitle(error.status, fallback);
    return {
      title,
      message: error.message,
      details: JSON.stringify(error.body, null, 2),
    };
  }
  return {
    title: fallback,
    message: error instanceof Error ? error.message : 'Unknown error',
  };
}

function apiErrorTitle(status: number, fallback: string): string {
  if (status === 422) return 'Validation error';
  if (status === 429) return 'Solver busy';
  if (status === 404) return 'Job not found';
  return fallback;
}

function errorDtoToNotice(error: ErrorDto | null | undefined, fallback: string): Notice {
  return {
    title: fallback,
    message: error?.message ?? 'The solver returned a failed status.',
    details: error?.details,
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toPrecision(8);
}
