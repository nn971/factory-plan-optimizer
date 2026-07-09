import { useMemo, useState } from 'react';

import type { ClusterDto, SolveResultDto } from '../../api/dtos';
import {
  diagnosticCost,
  formatNumber,
  sortedBoundaryItems,
  sortedDiagnosticClusters,
  summarizeClusterDiagnostics,
} from '../../domain/clusterDiagnostics';

export function ClusterDiagnosticsPanel({ result }: { result: SolveResultDto }) {
  const summary = summarizeClusterDiagnostics(result);
  const clusters = useMemo(() => (summary ? sortedDiagnosticClusters(summary.diagnostics) : []), [summary]);
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);

  if (!summary) return null;

  const selectedCluster = clusters.find((cluster) => cluster.id === selectedClusterId) ?? clusters[0] ?? null;
  const defaults = summary.diagnostics.cost_defaults;

  return (
    <section className="cluster-diagnostics-panel" aria-labelledby="cluster-diagnostics-title">
      <div className="cluster-diagnostics-hero">
        <div>
          <p className="eyebrow">Solver cluster diagnostics</p>
          <h3 id="cluster-diagnostics-title">Boundary item review</h3>
          <p className="muted">
            These clusters come from the solver after the plan is solved. Costs here are diagnostic only; the optimized objective above is unchanged.
          </p>
          <p className="muted">
            Boundary costs are approximate diagnostics inferred from each cluster&apos;s net item flows. They are not exact routing or transport decisions.
          </p>
        </div>
        <div className="cluster-total-cards">
          <MetricCard label="Optimized objective" value={summary.diagnostics.base_objective_value} note="actual solve" />
          <MetricCard label="Diagnostic costs" value={summary.diagnostics.diagnostic_total} note="not optimized" accent />
          <MetricCard label="Combined view" value={summary.diagnostics.combined_diagnostic_objective_value} note="objective + diagnostics" />
        </div>
      </div>

      <div className="cluster-diagnostics-stats">
        <span><strong>{summary.clusterCount}</strong> clusters</span>
        <span><strong>{summary.activeRecipeCount}</strong> active recipes</span>
        <span><strong>{summary.boundaryItemRowCount}</strong> boundary rows</span>
        <span><strong>{summary.zeroNetRowCount}</strong> zero-net rows</span>
      </div>

      {summary.clusterCount === 0 ? (
        <div className="cluster-empty-state">
          <strong>Diagnostics ran, but no active clusters were found.</strong>
          <p className="muted">This is different from a missing diagnostics payload. There simply were no active recipe groups to show.</p>
        </div>
      ) : (
        <div className="cluster-diagnostics-layout">
          <div className="cluster-overview-card">
            <div className="cluster-section-heading">
              <div>
                <h4>All clusters</h4>
                <p className="muted">Sorted by diagnostic cost so the noisiest boundaries are first. Totals may also include size penalties beyond flow and port costs.</p>
              </div>
            </div>
            <div className="cluster-table-wrap">
              <table className="cluster-table cluster-overview-table">
                <thead>
                  <tr>
                    <th>Cluster</th>
                    <th>Recipes</th>
                    <th>Boundary types</th>
                    <th>Diagnostic cost</th>
                    <th>Flow</th>
                    <th>Port</th>
                  </tr>
                </thead>
                <tbody>
                  {clusters.map((cluster) => (
                    <tr key={cluster.id} className={cluster.id === selectedCluster?.id ? 'selected' : ''}>
                      <th scope="row">
                        <button
                          type="button"
                          className="cluster-link-button"
                          aria-pressed={cluster.id === selectedCluster?.id}
                          onClick={() => setSelectedClusterId(cluster.id)}
                        >
                          <span>{cluster.label}</span>
                          <small>{cluster.category}</small>
                        </button>
                      </th>
                      <td>{cluster.active_recipe_count}</td>
                      <td>{cluster.boundary_item_type_count}</td>
                      <td>{formatNumber(diagnosticCost(cluster))}</td>
                      <td>{formatNumber(cluster.diagnostic_components.flow_cost ?? 0)}</td>
                      <td>{formatNumber(cluster.diagnostic_components.port_cost ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {selectedCluster && <ClusterDetail cluster={selectedCluster} />}
        </div>
      )}

      <details className="cluster-cost-note">
        <summary>Diagnostic cost settings</summary>
        <dl>
          <CostSetting label="Flow cost per quantity" value={defaults.flow_cost_per_quantity} />
          <CostSetting label="Port cost per boundary type" value={defaults.port_cost_per_boundary_type} />
          <CostSetting label="Recipe size penalty" value={defaults.recipe_size_penalty} />
          <CostSetting label="Boundary type size penalty" value={defaults.boundary_type_size_penalty} />
          <CostSetting label="Target active recipes" value={defaults.target_active_recipes.join('–')} />
          <CostSetting label="Target boundary item types" value={defaults.target_boundary_item_types.join('–')} />
        </dl>
      </details>
    </section>
  );
}

function ClusterDetail({ cluster }: { cluster: ClusterDto }) {
  const boundaryItems = sortedBoundaryItems(cluster);
  return (
    <article className="cluster-detail-card">
      <div className="cluster-section-heading">
        <div>
          <p className="eyebrow">Selected cluster</p>
          <h4>{cluster.label}</h4>
          <p className="muted">
            {cluster.active_recipe_count} active recipes · {cluster.boundary_item_type_count} boundary item types
          </p>
        </div>
        <div className="cluster-cost-stack">
          {Object.entries(cluster.diagnostic_components).map(([name, value]) => (
            <span key={name}><strong>{formatNumber(value)}</strong> {componentLabel(name)}</span>
          ))}
        </div>
      </div>
      <div className="cluster-recipe-list">
        {cluster.recipe_ids.map((recipeId) => <code key={recipeId}>{recipeId}</code>)}
      </div>
      <div className="cluster-table-wrap">
        <table className="cluster-table boundary-table">
          <thead>
            <tr>
              <th>Boundary item</th>
              <th>Direction</th>
              <th>Net quantity</th>
              <th>Flow cost</th>
              <th>Port cost</th>
              <th>Net</th>
            </tr>
          </thead>
          <tbody>
            {boundaryItems.map((item) => (
              <tr key={`${cluster.id}:${item.item_id}:${item.direction}`} className={item.is_zero_net ? 'zero-net' : ''}>
                <th scope="row"><code>{item.item_id}</code></th>
                <td><span className={`direction-pill ${item.direction}`}>{item.direction}</span></td>
                <td>{formatNumber(item.quantity)}</td>
                <td>{formatNumber(item.flow_cost)}</td>
                <td>{formatNumber(item.port_cost)}</td>
                <td>{item.is_zero_net ? 'zero-net' : 'nonzero'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
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

function CostSetting({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{typeof value === 'number' ? formatNumber(value) : value}</dd>
    </div>
  );
}

function componentLabel(name: string) {
  return name.replace(/_/g, ' ');
}
