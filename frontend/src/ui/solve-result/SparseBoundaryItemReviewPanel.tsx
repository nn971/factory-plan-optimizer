import { useMemo, useState } from 'react';

import type {
  SparseBoundaryPortTypeDto,
  SparseClusterSummaryDto,
  SparseClusteringResultDto,
  SparseExternalBoundaryPortTypeDto,
} from '../../api/dtos';
import { formatNumber } from '../../domain/clusterDiagnostics';
import { clusterLabel } from '../../domain/sparseClustering';

export function SparseBoundaryItemReviewPanel({ result }: { result: SparseClusteringResultDto | null | undefined }) {
  const clusters = useMemo(() => sortedSparseClusters(result), [result]);
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);

  if (!result || result.status !== 'success' || !result.cluster_summaries) return null;

  if (clusters.length === 0) {
    return (
      <section className="cluster-diagnostics-panel" aria-labelledby="sparse-boundary-review-title">
        <p className="eyebrow">Sparse cluster review</p>
        <h3 id="sparse-boundary-review-title">Net port review</h3>
        <p className="muted">Sparse clustering completed, but there are no cluster summaries to review.</p>
      </section>
    );
  }

  const selectedCluster = clusters.find((cluster) => clusterId(cluster) === selectedClusterId) ?? clusters[0];
  const objective = result.port_aware_objective;

  return (
    <section className="cluster-diagnostics-panel" aria-labelledby="sparse-boundary-review-title">
      <div className="cluster-diagnostics-hero">
        <div>
          <p className="eyebrow">Sparse cluster review</p>
          <h3 id="sparse-boundary-review-title">Net port review</h3>
          <p className="muted">
            These rows come directly from sparse clustering. Net ports are signed item balances for each cluster, not routed train paths.
          </p>
        </div>
        {objective && (
          <div className="cluster-total-cards">
            <MetricCard label="Net ports" value={objective.net_port_count} note="objective count" accent />
            <MetricCard label="Port cost" value={objective.port_cost} note="primary term" />
            <MetricCard label="Size penalty" value={objective.size_penalty} note="cluster balance" />
            <MetricCard label="Flow cost" value={objective.flow_cost} note="absolute net" />
            <MetricCard label="Refinement passes" value={objective.refinement_passes} note="completed" />
          </div>
        )}
      </div>

      <div className="cluster-diagnostics-stats">
        <span><strong>{clusters.length}</strong> clusters</span>
        <span><strong>{formatNumber(sum(clusters, (cluster) => cluster.recipe_count))}</strong> recipes</span>
        <span><strong>{formatNumber(result.net_port_count ?? result.boundary_port_type_count ?? 0)}</strong> net ports</span>
        <span><strong>{formatNumber(result.boundary_port_types?.total_count ?? 0)}</strong> net port rows</span>
      </div>

      <div className="cluster-diagnostics-layout">
        <div className="cluster-overview-card">
          <div className="cluster-section-heading">
            <div>
              <h4>All sparse clusters</h4>
              <p className="muted">Sorted by net ports first, then recipe count.</p>
            </div>
          </div>
          <div className="cluster-table-wrap">
            <table className="cluster-table cluster-overview-table">
              <thead>
                <tr>
                  <th>Cluster</th>
                  <th>Recipes</th>
                  <th>Net in</th>
                  <th>Net out</th>
                  <th>Net ports</th>
                </tr>
              </thead>
              <tbody>
                {clusters.map((cluster) => {
                  const id = clusterId(cluster);
                  return (
                    <tr key={id} className={id === clusterId(selectedCluster) ? 'selected' : ''}>
                      <th scope="row">
                        <button
                          type="button"
                          className="cluster-link-button"
                          aria-pressed={id === clusterId(selectedCluster)}
                          onClick={() => setSelectedClusterId(id)}
                        >
                          <span>{clusterLabel(cluster.cluster_id)}</span>
                          <small>{id}</small>
                        </button>
                      </th>
                      <td>{formatNumber(cluster.recipe_count)}</td>
                      <td>{formatOptionalNumber(cluster.net_input_port_count)}</td>
                      <td>{formatOptionalNumber(cluster.net_output_port_count)}</td>
                      <td>{formatOptionalNumber(cluster.net_port_count)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <SparseClusterDetail cluster={selectedCluster} sparse={result} />
      </div>
    </section>
  );
}

function SparseClusterDetail({ cluster, sparse }: { cluster: SparseClusterSummaryDto; sparse: SparseClusteringResultDto }) {
  const id = clusterId(cluster);
  const netPorts = sortedNetPorts(sparse.boundary_port_types?.items ?? [], id);
  const externalRows = sortedExternalRows(sparse.external_boundary_port_types?.items ?? [], id);

  return (
    <article className="cluster-detail-card">
      <div className="cluster-section-heading">
        <div>
          <p className="eyebrow">Selected sparse cluster</p>
          <h4>{clusterLabel(cluster.cluster_id)}</h4>
          <p className="muted">
            {formatNumber(cluster.recipe_count)} recipes · {formatOptionalNumber(cluster.net_port_count)} net ports
          </p>
        </div>
        <div className="cluster-cost-stack">
          <span><strong>{formatOptionalNumber(cluster.net_input_port_count)}</strong> net input ports</span>
          <span><strong>{formatOptionalNumber(cluster.net_output_port_count)}</strong> net output ports</span>
          <span><strong>{formatOptionalNumber(cluster.net_port_count)}</strong> net ports</span>
        </div>
      </div>

      <div className="cluster-recipe-list">
        {cluster.recipe_ids.map((recipeId) => <code key={recipeId}>{recipeId}</code>)}
      </div>

      <div className="cluster-table-wrap">
        <table className="cluster-table boundary-table">
          <thead>
            <tr>
              <th>Net port item</th>
              <th>Direction</th>
              <th>Net amount</th>
            </tr>
          </thead>
          <tbody>
            {netPorts.length === 0 ? (
              <tr><td colSpan={3}>No net port rows for this cluster.</td></tr>
            ) : netPorts.map((row) => (
              <tr key={`${id}:${row.item_id}:${row.direction}`}>
                <th scope="row"><code>{row.item_id}</code></th>
                <td><span className={`direction-pill ${row.direction}`}>{row.direction}</span></td>
                <td>{formatSignedAmount(row.net_amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="cluster-cost-note">
        <h5>External source/demand diagnostics</h5>
        <p className="muted">Diagnostics only. These rows are not objective net ports and are not exact routed flow.</p>
        <div className="cluster-table-wrap">
          <table className="cluster-table boundary-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Direction</th>
                <th>Source/demand amount</th>
              </tr>
            </thead>
            <tbody>
              {externalRows.length === 0 ? (
                <tr><td colSpan={3}>No external diagnostics for this cluster.</td></tr>
              ) : externalRows.map((row) => (
                <tr key={`${id}:${row.item_id}:${row.direction}`}>
                  <th scope="row"><code>{row.item_id}</code></th>
                  <td>{row.direction}</td>
                  <td>{formatNumber(row.source_or_demand_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </article>
  );
}

function sortedSparseClusters(result: SparseClusteringResultDto | null | undefined): SparseClusterSummaryDto[] {
  if (!result || result.status !== 'success') return [];
  return [...(result.cluster_summaries?.items ?? [])].sort(
    (left, right) =>
      (right.net_port_count ?? 0) - (left.net_port_count ?? 0) ||
      right.recipe_count - left.recipe_count ||
      clusterId(left).localeCompare(clusterId(right)),
  );
}

function sortedNetPorts(rows: SparseBoundaryPortTypeDto[], selectedClusterId: string): SparseBoundaryPortTypeDto[] {
  return rows
    .filter((row) => String(row.cluster_id) === selectedClusterId)
    .sort((left, right) =>
      left.direction.localeCompare(right.direction) ||
      Math.abs(right.net_amount ?? 0) - Math.abs(left.net_amount ?? 0) ||
      left.item_id.localeCompare(right.item_id),
    );
}

function sortedExternalRows(rows: SparseExternalBoundaryPortTypeDto[], selectedClusterId: string): SparseExternalBoundaryPortTypeDto[] {
  return rows
    .filter((row) => String(row.cluster_id) === selectedClusterId)
    .sort((left, right) =>
      left.direction.localeCompare(right.direction) ||
      Math.abs(right.source_or_demand_amount) - Math.abs(left.source_or_demand_amount) ||
      left.item_id.localeCompare(right.item_id),
    );
}

function clusterId(cluster: Pick<SparseClusterSummaryDto, 'cluster_id'>): string {
  return String(cluster.cluster_id);
}

function formatOptionalNumber(value: number | null | undefined): string {
  return value == null ? 'n/a' : formatNumber(value);
}

function formatSignedAmount(value: number | null | undefined): string {
  if (value == null) return 'n/a';
  return `${value > 0 ? '+' : ''}${formatNumber(value)}`;
}

function sum<T>(items: T[], value: (item: T) => number): number {
  return items.reduce((total, item) => total + value(item), 0);
}

function MetricCard({ label, value, note, accent = false }: { label: string; value: number; note: string; accent?: boolean }) {
  return (
    <article className={accent ? 'metric-card accent' : 'metric-card'}>
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
      <small>{note}</small>
    </article>
  );
}
