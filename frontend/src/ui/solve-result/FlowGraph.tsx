import { useEffect, useMemo, useState } from 'react';
import { Background, Controls, Position, ReactFlow, type Edge, type Node } from '@xyflow/react';

import type { SolveResultDto } from '../../api/dtos';
import type { ActiveFlowGraph, FlowGraphMode } from '../../domain/solveResultFlow';
import { buildSolveResultVisualGraph, type VisualGraph, type VisualGraphEdge, type VisualGraphNode } from '../../domain/solveResultVisualGraph';
import { layoutVisualGraph, type FlowLayoutResult, type PositionedVisualGraph } from './flowLayout';
import { NodeDetails } from './NodeDetails';

export function FlowGraph({ graph, result, initialMode }: { graph: ActiveFlowGraph; result: SolveResultDto; initialMode?: FlowGraphMode }) {
  const explorerMetadataAvailable = !graph.warnings.some((warning) => warning.kind === 'recipe-topology-unavailable');
  const computedDefaultMode = useMemo(() => defaultGraphMode(graph, result, explorerMetadataAvailable), [explorerMetadataAvailable, graph, result]);
  const [graphMode, setGraphMode] = useState<FlowGraphMode>(() => normalizeMode(initialMode ?? computedDefaultMode));
  const [userSelectedMode, setUserSelectedMode] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [layoutResult, setLayoutResult] = useState<FlowLayoutResult | null>(null);
  const visualGraph = useMemo(
    () => graphMode === 'optimizer-overlay'
      ? buildSolveResultVisualGraph(graph, result, { explorerMetadataAvailable })
      : buildSolveResultVisualGraph(graph, { ...result, sparse_clustering: null }, { explorerMetadataAvailable }),
    [explorerMetadataAvailable, graph, graphMode, result],
  );
  const prominentDiagnostics = graph.diagnostics.filter((diagnostic) => diagnostic.kind === 'unmet' || diagnostic.kind === 'surplus');
  const selectedIdExists = selectedId ? selectedVisualIdExists(visualGraph, selectedId) : true;
  const effectiveSelectedId = selectedIdExists ? selectedId : null;
  const selectedDetails = effectiveSelectedId ? visualGraph.detailById.get(effectiveSelectedId) ?? null : null;
  const layoutGraph = layoutResult?.ok && layoutResult.graph.graph === visualGraph ? layoutResult.graph : null;
  const flowNodes = useMemo(() => layoutGraph ? toReactFlowNodes(layoutGraph, selectedId) : [], [layoutGraph, selectedId]);
  const flowEdges = useMemo(() => layoutGraph ? toReactFlowEdges(layoutGraph, selectedId) : [], [layoutGraph, selectedId]);

  useEffect(() => {
    let cancelled = false;
    setLayoutResult(null);
    void layoutVisualGraph(visualGraph).then((next) => {
      if (!cancelled) setLayoutResult(next);
    });
    return () => { cancelled = true; };
  }, [visualGraph]);

  useEffect(() => {
    if (!selectedIdExists) setSelectedId(null);
  }, [selectedIdExists]);

  useEffect(() => {
    if (!initialMode && !userSelectedMode) setGraphMode(computedDefaultMode);
  }, [computedDefaultMode, initialMode, userSelectedMode]);

  return (
    <section className="flow-graph-panel" aria-labelledby="flow-graph-title">
      <div className="flow-graph-heading">
        <div>
          <p className="eyebrow">Active flow graph</p>
          <h3 id="flow-graph-title">Solved item and recipe flow</h3>
          <p className="muted">React Flow view of active recipes, diagnostics, and optimizer clusters when complete.</p>
        </div>
        <div className="flow-graph-counts">
          <span><strong>{visualGraph.nodes.length}</strong> nodes</span>
          <span><strong>{visualGraph.edges.length}</strong> edges</span>
          <span><strong>{graph.warnings.length}</strong> warnings</span>
        </div>
      </div>

      <fieldset className="flow-mode-controls">
        <legend>Graph mode</legend>
        {GRAPH_MODES.map((mode) => (
          <button key={mode.id} type="button" className={graphMode === mode.id ? 'active' : ''} onClick={() => { setUserSelectedMode(true); setGraphMode(mode.id); }} aria-pressed={graphMode === mode.id}>
            <strong>{mode.label}</strong>
            <span>{mode.hint}</span>
          </button>
        ))}
      </fieldset>

      {graphMode === 'optimizer-overlay' && <OptimizerOverlayNotice visualGraph={visualGraph} />}

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
          <ul>{graph.warnings.map((warning, index) => <li key={`${warning.kind}:${index}`}>{warning.message}</li>)}</ul>
        </div>
      )}

      {visualGraph.notices
        .filter((notice) => graphMode !== 'optimizer-overlay' || notice.severity !== 'warning')
        .map((notice) => <output key={notice.code} className={`flow-overlay-note ${notice.severity}`}><strong>{notice.code}</strong><span>{notice.message}</span></output>)}
      {layoutResult && !layoutResult.ok && <output className="flow-overlay-note warning"><strong>Layout unavailable</strong><span>{layoutResult.message}</span></output>}

      {visualGraph.nodes.length === 0 ? (
        <p className="muted">No active positive flows or positive diagnostics were found in this result.</p>
      ) : (
        <div className="flow-graph-with-details">
          <div className="flow-graph-canvas rf-flow-canvas" data-testid="react-flow-shell">
            <div className="flow-graph-legend">
              <span className="legend-swatch external" /> External supply
              <span className="legend-swatch recipe" /> Recipe
              <span className="legend-swatch item" /> Item / pool
              <span className="legend-swatch unmet" /> Unmet demand
              <span className="legend-swatch surplus" /> Surplus
            </div>
            {!layoutResult && <p className="muted rf-flow-status">Laying out graph…</p>}
            {layoutGraph && (
              <ReactFlow nodes={flowNodes} edges={flowEdges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable onNodeClick={(_, node) => setSelectedId(node.id)} onEdgeClick={(_, edge) => setSelectedId(edge.id)}>
                <Background />
                <Controls showInteractive={false} />
              </ReactFlow>
            )}
          </div>
          <NodeDetails details={selectedDetails} />
        </div>
      )}
    </section>
  );
}

