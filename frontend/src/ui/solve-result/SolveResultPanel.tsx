import type { ExplorerResponseDto, SolveJobDto } from '../../api/dtos';
import {
  describeJobStatus,
  describeSolverStatus,
  graphAvailability,
  type StatusSummary,
} from '../../domain/solveOutcome';
import { buildActiveFlowGraph } from '../../domain/solveResultFlow';
import { ClusterDiagnosticsPanel } from './ClusterDiagnosticsPanel';
import { FlowGraph } from './FlowGraph';
import { RawResultTables } from './RawResultTables';

export function SolveResultPanel({
  job,
  explorer,
  explorerLoading,
  explorerStale,
  onLoadExplorer,
  currentPackageId,
}: {
  job: SolveJobDto | null;
  explorer: ExplorerResponseDto | null;
  explorerLoading: boolean;
  explorerStale: boolean;
  onLoadExplorer: () => void;
  currentPackageId?: string | null;
}) {
  if (!job) return <p>No result yet.</p>;

  const jobStatus = describeJobStatus(job.status);
  const solverStatus = describeSolverStatus(job.result);
  const graphStatus = graphAvailability({ job, explorer, explorerLoading, explorerStale, currentPackageId });
  const canLoadRecipeData = Boolean(job.result && !explorerLoading && graphStatus.tone !== 'success');
  const recipeDataActionLabel = graphStatus.tone === 'warning' ? 'Refresh recipe data' : 'Load recipe data';
  const graph = graphStatus.tone === 'success' && job.result && explorer
    ? buildActiveFlowGraph(job.result, explorer)
    : null;

  return (
    <div className="result">
      <div className="solve-outcome-strip">
        <StatusLine label="Job lifecycle" summary={jobStatus} detail={`Job ${job.job_id}`} />
        <StatusLine label="Solver outcome" summary={solverStatus} />
      </div>
      {job.status === 'failed' && (
        <div className="notice error">
          <strong>{job.error?.message ?? 'Solver failed'}</strong>
          {job.error?.details && <pre>{job.error.details}</pre>}
        </div>
      )}
      {job.status !== 'succeeded' && <p className="muted">Waiting for a completed solver result.</p>}
      {job.result && (
        <>
          {solverStatus.tone !== 'success' && (
            <section className={`notice ${noticeClassForTone(solverStatus.tone)}`}>
              <strong>Solver outcome needs review</strong>
              <p>{solverStatus.description}</p>
            </section>
          )}
          <p className="objective-line">
            Objective value <strong>{job.result.objective_value ?? 'n/a'}</strong>
          </p>
          {job.result.message && <p>{job.result.message}</p>}
          <section className={`notice ${noticeClassForTone(graphStatus.tone)}`}>
            <strong>{graphStatus.label}</strong>
            <p>{graphStatus.description}</p>
            {graph && solverStatus.tone !== 'success' && (
              <p>Treat graph quantities as diagnostic output, not an accepted plan.</p>
            )}
            {canLoadRecipeData && (
              <button type="button" onClick={onLoadExplorer}>{recipeDataActionLabel}</button>
            )}
          </section>
          <ClusterDiagnosticsPanel result={job.result} />
          {graph && <FlowGraph key={job.job_id} graph={graph} result={job.result} />}
          <RawResultTables result={job.result} />
        </>
      )}
    </div>
  );
}

function StatusLine({
  label,
  summary,
  detail,
}: {
  label: string;
  summary: StatusSummary;
  detail?: string;
}) {
  return (
    <article className={`status-card ${summary.tone}`} title={summary.description}>
      <span>{label}</span>
      <strong>{summary.label}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}

function noticeClassForTone(tone: StatusSummary['tone']) {
  if (tone === 'error') return 'error';
  if (tone === 'warning') return 'warning';
  if (tone === 'success') return 'success';
  return 'info';
}
