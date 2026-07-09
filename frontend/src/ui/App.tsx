import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { ApiError, apiClient } from '../api/client';
import type { ErrorDto, ExplorerResponseDto, ProblemDto, SolveJobDto } from '../api/dtos';
import {
  selectionExists,
  type ExplorerSelection,
} from '../domain/explorerState';
import { ExplorerPanel } from './ExplorerPanel';
import { SolveResultPanel } from './solve-result/SolveResultPanel';
import {
  createEditableProblem,
  displayRateToItemsPerSecond,
  findApprovedInputsMissingCapacity,
  hasPositiveDemand,
  problemLocalStorageKey,
  toSolveRequest,
  type DisplayRateUnits,
  type EditableProblem,
} from '../domain/problemState';

type Notice = {
  title: string;
  message: string;
  details?: string;
  tone?: 'error' | 'info';
};

type AppTab = 'solver' | 'explorer';

type SavedEditableProblem = Pick<EditableProblem, 'solveMode' | 'displayRateUnits' | 'demands' | 'externalInputs'> & {
  version: 1;
};

export function App() {
  const [problem, setProblem] = useState<ProblemDto | null>(null);
  const [editable, setEditable] = useState<EditableProblem | null>(null);
  const [job, setJob] = useState<SolveJobDto | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<AppTab>('solver');
  const [explorer, setExplorer] = useState<ExplorerResponseDto | null>(null);
  const [explorerLoading, setExplorerLoading] = useState(false);
  const [explorerStale, setExplorerStale] = useState(true);
  const [explorerAutoLoadBlocked, setExplorerAutoLoadBlocked] = useState(false);
  const [explorerSelection, setExplorerSelection] = useState<ExplorerSelection>(null);
  const [demandSearch, setDemandSearch] = useState('');
  const [inputSearch, setInputSearch] = useState('');
  const [showDisabledInputs, setShowDisabledInputs] = useState(false);
  const [storageKey, setStorageKey] = useState<string | null>(null);
  const [selectedMilestone, setSelectedMilestone] = useState<string>('');
  const pollCancelRef = useRef(false);
  const pollAbortRef = useRef<AbortController | null>(null);
  const explorerRequestTokenRef = useRef(0);

  useEffect(() => {
    void loadProblem();
    return () => {
      pollCancelRef.current = true;
      pollAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (activeTab === 'explorer' && (!explorer || explorerStale) && !explorerLoading && !explorerAutoLoadBlocked) {
      void loadExplorer();
    }
  }, [activeTab, explorer, explorerAutoLoadBlocked, explorerLoading, explorerStale]);

  useEffect(() => {
    if (!editable || !storageKey) return;
    const payload: SavedEditableProblem = { version: 1, ...editable };
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch {
      // Ignore quota/private-mode failures so editing remains usable.
    }
  }, [editable, storageKey]);

  useEffect(() => {
    if (!selectedMilestone || !explorer) return;
    setExplorerSelection((current) => {
      if (current?.type === 'item' && current.id === selectedMilestone) return current;
      return explorer.items.some((item) => item.id === selectedMilestone)
        ? { type: 'item', id: selectedMilestone }
        : current;
    });
  }, [explorer, selectedMilestone]);

  async function loadProblem() {
    pollCancelRef.current = true;
    pollAbortRef.current?.abort();
    setLoading(true);
    setNotice(null);
    try {
      const loaded = await apiClient.getDefaultProblem();
      setProblem(loaded);
      setEditable(createEditableProblemFromStorage(loaded));
      setSelectedMilestone(defaultMilestoneId(loaded));
      setStorageKey(problemLocalStorageKey(loaded));
      setJob(null);
      afterProblemDataChanged();
    } catch (error) {
      setNotice(toNotice(error, 'Could not load default problem'));
    } finally {
      setLoading(false);
    }
  }

  async function uploadPackage(file: File | null) {
    if (!file) return;
    pollCancelRef.current = true;
    pollAbortRef.current?.abort();
    setLoading(true);
    setNotice(null);
    try {
      const payload = JSON.parse(await file.text()) as unknown;
      const uploaded = await apiClient.uploadPackage(payload);
      const loaded = { ...uploaded.problem, package_id: uploaded.package_id };
      setProblem(loaded);
      setEditable(createEditableProblemFromStorage(loaded));
      setSelectedMilestone(defaultMilestoneId(loaded));
      setStorageKey(problemLocalStorageKey(loaded));
      setJob(null);
      afterProblemDataChanged();
      setNotice({
        title: 'Package loaded',
        message: `${file.name} is now the active problem data.`,
        tone: 'info',
      });
    } catch (error) {
      setNotice(toNotice(error, 'Could not load package'));
    } finally {
      setLoading(false);
    }
  }

  async function startSolve() {
    if (!editable) return;
    const validationNotice = validateEditableProblem(editable);
    if (validationNotice) {
      setNotice(validationNotice);
      return;
    }
    pollCancelRef.current = false;
    pollAbortRef.current?.abort();
    setLoading(true);
    setNotice({
      title: 'Solver queued',
      message: 'Submitting the edited problem.',
      tone: 'info',
    });
    try {
      const queued = await apiClient.startSolve(toSolveRequest(editable, problem?.package_id, selectedMilestone));
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

  async function loadExplorer() {
    const requestToken = explorerRequestTokenRef.current + 1;
    explorerRequestTokenRef.current = requestToken;
    setExplorerAutoLoadBlocked(false);
    setExplorerLoading(true);
    try {
      const loaded = await apiClient.getExplorer();
      if (explorerRequestTokenRef.current !== requestToken) return;
      setExplorer(loaded);
      setExplorerStale(false);
      setExplorerSelection((current) => (selectionExists(current, loaded) ? current : null));
    } catch (error) {
      if (explorerRequestTokenRef.current !== requestToken) return;
      setExplorerAutoLoadBlocked(true);
      setNotice(toNotice(error, 'Could not load explorer'));
    } finally {
      if (explorerRequestTokenRef.current === requestToken) {
        setExplorerLoading(false);
      }
    }
  }

  function afterProblemDataChanged() {
    explorerRequestTokenRef.current += 1;
    setExplorerLoading(false);
    setExplorerAutoLoadBlocked(false);
    setExplorerStale(true);
    if (activeTab === 'explorer') {
      void loadExplorer();
    }
  }

  function switchTab(tab: AppTab) {
    setActiveTab(tab);
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

  function updateDisplayRateUnits(nextUnits: DisplayRateUnits) {
    setEditable((current) => {
      if (!current || current.displayRateUnits === nextUnits) return current;
      return {
        ...current,
        displayRateUnits: nextUnits,
        demands: Object.fromEntries(
          Object.entries(current.demands).map(([itemId, value]) => {
            const parsed = Number(value);
            if (value.trim() === '' || !Number.isFinite(parsed) || parsed < 0) return [itemId, value];
            const perSecond = displayRateToItemsPerSecond(parsed, current.displayRateUnits);
            return [itemId, formatEditableRate(fromItemsPerSecond(perSecond, nextUnits))];
          }),
        ),
      };
    });
  }

  function updateSolveMode(solveMode: EditableProblem['solveMode']) {
    setEditable((current) => (current ? { ...current, solveMode } : current));
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
  const scenarioTitle = problem?.scenario_label ?? 'Scenario';
  const scenarioId = problem?.scenario_id ?? 'default-scenario';
  const milestoneOptions = scienceMilestoneOptions(problem);
  const targetDemandIdSet = new Set(problem?.target_demands ?? []);
  const milestoneOrder = new Map(milestoneOptions.map((itemId, index) => [itemId, index]));
  const visibleDemands = Object.entries(editable?.demands ?? {})
    .filter(([itemId, amount]) => {
      const matchesSearch = itemId.toLowerCase().includes(demandSearch.toLowerCase());
      const isTarget = targetDemandIdSet.has(itemId);
      return matchesSearch && (isTarget || Number(amount) > 0);
    })
    .sort(([left], [right]) => {
      const leftOrder = milestoneOrder.get(left) ?? Number.MAX_SAFE_INTEGER;
      const rightOrder = milestoneOrder.get(right) ?? Number.MAX_SAFE_INTEGER;
      return leftOrder - rightOrder || left.localeCompare(right);
    });
  const visibleExternalInputs = (editable?.externalInputs ?? []).filter((input) => {
    const matchesSearch = input.item_id.toLowerCase().includes(inputSearch.toLowerCase());
    return matchesSearch && (showDisabledInputs || input.enabled);
  });

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Factory Plan Optimizer</p>
          <h1>{scenarioTitle}</h1>
          <p>
            Set target science rates, review the raw inputs the backend found, then run a
            solve. Blank or zero target rates are not sent.
          </p>
          <div className="scenario-meta">
            <span>{scenarioId}</span>
            <span>{problem?.package_id ?? 'default package'}</span>
          </div>
        </div>
        <div className="hero-actions">
          <label className="file-picker">
            Upload .factory-data.json
            <input
              type="file"
              accept=".json,.factory-data.json,application/json"
              disabled={loading}
              onChange={(event) => void uploadPackage(event.target.files?.[0] ?? null)}
            />
          </label>
          <button type="button" onClick={() => void loadProblem()} disabled={loading}>
            Reload default
          </button>
        </div>
      </header>

      {notice && <NoticeBox notice={notice} />}

      <nav className="tabs" aria-label="Primary sections">
        <button
          type="button"
          className={activeTab === 'solver' ? 'active' : ''}
          onClick={() => switchTab('solver')}
        >
          Solver
        </button>
        <button
          type="button"
          className={activeTab === 'explorer' ? 'active' : ''}
          onClick={() => switchTab('explorer')}
        >
          Explorer
        </button>
      </nav>

      <MilestonePanel
        selectedMilestone={selectedMilestone}
        milestones={milestoneOptions}
        onSelect={setSelectedMilestone}
      />

      {activeTab === 'solver' ? (
        <>
          <section className="grid two">
            <Panel title="Target science rates" subtitle="Only positive target rates are sent to the solver.">
              {editable ? (
                <>
                  <div className="control-strip">
                    <input
                      type="search"
                      placeholder="Search target packs"
                      value={demandSearch}
                      onChange={(event) => setDemandSearch(event.target.value)}
                    />
                    <label>
                      Units
                      <select
                        value={editable.displayRateUnits}
                        onChange={(event) => updateDisplayRateUnits(event.target.value as DisplayRateUnits)}
                      >
                        <option value="items_per_second">items/s</option>
                        <option value="items_per_minute">items/min</option>
                      </select>
                    </label>
                  </div>
                  {visibleDemands.map(([itemId, amount]) => (
                    <label className={`target-row ${itemId === selectedMilestone ? 'active' : ''}`} key={itemId}>
                      <span>
                        <strong>
                          {friendlyItemName(itemId)}
                          {itemId === selectedMilestone && <em className="selected-milestone-label">Selected milestone</em>}
                        </strong>
                        <small>{itemId}</small>
                      </span>
                      <input
                        type="number"
                        min="0"
                        step="any"
                        placeholder="0"
                        value={amount}
                        onChange={(event) => updateDemand(itemId, event.target.value)}
                      />
                    </label>
                  ))}
                  {!visibleDemands.length && <p className="muted">No matching demands.</p>}
                </>
              ) : (
                <p>Loading problem…</p>
              )}
            </Panel>

            <Panel
              title="Raw input review"
              subtitle="Backend-computed candidates. Approve what may enter from outside the factory."
            >
              {editable ? (
                <>
                  <div className="filters">
                    <input
                      type="search"
                      placeholder="Search external inputs"
                      value={inputSearch}
                      onChange={(event) => setInputSearch(event.target.value)}
                    />
                    <label className="check inline">
                      <input
                        type="checkbox"
                        checked={showDisabledInputs}
                        onChange={(event) => setShowDisabledInputs(event.target.checked)}
                      />{' '}
                      Show disabled
                    </label>
                  </div>
                  {visibleExternalInputs.map((input) => (
                    <div className="input-card" key={input.item_id}>
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={input.enabled}
                          onChange={(event) =>
                            updateExternalInput(input.item_id, { enabled: event.target.checked })
                          }
                        />{' '}
                        {friendlyItemName(input.item_id)}
                      </label>
                      <span className="source-pill">{input.kind ?? 'unknown'}</span>
                      <span className="source-pill">{sourceLabel(input.source)}</span>
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
                          placeholder="required cap"
                          value={input.capacity}
                          onChange={(event) =>
                            updateExternalInput(input.item_id, {
                              capacity: event.target.value,
                            })
                          }
                        />
                      </label>
                    </div>
                  ))}
                  {!visibleExternalInputs.length && <p className="muted">No matching inputs.</p>}
                </>
              ) : (
                <p>Loading inputs…</p>
              )}
            </Panel>
          </section>

          <section className="actions">
            <fieldset className="solve-mode">
              <legend>Solve mode</legend>
              <label className="check inline">
                <input
                  type="radio"
                  name="solve-mode"
                  checked={editable?.solveMode === 'hard_demand'}
                  onChange={() => updateSolveMode('hard_demand')}
                  disabled={!editable || loading}
                />
                Hard demand
              </label>
              <label className="check inline">
                <input
                  type="radio"
                  name="solve-mode"
                  checked={editable?.solveMode === 'soft_diagnostics'}
                  onChange={() => updateSolveMode('soft_diagnostics')}
                  disabled={!editable || loading}
                />
                Soft diagnostics
              </label>
              <p className="muted">
                Hard mode must meet the requested rates. Soft diagnostics can show unmet demand when a plan cannot fit.
              </p>
            </fieldset>
            <button
              type="button"
              className="primary"
              disabled={!editable || loading}
              onClick={() => void startSolve()}
            >
              Solve scenario
            </button>
            {job && (
              <span>
                Job {job.job_id}: <strong>{job.status}</strong>
              </span>
            )}
          </section>

          <section className="grid">
            <Panel title="Solution summary">
              <SolveResultPanel
                job={job}
                explorer={explorer}
                explorerLoading={explorerLoading}
                explorerStale={explorerStale}
                onLoadExplorer={() => void loadExplorer()}
                currentPackageId={problem?.package_id}
              />
            </Panel>
            <Panel title="Problem summary">
              <p>
                {problem?.items.length ?? 0} items · {problem?.recipe_ids.length ?? 0} recipes
                {problem?.package_id ? ` · package ${problem.package_id}` : ' · default package'}
              </p>
            </Panel>
          </section>

          <MetadataDetails problem={problem} />
        </>
      ) : (
        <ExplorerPanel
          explorer={explorer}
          loading={explorerLoading}
          stale={explorerStale}
          selection={explorerSelection}
          onSelect={setExplorerSelection}
          onRefresh={() => void loadExplorer()}
          milestoneItemId={selectedMilestone}
        />
      )}
    </main>
  );
}

function MilestonePanel({
  selectedMilestone,
  milestones,
  onSelect,
}: {
  selectedMilestone: string;
  milestones: string[];
  onSelect: (itemId: string) => void;
}) {
  return (
    <section className="panel milestone-panel" aria-label="Milestone selection">
      <div>
        <p className="eyebrow">Milestone</p>
        <h2>{selectedMilestone ? friendlyItemName(selectedMilestone) : 'No science milestone'}</h2>
        <p className="muted">
          The selected science pack is highlighted in Solver and opened in Explorer.
        </p>
      </div>
      <label>
        Science pack
        <select
          value={selectedMilestone}
          onChange={(event) => onSelect(event.target.value)}
          disabled={!milestones.length}
        >
          {milestones.length ? (
            milestones.map((itemId) => (
              <option value={itemId} key={itemId}>
                {friendlyItemName(itemId)}
              </option>
            ))
          ) : (
            <option value="">No science packs</option>
          )}
        </select>
      </label>
    </section>
  );
}

function MetadataDetails({ problem }: { problem: ProblemDto | null }) {
  const itemCount = Object.keys(problem?.item_metadata ?? {}).length;
  const recipeCount = Object.keys(problem?.recipe_metadata ?? {}).length;
  return (
    <section className="panel metadata-panel">
      <details>
        <summary>Readonly metadata</summary>
        <p className="muted">
          Item and recipe metadata is shown here when the package provides it. This scenario currently has {itemCount} item metadata entries and {recipeCount} recipe metadata entries.
        </p>
        {itemCount > 0 && <MetadataTable title="Item metadata" values={problem?.item_metadata ?? {}} />}
        {recipeCount > 0 && <MetadataTable title="Recipe metadata" values={problem?.recipe_metadata ?? {}} />}
      </details>
    </section>
  );
}

function MetadataTable({ title, values }: { title: string; values: Record<string, Record<string, string>> }) {
  return (
    <section className="kv">
      <h3>{title}</h3>
      <table>
        <tbody>
          {Object.entries(values).map(([id, metadata]) => (
            <tr key={id}>
              <th>{id}</th>
              <td>{Object.keys(metadata).length ? JSON.stringify(metadata) : 'No fields'}</td>
            </tr>
          ))}
        </tbody>
      </table>
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

function createEditableProblemFromStorage(problem: ProblemDto): EditableProblem {
  const base = createEditableProblem(problem);
  const saved = readSavedEditableProblem(problemLocalStorageKey(problem));
  if (!saved) return base;

  const savedInputs = new Map(saved.externalInputs.map((input) => [input.item_id, input]));
  return {
    ...base,
    solveMode: saved.solveMode,
    displayRateUnits: saved.displayRateUnits,
    demands: Object.fromEntries(
      Object.keys(base.demands).map((itemId) => [itemId, saved.demands[itemId] ?? base.demands[itemId]]),
    ),
    externalInputs: base.externalInputs.map((input) => {
      const savedInput = savedInputs.get(input.item_id);
      const savedCapacity = savedInput?.capacity;
      return {
        ...input,
        enabled: savedInput?.enabled ?? input.enabled,
        cost: savedInput?.cost ?? input.cost,
        capacity:
          savedCapacity != null && isValidRequiredNonnegativeNumber(savedCapacity)
            ? savedCapacity
            : input.capacity,
      };
    }),
  };
}

function readSavedEditableProblem(key: string): SavedEditableProblem | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!isRecord(parsed)) return null;
    if (
      parsed.version !== 1 ||
      (parsed.solveMode !== 'hard_demand' && parsed.solveMode !== 'soft_diagnostics') ||
      (parsed.displayRateUnits !== 'items_per_second' && parsed.displayRateUnits !== 'items_per_minute') ||
      !isRecord(parsed.demands) ||
      !Array.isArray(parsed.externalInputs)
    ) {
      return null;
    }
    const demands = sanitizeStringRecord(parsed.demands);
    const externalInputs = parsed.externalInputs.flatMap((input) => {
      if (!isRecord(input) || typeof input.item_id !== 'string') return [];
      return [{
        item_id: input.item_id,
        kind: sanitizeInputKind(input.kind),
        enabled: typeof input.enabled === 'boolean' ? input.enabled : false,
        cost: typeof input.cost === 'string' ? input.cost : '',
        capacity: typeof input.capacity === 'string' ? input.capacity : '',
        defaultApproved: typeof input.defaultApproved === 'boolean' ? input.defaultApproved : false,
      }];
    });
    return {
      version: 1,
      solveMode: parsed.solveMode,
      displayRateUnits: parsed.displayRateUnits,
      demands,
      externalInputs,
    };
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function sanitizeStringRecord(value: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, entry]) => {
      if (typeof key !== 'string' || typeof entry !== 'string') return [];
      return [[key, entry]];
    }),
  );
}

function sanitizeInputKind(value: unknown): 'item' | 'fluid' | 'unknown' {
  return value === 'item' || value === 'fluid' || value === 'unknown' ? value : 'unknown';
}

function scienceMilestoneOptions(problem: ProblemDto | null): string[] {
  if (!problem) return [];
  const scienceItemIds = new Set(problem.items.map((item) => item.id).filter(isSciencePackId));
  for (const milestone of problem.milestones) {
    if (isSciencePackId(milestone.item_id)) scienceItemIds.add(milestone.item_id);
  }
  const orderedTargets = problem.target_demands.filter((itemId) => scienceItemIds.has(itemId));
  const remainingScience = [...scienceItemIds].filter((itemId) => !orderedTargets.includes(itemId)).sort();
  return [...orderedTargets, ...remainingScience];
}

function defaultMilestoneId(problem: ProblemDto): string {
  const options = scienceMilestoneOptions(problem);
  return options.length ? options[options.length - 1] : '';
}

function isSciencePackId(itemId: string): boolean {
  return itemId.includes('science-pack');
}

function validateEditableProblem(editable: EditableProblem): Notice | null {
  const invalidDemandIds = invalidNumberEntries(editable.demands);
  if (invalidDemandIds.length > 0) {
    return {
      title: 'Check target rates',
      message: `Target rates must be zero or a positive number. Fix: ${invalidDemandIds.join(', ')}.`,
    };
  }
  if (!hasPositiveDemand(editable.demands)) {
    return {
      title: 'Add a target rate',
      message: 'Enter a positive rate for at least one science pack before solving.',
    };
  }

  const invalidCostIds = editable.externalInputs
    .filter((input) => input.enabled && !isValidOptionalNonnegativeNumber(input.cost))
    .map((input) => input.item_id)
    .sort();
  if (invalidCostIds.length > 0) {
    return {
      title: 'Check raw input costs',
      message: `Approved raw inputs need zero or positive costs. Fix: ${invalidCostIds.join(', ')}.`,
    };
  }

  const missingCapacityIds = findApprovedInputsMissingCapacity(editable.externalInputs);
  if (missingCapacityIds.length > 0) {
    return {
      title: 'Check raw input caps',
      message: `Approved raw inputs need a finite capacity before solving. Fix: ${missingCapacityIds.join(', ')}.`,
    };
  }
  return null;
}

function invalidNumberEntries(values: Record<string, string>): string[] {
  return Object.entries(values)
    .filter(([, value]) => value.trim() !== '' && !isValidOptionalNonnegativeNumber(value))
    .map(([itemId]) => itemId)
    .sort();
}

function isValidOptionalNonnegativeNumber(value: string): boolean {
  if (value.trim() === '') return true;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0;
}

function isValidRequiredNonnegativeNumber(value: string): boolean {
  if (value.trim() === '') return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0;
}

function fromItemsPerSecond(value: number, units: DisplayRateUnits): number {
  return units === 'items_per_minute' ? value * 60 : value;
}

function formatEditableRate(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(8)));
}

function friendlyItemName(itemId: string): string {
  return itemId
    .split('-')
    .map((part) => (part ? `${part[0].toUpperCase()}${part.slice(1)}` : part))
    .join(' ');
}

function sourceLabel(source: string | null | undefined): string {
  switch (source) {
    case 'package_external_supply':
      return 'package supply';
    case 'inferred_unproduced':
      return 'inferred raw';
    case 'inferred_fluid':
      return 'inferred fluid';
    default:
      return 'candidate';
  }
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
  if (status === 429) {
    return fallback === 'Could not load package' ? 'Package store full' : 'Solver busy';
  }
  if (status === 404) {
    return fallback === 'Could not start solver' ? 'Package not found' : 'Job not found';
  }
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
