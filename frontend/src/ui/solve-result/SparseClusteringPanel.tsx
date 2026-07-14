import type { ReactNode } from 'react';
import type { SparseCappedArrayDto, SparseClusteringResultDto } from '../../api/dtos';
import { formatNumber } from '../../domain/clusterDiagnostics';
import {
  cappedArraySummary,
  clusterLabel,
  componentLabel,
  describeSparseClusteringStatus,
  displayId,
  formatSparseValue,
  skippedHubEdgeCount,
  sparseWarnings,
} from '../../domain/sparseClustering';

export function SparseClusteringPanel({ result }: { result: SparseClusteringResultDto | null | undefined }) {
  if (result == null) {
    return (
      <section className="sparse-clustering-panel quiet" aria-labelledby="sparse-clustering-result-title">
        <p className="eyebrow">Sparse clustering</p>
        <h3 id="sparse-clustering-result-title">Not requested</h3>
        <p className="muted">Run sparse clustering to see a summary-first recipe graph partition for large plans.</p>
      </section>
    );
  }

  const status = describeSparseClusteringStatus(result.status);
  const warnings = sparseWarnings(result);
  const canShowDetails = result.status === 'success';

  return (
    <section className="sparse-clustering-panel" aria-labelledby="sparse-clustering-result-title">
      <div className="cluster-diagnostics-hero">
        <div>
          <p className="eyebrow">Sparse clustering</p>
          <h3 id="sparse-clustering-result-title">Recipe graph overview</h3>
          <p className="muted">
            Sparse post-process explanation for the solved recipe graph. It is not optimizer allocation and does not change recipe rates.
          </p>
          <div className="scenario-meta sparse-meta">
            <span>{result.mode} mode</span>
            <span>{result.engine ?? 'no engine'}</span>
            <span>{result.graph_type}</span>
          </div>
        </div>
        <div className="cluster-total-cards">
          <MetricCard label="Status" value={status.label} note={result.message || status.description} tone={status.tone} />
          <MetricCard label="Clusters" value={formatMaybeCount(result.cluster_count)} note={targetClusterNote(result)} />
          <MetricCard label="Net ports" value={formatMaybeCount(netPortCount(result))} note="signed item nets by cluster" />
          <MetricCard label="Refinement passes" value={formatMaybeCount(result.port_aware_objective?.refinement_passes)} note="accepted search passes" />
          <MetricCard label="External diagnostics" value={formatMaybeCount(result.external_boundary_port_type_count)} note="source/demand rows" />
          <MetricCard label="Skipped hub edges" value={formatNumber(skippedHubEdgeCount(result))} note="summarized by item" tone={skippedHubEdgeCount(result) > 0 ? 'warning' : undefined} />
        </div>
      </div>

      <section className={`notice ${noticeClassForTone(status.tone)}`}>
        <strong>{status.label}</strong>
        <p>{result.message || status.description}</p>
      </section>

      {warnings.length > 0 && (
        <section className="notice warning">
          <strong>Notes and capped details</strong>
          <ul className="sparse-warning-list">
            {warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </section>
      )}

      {!canShowDetails && (
        <p className="muted">No sparse cluster detail tables are available for this status. The main solve result is still shown below.</p>
      )}

      {canShowDetails && (
        <details className="cluster-cost-note sparse-details" open>
          <summary>Cluster details</summary>
          <div className="sparse-result-grid">
            <CompactMap title="Port-aware objective" values={result.port_aware_objective ?? {}} />
            <CompactMap title="Graph statistics" values={result.graph_statistics ?? {}} />
          </div>
          <div className="sparse-result-grid wide">
            <ClusterSummaryTable capped={result.cluster_summaries} />
            <HubSummaryTable capped={result.hub_summaries} />
          </div>
          <div className="sparse-result-grid wide">
            <BoundaryPortTable capped={result.boundary_port_types} />
            <ExternalBoundaryPortTable capped={result.external_boundary_port_types} />
          </div>
          <p className="muted">Source-target cluster allocation is not reported. Cluster net ports are authoritative for sparse overview visualization.</p>
          <div className="sparse-result-grid wide">
            <SurplusUnmetTable capped={result.surplus_unmet_summary} />
          </div>
        </details>
      )}
    </section>
  );
}

function CompactMap({ title, values }: { title: string; values: Record<string, unknown> }) {
  const entries = Object.entries(values);
  return (
    <section className="cluster-overview-card">
      <h4>{title}</h4>
      {entries.length === 0 ? <p className="muted">No {title.toLowerCase()} to show.</p> : (
        <dl className="compact-cost-list">
          {entries.map(([name, value]) => (
            <div key={name}>
              <dt>{componentLabel(name)}</dt>
              <dd>{formatSparseValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function ClusterSummaryTable({ capped }: { capped: SparseClusteringResultDto['cluster_summaries'] }) {
  return (
    <CappedTable title="Cluster summaries" capped={capped} empty="No cluster summaries to show." headers={['Cluster', 'Recipes', 'Net in', 'Net out', 'Net ports', 'Examples']}>
      {capped?.items.map((row) => (
        <tr key={String(row.cluster_id)}>
          <th scope="row"><code>{clusterLabel(row.cluster_id)}</code></th>
          <td>{formatNumber(row.recipe_count)}</td>
          <td>{formatOptionalNumber(row.net_input_port_count)}</td>
          <td>{formatOptionalNumber(row.net_output_port_count)}</td>
          <td>{formatOptionalNumber(row.net_port_count)}</td>
          <td>{row.recipe_ids.slice(0, 4).map((id) => <code key={id}>{id} </code>)}{row.recipe_ids.length > 4 ? '…' : ''}</td>
        </tr>
      )) ?? []}
    </CappedTable>
  );
}

function BoundaryPortTable({ capped }: { capped: SparseClusteringResultDto['boundary_port_types'] }) {
  return (
    <CappedTable title="Net port types" capped={capped} empty="No net ports to show." headers={['Item', 'Cluster', 'Direction', 'Net amount']}>
      {capped?.items.map((row) => (
        <tr key={`${row.cluster_id}:${row.item_id}:${row.direction}`}>
          <th scope="row"><code>{displayId(row.item_id)}</code></th>
          <td><code>{clusterLabel(row.cluster_id)}</code></td>
          <td>{row.direction}</td>
          <td>{formatNetAmount(row.net_amount, row.direction)}</td>
        </tr>
      )) ?? []}
    </CappedTable>
  );
}

function ExternalBoundaryPortTable({ capped }: { capped: SparseClusteringResultDto['external_boundary_port_types'] }) {
  return (
    <CappedTable title="External source/demand diagnostics" capped={capped} empty="No external source/demand rows to show." headers={['Item', 'Cluster', 'Direction', 'Source/demand amount']}>
      <tr className="table-note-row"><td colSpan={4}>External rows are diagnostics only. Source/demand amount is not a net-port objective amount or exact routed cluster flow.</td></tr>
      {capped?.items.map((row) => (
        <tr key={`${row.cluster_id}:${row.item_id}:${row.direction}`}>
          <th scope="row"><code>{displayId(row.item_id)}</code></th>
          <td><code>{clusterLabel(row.cluster_id)}</code></td>
          <td>{row.direction}</td>
          <td>{formatNumber(row.source_or_demand_amount)}</td>
        </tr>
      )) ?? []}
    </CappedTable>
  );
}

function HubSummaryTable({ capped }: { capped: SparseClusteringResultDto['hub_summaries'] }) {
  return (
    <CappedTable title="Hub summaries" capped={capped} empty="No hub summaries to show." headers={['Item', 'Kept', 'Skipped', 'Skipped estimate']}>
      {capped?.items.map((row) => (
        <tr key={row.item_id}>
          <th scope="row"><code>{displayId(row.item_id)}</code></th>
          <td>{formatNumber(row.kept_count)}</td>
          <td>{formatNumber(row.skipped_count)}</td>
          <td>{formatNumber(row.skipped_estimated_flow)}</td>
        </tr>
      )) ?? []}
    </CappedTable>
  );
}

function SurplusUnmetTable({ capped }: { capped: SparseClusteringResultDto['surplus_unmet_summary'] }) {
  return (
    <CappedTable title="Surplus and unmet demand" capped={capped} empty="No surplus or unmet demand rows to show." headers={['Item', 'Surplus', 'Unmet demand']}>
      {capped?.items.map((row) => (
        <tr key={row.item_id}>
          <th scope="row"><code>{displayId(row.item_id)}</code></th>
          <td>{formatNumber(row.surplus)}</td>
          <td>{formatNumber(row.unmet_demand)}</td>
        </tr>
      )) ?? []}
    </CappedTable>
  );
}

function CappedTable<T extends Record<string, unknown>>({
  title,
  capped,
  empty,
  headers,
  children,
}: {
  title: string;
  capped: SparseCappedArrayDto<T> | null | undefined;
  empty: string;
  headers: string[];
  children: ReactNode;
}) {
  const childrenArray = Array.isArray(children) ? children : [children];
  const hasRows = childrenArray.length > 0;
  return (
    <section className="cluster-overview-card">
      <h4>{title}</h4>
      <p className="muted">{cappedArraySummary(capped, title.toLowerCase())}</p>
      {!hasRows ? <p className="muted">{empty}</p> : (
        <div className="cluster-table-wrap">
          <table className="cluster-table">
            <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
            <tbody>{children}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function MetricCard({ label, value, note, tone }: { label: string; value: string; note: string; tone?: string }) {
  return (
    <article className={`metric-card ${tone ?? ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function formatMaybeCount(value: number | null | undefined): string {
  return value == null ? 'n/a' : formatNumber(value);
}

function formatOptionalNumber(value: number | null | undefined): string {
  return value == null ? 'n/a' : formatNumber(value);
}

function netPortCount(result: SparseClusteringResultDto): number | null | undefined {
  return result.net_port_count ?? result.port_aware_objective?.net_port_count ?? result.boundary_port_type_count;
}

function formatNetAmount(value: number | null | undefined, direction: string): string {
  if (value == null) return 'n/a';
  const prefix = value > 0 ? '+' : '';
  const directionHint = direction === 'input' ? 'input' : direction === 'output' ? 'output' : direction;
  return `${prefix}${formatNumber(value)} ${directionHint}`;
}

function targetClusterNote(result: SparseClusteringResultDto): string {
  return result.target_cluster_count == null ? 'automatic target' : `target ${formatNumber(result.target_cluster_count)}`;
}

function noticeClassForTone(tone: 'success' | 'warning' | 'error' | 'info') {
  if (tone === 'error') return 'error';
  if (tone === 'warning') return 'warning';
  if (tone === 'success') return 'success';
  return 'info';
}
