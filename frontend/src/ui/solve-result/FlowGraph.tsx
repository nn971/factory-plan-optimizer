import { useEffect, useState } from 'react';
import type { KeyboardEvent } from 'react';

import type { SolveResultDto } from '../../api/dtos';
import {
  buildDisplayFlowGraph,
  buildFlowSelectionDetails,
  type ActiveFlowGraph,
  type DisplayFlowEdge,
  type DisplayFlowNode,
} from '../../domain/solveResultFlow';
import { NodeDetails } from './NodeDetails';

const GRAPH_WIDTH = 920;
const COLUMN_GAP = 210;
const LEFT_PAD = 74;
const TOP_PAD = 64;
const ROW_GAP = 58;
const NODE_RADIUS = 15;

type PositionedNode = DisplayFlowNode & { x: number; y: number; column: number };

export function FlowGraph({ graph, result }: { graph: ActiveFlowGraph; result: SolveResultDto }) {
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(() => new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const displayGraph = buildDisplayFlowGraph(graph, expandedClusters);
  const selectedNodeIsVisible = selectedId ? displayGraph.nodes.some((node) => node.id === selectedId) : true;
  const effectiveSelectedId = selectedNodeIsVisible ? selectedId : null;
  const selectedDetails = buildFlowSelectionDetails(graph, effectiveSelectedId, result);
  const positionedNodes = layoutNodes(displayGraph.nodes);
  const nodeById = new Map(positionedNodes.map((node) => [node.id, node]));
  const height = graphHeight(positionedNodes);
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
          {displayGraph.clusters.length > 0 && <span><strong>{displayGraph.clusters.length}</strong> clusters</span>}
          <span><strong>{graph.warnings.length}</strong> warnings</span>
        </div>
      </div>

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

      {displayGraph.clusters.length > 0 && (
        <div className="flow-cluster-controls">
          <strong>Dense graph grouping</strong>
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
          <svg viewBox={`0 0 ${GRAPH_WIDTH} ${height}`} className="flow-graph-svg" role="img">
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
                <FlowGraphNode key={node.id} node={node} selected={selectedId === node.id} onSelect={setSelectedId} />
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

function FlowGraphNode({ node, selected, onSelect }: { node: PositionedNode; selected: boolean; onSelect: (id: string) => void }) {
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
    <g className={`flow-node ${node.kind} ${node.diagnosticKind ?? ''} ${selected ? 'selected' : ''}`} transform={`translate(${node.x} ${node.y})`} onClick={() => onSelect(node.id)} onKeyDown={(event) => selectFromKeyboard(event, node.id, onSelect)} role="button" tabIndex={0}>
      <circle r={NODE_RADIUS} />
      <text className="node-label" x={0} y={-24} textAnchor="middle">
        {shortLabel(node.label)}
      </text>
      {node.quantity !== undefined && (
        <text className="node-quantity" x={0} y={35} textAnchor="middle">
          {formatNumber(node.quantity)}
        </text>
      )}
    </g>
  );
}

function layoutNodes(nodes: DisplayFlowNode[]): PositionedNode[] {
  const columns = [
    nodes.filter((node) => node.kind === 'diagnostic' && node.diagnosticKind === 'external'),
    nodes.filter((node) => node.kind === 'item'),
    nodes.filter((node) => node.kind === 'recipe' || node.kind === 'cluster'),
    nodes.filter((node) => node.kind === 'diagnostic' && node.diagnosticKind !== 'external'),
  ];
  return columns.flatMap((columnNodes, columnIndex) => {
    const x = LEFT_PAD + columnIndex * COLUMN_GAP;
    return columnNodes.map((node, rowIndex) => ({
      ...node,
      x,
      y: TOP_PAD + rowIndex * ROW_GAP,
      column: columnIndex,
    }));
  });
}

function graphHeight(nodes: PositionedNode[]) {
  const maxY = nodes.reduce((max, node) => Math.max(max, node.y), TOP_PAD);
  return maxY + 76;
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
