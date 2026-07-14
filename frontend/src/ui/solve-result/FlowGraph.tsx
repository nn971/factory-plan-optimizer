import { useEffect, useMemo, useState } from 'react';
import type { KeyboardEvent } from 'react';

import type { SolveResultDto } from '../../api/dtos';
import {
  buildDisplayFlowGraph,
  buildFlowSelectionDetailIndex,
  buildOptimizerOverlay,
  type ActiveFlowGraph,
  type DisplayFlowEdge,
  type DisplayFlowNode,
  type FlowGraphMode,
} from '../../domain/solveResultFlow';
import { NodeDetails } from './NodeDetails';

const MIN_GRAPH_WIDTH = 560;
const HORIZONTAL_PAD = 64;
const TOP_PAD = 64;
const BOTTOM_PAD = 78;
const NODE_RADIUS = 15;

type PositionedNode = DisplayFlowNode & { x: number; y: number; column: number };

type FlowGraphLayout = {
  nodes: PositionedNode[];
  width: number;
  height: number;
};

export function FlowGraph({ graph, result, initialMode = 'raw' }: { graph: ActiveFlowGraph; result: SolveResultDto; initialMode?: FlowGraphMode }) {
  const [graphMode, setGraphMode] = useState<FlowGraphMode>(initialMode);
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(() => new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const displayMode = graphMode === 'heuristic' ? 'heuristic' : 'raw';
  const displayGraph = useMemo(
    () => buildDisplayFlowGraph(graph, expandedClusters, displayMode),
    [graph, expandedClusters, displayMode],
  );
  const overlay = graphMode === 'optimizer-overlay' ? buildOptimizerOverlay(graph, result) : null;
  const selectedNodeIsVisible = selectedId ? displayGraph.nodes.some((node) => node.id === selectedId) : true;
  const effectiveSelectedId = selectedNodeIsVisible ? selectedId : null;
  const detailIndex = useMemo(
    () => buildFlowSelectionDetailIndex(graph, result, displayGraph.clusters),
    [graph, result, displayGraph.clusters],
  );
  const selectedDetails = effectiveSelectedId ? detailIndex.detailById.get(effectiveSelectedId) ?? null : null;
  const layout = layoutFlowGraphNodes(displayGraph.nodes);
  const positionedNodes = layout.nodes;
  const nodeById = new Map(positionedNodes.map((node) => [node.id, node]));
  const prominentDiagnostics = graph.diagnostics.filter(
    (diagnostic) => diagnostic.kind === 'unmet' || diagnostic.kind === 'surplus',
  );

  useEffect(() => {
    if (!selectedNodeIsVisible) setSelectedId(null);
  }, [selectedNodeIsVisible]);

  return (
    <section className="flow-graph-panel" aria-labelledby="flow-graph-title">
      <div className="flow-graph-heading">
        <div>
          <p className="eyebrow">Active flow graph</p>
          <h3 id="flow-graph-title">Solved item and recipe flow</h3>
          <p className="muted">
            First-pass graph from active recipe rates. Node labels are shortened for readability; raw tables below keep exact IDs and values.
          </p>
        </div>
        <div className="flow-graph-counts">
          <span><strong>{graph.nodes.length}</strong> nodes</span>
          <span><strong>{graph.edges.length}</strong> edges</span>
          {displayGraph.clusters.length > 0 && graphMode === 'heuristic' && <span><strong>{displayGraph.clusters.length}</strong> groups</span>}
          <span><strong>{graph.warnings.length}</strong> warnings</span>
        </div>
      </div>

      <fieldset className="flow-mode-controls">
        <legend>Graph mode</legend>
        {GRAPH_MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            className={graphMode === mode.id ? 'active' : ''}
            onClick={() => {
              setGraphMode(mode.id);
              setExpandedClusters(new Set());
            }}
            aria-pressed={graphMode === mode.id}
          >
            <strong>{mode.label}</strong>
            <span>{mode.hint}</span>
          </button>
        ))}
      </fieldset>

      {graphMode === 'optimizer-overlay' && overlay && (
        overlay.available ? (
          <div className="flow-overlay-note success">
            <strong>Overlay source</strong>
            <span>{overlay.label}. Complete active recipe mapping.</span>
          </div>
        ) : (
          <output className="flow-overlay-note warning">
            <strong>Overlay unavailable</strong>
            <span>{overlay.reason} Showing raw graph.</span>
          </output>
        )
      )}

      {prominentDiagnostics.length > 0 && (
        <div className="flow-diagnostic-spotlight">
          {prominentDiagnostics.map((diagnostic) => (
            <article key={diagnostic.id} className={`flow-diagnostic-card ${diagnostic.kind}`}>
              <span>{diagnostic.kind === 'unmet' ? 'Unmet demand' : 'Surplus'}</span>
              <strong>{formatNumber(diagnostic.quantity ?? 0)}</strong>
              <code>{diagnostic.itemId}</code>
            </article>
          ))}
        </div>
      )}

      {graph.warnings.length > 0 && (
        <div className="flow-warning-list">
          <strong>Graph diagnostics to review</strong>
          <ul>
            {graph.warnings.map((warning, index) => (
              <li key={`${warning.kind}:${warning.recipeId ?? ''}:${warning.itemId ?? ''}:${warning.field ?? ''}:${index}`}>
                {warning.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {graphMode === 'heuristic' && displayGraph.clusters.length > 0 && (
        <div className="flow-cluster-controls">
          <strong>Heuristic groups</strong>
          <div>
            {displayGraph.clusters.map((cluster) => {
              const expanded = expandedClusters.has(cluster.id);
              return (
                <button
                  key={cluster.id}
                  type="button"
                  className={expanded ? 'expanded' : ''}
                  onClick={() => setExpandedClusters((current) => toggleSet(current, cluster.id))}
                >
                  {expanded ? 'Collapse' : 'Expand'} {cluster.label} · {cluster.nodeCount} nodes
                  {cluster.unmetDemandCount > 0 && ` · unmet ${formatNumber(cluster.unmetDemandQuantity)}`}
                  {cluster.surplusCount > 0 && ` · surplus ${formatNumber(cluster.surplusQuantity)}`}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {graph.nodes.length === 0 ? (
        <p className="muted">No active positive flows or positive diagnostics were found in this result.</p>
      ) : (
        <div className="flow-graph-with-details">
        <div className="flow-graph-canvas">
          <div className="flow-graph-legend">
            <span className="legend-swatch external" /> External supply
            <span className="legend-swatch recipe" /> Recipe
            <span className="legend-swatch item" /> Item
            <span className="legend-swatch unmet" /> Unmet demand
            <span className="legend-swatch surplus" /> Surplus
          </div>
          <svg viewBox={`0 0 ${layout.width} ${layout.height}`} className="flow-graph-svg" role="img">
            <title>Node-link view of active recipe, item, and diagnostic flows</title>
            <g className="flow-edges">
              {displayGraph.edges.map((edge) => {
                const source = nodeById.get(edge.source);
                const target = nodeById.get(edge.target);
                if (!source || !target) return null;
                return <FlowGraphEdge key={edge.id} edge={edge} source={source} target={target} />;
              })}
            </g>
            <g className="flow-nodes">
              {positionedNodes.map((node) => (
                <FlowGraphNode
                  key={node.id}
                  node={node}
                  selected={selectedId === node.id}
                  onSelect={setSelectedId}
                  overlayClusterId={overlay?.available && node.kind === 'recipe' && node.recipeId ? overlay.recipeToCluster.get(node.recipeId) : undefined}
                />
              ))}
            </g>
          </svg>
        </div>
        <NodeDetails details={selectedDetails} />
        </div>
      )}
    </section>
  );
}

const GRAPH_MODES: Array<{ id: FlowGraphMode; label: string; hint: string }> = [
  { id: 'raw', label: 'Raw LP flow', hint: 'Ungrouped' },
  { id: 'heuristic', label: 'Heuristic grouping', hint: 'Collapse dense areas' },
  { id: 'optimizer-overlay', label: 'Optimizer overlay', hint: 'Show clusters' },
];

function FlowGraphEdge({ edge, source, target }: { edge: DisplayFlowEdge; source: PositionedNode; target: PositionedNode }) {
  const direction = target.x >= source.x ? 1 : -1;
  const control = Math.max(70, Math.abs(target.x - source.x) * 0.48);
  const path = `M ${source.x} ${source.y} C ${source.x + control * direction} ${source.y}, ${target.x - control * direction} ${target.y}, ${target.x} ${target.y}`;
  const labelX = (source.x + target.x) / 2;
  const labelY = (source.y + target.y) / 2 - 7;
  return (
    <g className={`flow-edge ${edge.kind} ${edge.collapsed ? 'collapsed' : ''}`}>
      <path d={path} pathLength={1} />
      <text x={labelX} y={labelY} textAnchor="middle">
        {formatNumber(edge.quantity)}
      </text>
    </g>
  );
}

function FlowGraphNode({ node, selected, onSelect, overlayClusterId }: { node: PositionedNode; selected: boolean; onSelect: (id: string) => void; overlayClusterId?: string }) {
  if (node.kind === 'cluster') {
    return (
      <g className={`flow-node cluster ${selected ? 'selected' : ''}`} transform={`translate(${node.x} ${node.y})`} onClick={() => onSelect(node.id)} onKeyDown={(event) => selectFromKeyboard(event, node.id, onSelect)} role="button" tabIndex={0}>
        <circle r={NODE_RADIUS + 11} />
        <text className="node-label" x={0} y={-34} textAnchor="middle">{node.label}</text>
        <text className="node-quantity" x={0} y={5} textAnchor="middle">{node.cluster.nodeCount} nodes</text>
        {(node.cluster.unmetDemandCount > 0 || node.cluster.surplusCount > 0) && (
          <text className="node-badge" x={0} y={45} textAnchor="middle">
            {node.cluster.unmetDemandCount > 0 ? `unmet ${formatNumber(node.cluster.unmetDemandQuantity)}` : ''}
            {node.cluster.unmetDemandCount > 0 && node.cluster.surplusCount > 0 ? ' · ' : ''}
            {node.cluster.surplusCount > 0 ? `surplus ${formatNumber(node.cluster.surplusQuantity)}` : ''}
          </text>
        )}
      </g>
    );
  }
  return (
    <g className={`flow-node ${node.kind} ${node.diagnosticKind ?? ''} ${overlayClusterId ? `optimizer-overlay cluster-accent-${clusterAccent(overlayClusterId)}` : ''} ${selected ? 'selected' : ''}`} transform={`translate(${node.x} ${node.y})`} onClick={() => onSelect(node.id)} onKeyDown={(event) => selectFromKeyboard(event, node.id, onSelect)} role="button" tabIndex={0}>
      <circle r={NODE_RADIUS} />
      <text className="node-label" x={0} y={-24} textAnchor="middle">
        {shortLabel(node.label)}
      </text>
      {node.quantity !== undefined && (
        <text className="node-quantity" x={0} y={35} textAnchor="middle">
          {formatNumber(node.quantity)}
        </text>
      )}
      {overlayClusterId && (
        <text className="node-overlay-badge" x={0} y={node.quantity !== undefined ? 52 : 35} textAnchor="middle">
          C {shortClusterLabel(overlayClusterId)}
        </text>
      )}
    </g>
  );
}

function clusterAccent(clusterId: string) {
  let hash = 0;
  for (const char of clusterId) hash = (hash + char.charCodeAt(0)) % 6;
  return hash + 1;
}

function shortClusterLabel(clusterId: string) {
  return clusterId.length > 10 ? `${clusterId.slice(0, 9)}…` : clusterId;
}

export function layoutFlowGraphNodes(nodes: DisplayFlowNode[]): FlowGraphLayout {
  const columns = compactColumns([
    nodes.filter((node) => node.kind === 'diagnostic' && node.diagnosticKind === 'external'),
    nodes.filter((node) => node.kind === 'item'),
    nodes.filter((node) => node.kind === 'recipe' || node.kind === 'cluster'),
    nodes.filter((node) => node.kind === 'diagnostic' && node.diagnosticKind !== 'external'),
  ]);
  const maxRows = Math.max(1, ...columns.map((column) => column.length));
  const hasClusterNode = nodes.some((node) => node.kind === 'cluster');
  const totalNodes = nodes.length;
  const columnGap = adaptiveColumnGap(totalNodes);
  const rowGap = adaptiveRowGap(maxRows, hasClusterNode);
  const width = Math.max(MIN_GRAPH_WIDTH, HORIZONTAL_PAD * 2 + Math.max(0, columns.length - 1) * columnGap);
  const availableWidth = Math.max(0, width - HORIZONTAL_PAD * 2);
  const positionedNodes = columns.flatMap((columnNodes, columnIndex) => {
    const x = columns.length === 1 ? width / 2 : HORIZONTAL_PAD + (availableWidth * columnIndex) / (columns.length - 1);
    return columnNodes.map((node, rowIndex) => ({
      ...node,
      x,
      y: TOP_PAD + rowIndex * rowGap,
      column: columnIndex,
    }));
  });

  return {
    nodes: positionedNodes,
    width,
    height: TOP_PAD + (maxRows - 1) * rowGap + BOTTOM_PAD,
  };
}

function compactColumns(columns: DisplayFlowNode[][]) {
  return columns.filter((column) => column.length > 0);
}

function adaptiveColumnGap(totalNodes: number) {
  if (totalNodes > 48) return 230;
  if (totalNodes > 24) return 210;
  if (totalNodes > 12) return 188;
  return 168;
}

function adaptiveRowGap(maxRows: number, hasClusterNode: boolean) {
  const base = maxRows > 22 ? 42 : maxRows > 14 ? 48 : maxRows > 7 ? 56 : 66;
  return hasClusterNode ? Math.max(base, 72) : base;
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toPrecision(6);
}

function shortLabel(label: string) {
  return label.length > 34 ? `${label.slice(0, 31)}…` : label;
}

function toggleSet(current: Set<string>, id: string) {
  const next = new Set(current);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

function selectFromKeyboard(event: KeyboardEvent<SVGGElement>, id: string, onSelect: (id: string) => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  event.preventDefault();
  onSelect(id);
}
