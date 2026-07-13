import type { OptimizedClusteringResultDto } from '../../api/dtos';
import type { ReactNode } from 'react';
import { formatNumber } from '../../domain/clusterDiagnostics';
import {
  componentLabel,
  describeOptimizedClusteringStatus,
  externalBoundaryLabel,
  formatMaybeNumber,
  hasOptimizedClusterCostAlias,
} from '../../domain/optimizedClustering';

export function OptimizedClusteringPanel({ result }: { result: OptimizedClusteringResultDto | null | undefined }) {
  if (result == null) {
    return (
      <section className="optimized-clustering-panel quiet" aria-labelledby="optimized-clustering-result-title">
        <p className="eyebrow">Optimized clustering</p>
        <h3 id="optimized-clustering-result-title">Not requested</h3>
        <p className="muted">This solve only includes the normal plan and deterministic cluster diagnostics.</p>
      </section>
    );
  }

  const status = describeOptimizedClusteringStatus(result.status);
  const visibleClusters = result.clusters.filter((cluster) => cluster.used || cluster.size > 0);
  const provisional = result.effective_parameters.preset_is_provisional === true;

  return (
    <section className="optimized-clustering-panel" aria-labelledby="optimized-clustering-result-title">
      <div className="cluster-diagnostics-hero">
        <div>
          <p className="eyebrow">Optimized clustering</p>
          <h3 id="optimized-clustering-result-title">Second-pass cluster allocation</h3>
          <p className="muted">
            This is separate from deterministic diagnostics. It fixes the solved recipe totals, then tries to allocate recipes into clusters with flow, port, and size costs.
          </p>
          {provisional && <p className="source-pill warning">Preset is provisional</p>}
        </div>
        <div className="cluster-total-cards">
          <MetricCard label="Status" value={status.label} note={status.description} tone={status.tone} />
          <MetricCard label="Objective" value={formatMaybeNumber(result.objective_value)} note="optimized clustering only" />
          <MetricCard label="Clusters" value={String(visibleClusters.length)} note="used clusters" />
        </div>
      </div>

      <section className={`notice ${noticeClassForTone(status.tone)}`}>
        <strong>{status.label}</strong>
        <p>{result.message || status.description}</p>
      </section>

      {hasOptimizedClusterCostAlias(result) && (
        <section className="notice warning">
          <strong>Unexpected cost field</strong>
          <p>Optimized clustering should report cluster_size_penalty, not cluster_cost.</p>
        </section>
      )}

      <div className="optimized-result-grid">
        <CompactMap title="Objective components" values={result.objective_components} />
        <CompactMap title="Cost breakdown" values={result.cost_breakdown} />
      </div>

      <details className="cluster-cost-note">
        <summary>Effective parameters</summary>
        <dl>
          {Object.entries(result.effective_parameters).map(([name, value]) => (
            <div key={name}>
              <dt>{componentLabel(name)}</dt>
              <dd>{formatParameterValue(value)}</dd>
            </div>
          ))}
        </dl>
      </details>

      <div className="optimized-result-grid wide">
        <OptimizedClustersTable clusters={visibleClusters} />
        <AllocationsTable allocations={result.allocations} />
      </div>
      <div className="optimized-result-grid wide">
        <FlowsTable flows={result.flows} />
        <ExternalFlowsTable rows={result.external_flows} />
      </div>
    </section>
  );
}

function CompactMap({ title, values }: { title: string; values: Record<string, number> }) {
  return (
    <section className="cluster-overview-card">
      <h4>{title}</h4>
      <dl className="compact-cost-list">
        {Object.entries(values).map(([name, value]) => (
          <div key={name}>
            <dt>{componentLabel(name)}</dt>
            <dd>{formatNumber(value)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function OptimizedClustersTable({ clusters }: { clusters: OptimizedClusteringResultDto['clusters'] }) {
  return (
    <CompactTable title="Clusters" empty="No used clusters to show." headers={['Cluster', 'Size', 'Under min', 'Over max']}>
      {clusters.map((cluster) => (
        <tr key={cluster.cluster_id}>
          <th scope="row"><code>{cluster.cluster_id}</code></th>
          <td>{formatNumber(cluster.size)}</td>
          <td>{formatNumber(cluster.under_min)}</td>
          <td>{formatNumber(cluster.over_max)}</td>
        </tr>
      ))}
    </CompactTable>
  );
}

function AllocationsTable({ allocations }: { allocations: OptimizedClusteringResultDto['allocations'] }) {
  return (
    <CompactTable title="Allocations and splits" empty="No allocation rows to show." headers={['Recipe', 'Cluster', 'Rate', 'Fraction']}>
      {allocations.map((row) => (
        <tr key={`${row.recipe_id}:${row.cluster_id}`}>
          <th scope="row"><code>{row.recipe_id}</code></th>
          <td><code>{row.cluster_id}</code></td>
          <td>{formatNumber(row.rate)}</td>
          <td>{formatNumber(row.fraction)}</td>
        </tr>
      ))}
    </CompactTable>
  );
}

function FlowsTable({ flows }: { flows: OptimizedClusteringResultDto['flows'] }) {
  return (
    <CompactTable title="Inter-cluster flows" empty="No inter-cluster flow rows to show." headers={['Item', 'From', 'To', 'Quantity']}>
      {flows.map((row) => (
        <tr key={`${row.from_cluster_id}:${row.to_cluster_id}:${row.item_id}`}>
          <th scope="row"><code>{row.item_id}</code></th>
          <td><code>{row.from_cluster_id}</code></td>
          <td><code>{row.to_cluster_id}</code></td>
          <td>{formatNumber(row.quantity)}</td>
        </tr>
      ))}
    </CompactTable>
  );
}

function ExternalFlowsTable({ rows }: { rows: OptimizedClusteringResultDto['external_flows'] }) {
  return (
    <CompactTable title="External rows" empty="No external rows to show." headers={['Item', 'Cluster', 'Direction', 'Boundary', 'Quantity']}>
      <tr className="table-note-row">
        <td colSpan={5}>External rows are aggregate balance rows, not exact raw-supply or final-demand routes.</td>
      </tr>
      {rows.map((row) => (
        <tr key={`${row.cluster_id}:${row.item_id}:${row.direction}:${row.quantity}`}>
          <th scope="row"><code>{row.item_id}</code></th>
          <td><code>{row.cluster_id}</code></td>
          <td>{row.direction}</td>
          <td>{externalBoundaryLabel(row)}</td>
          <td>{formatNumber(row.quantity)}</td>
        </tr>
      ))}
    </CompactTable>
  );
}

function CompactTable({ title, empty, headers, children }: { title: string; empty: string; headers: string[]; children: ReactNode }) {
  const rows = Array.isArray(children) ? children : [children];
  return (
    <section className="cluster-overview-card">
      <h4>{title}</h4>
      {rows.length === 0 ? <p className="muted">{empty}</p> : (
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

function formatParameterValue(value: boolean | number | string | string[]): string {
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'none';
  if (typeof value === 'number') return formatNumber(value);
  return String(value);
}

function noticeClassForTone(tone: 'success' | 'warning' | 'error' | 'info') {
  if (tone === 'error') return 'error';
  if (tone === 'warning') return 'warning';
  if (tone === 'success') return 'success';
  return 'info';
}