const GRAPH_MODES: Array<{ id: FlowGraphMode; label: string; hint: string }> = [
  { id: 'raw', label: 'Raw LP flow', hint: 'Ungrouped' },
  { id: 'optimizer-overlay', label: 'Optimizer overlay', hint: 'Show clusters' },
];

function defaultGraphMode(graph: ActiveFlowGraph, result: SolveResultDto, explorerMetadataAvailable: boolean): FlowGraphMode {
  return buildSolveResultVisualGraph(graph, result, { explorerMetadataAvailable }).mode === 'sparse-overview' ? 'optimizer-overlay' : 'raw';
}

export function normalizeMode(mode: FlowGraphMode): FlowGraphMode {
  return mode === 'heuristic' ? 'raw' : mode;
}

export function selectedVisualIdExists(visualGraph: VisualGraph, id: string): boolean {
  return visualGraph.nodes.some((node) => node.id === id) || visualGraph.edges.some((edge) => edge.id === id);
}

function OptimizerOverlayNotice({ visualGraph }: { visualGraph: VisualGraph }) {
  if (visualGraph.mode === 'sparse-overview') {
    return <div className="flow-overlay-note success"><strong>Overlay source</strong><span>Sparse clustering. Complete active recipe mapping.</span></div>;
  }
  const reason = visualGraph.notices[0]?.message ?? 'Sparse cluster overview is unavailable.';
  return <output className="flow-overlay-note warning"><strong>Overlay unavailable</strong><span>{reason} Displaying raw projection instead.</span></output>;
}

function toReactFlowNodes(layout: PositionedVisualGraph, selectedId: string | null): Node[] {
  return layout.nodes.map((node) => ({
    id: node.id,
    position: { x: node.x, y: node.y },
    data: { label: <FlowNodeLabel node={node} /> },
    className: `rf-flow-node rf-flow-node-${nodeClass(node)} ${selectedId === node.id ? 'selected' : ''}`,
    style: { width: node.width, height: node.height },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    selected: selectedId === node.id,
    type: 'default',
    draggable: false,
    selectable: true,
    connectable: false,
    focusable: true,
    ariaLabel: node.label,
  }));
}

export function toReactFlowEdges(layout: PositionedVisualGraph, selectedId: string | null): Edge[] {
  return layout.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edgeLabel(edge),
    className: `rf-flow-edge rf-flow-edge-${edge.visualKind} ${selectedId === edge.id ? 'selected' : ''}`,
    selected: selectedId === edge.id,
    animated: false,
  }));
}

function FlowNodeLabel({ node }: { node: PositionedVisualGraph['nodes'][number] }) {
  return <div className="rf-flow-node-label"><strong>{shortLabel(node.label)}</strong>{node.visualKind === 'cluster' && <span>{node.recipeCount} recipes</span>}{node.visualKind === 'item-pool' && <span>item pool</span>}{node.visualKind === 'raw' && node.quantity !== undefined && <span>{formatNumber(node.quantity)}</span>}</div>;
}

function nodeClass(node: VisualGraphNode) {
  if (node.visualKind === 'cluster') return 'cluster';
  if (node.visualKind === 'item-pool') return 'item-pool';
  return node.kind === 'diagnostic' ? `diagnostic-${node.diagnosticKind ?? 'unknown'}` : node.kind;
}

function edgeLabel(edge: VisualGraphEdge) {
  const quantity = 'quantity' in edge ? formatNumber(edge.quantity) : '';
  return edge.itemId ? `${edge.itemId} · ${quantity}` : quantity;
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toPrecision(6);
}

function shortLabel(label: string) {
  return label.length > 34 ? `${label.slice(0, 31)}…` : label;
}
