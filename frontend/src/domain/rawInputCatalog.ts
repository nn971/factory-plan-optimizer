import type { ExternalInputDto, ItemDto, ProblemDto } from '../api/dtos';
import type { EditableExternalInput } from './problemState';
import { friendlyItemName } from './itemDisplay';

export type RawInputCatalogEntry = {
  item_id: string;
  kind: ExternalInputDto['kind'];
  label: string;
  isStartupSuggestion: boolean;
  isExisting: boolean;
  source?: ExternalInputDto['source'];
  defaultApproved: boolean;
};

export type RawInputSelectionAction =
  | { type: 'focus'; item_id: string }
  | { type: 'add'; item_id: string; kind: ExternalInputDto['kind']; source?: ExternalInputDto['source']; default_approved?: boolean };

export type DropdownState = { open: boolean; activeIndex: number };
export type DropdownKey = 'ArrowDown' | 'ArrowUp' | 'Enter' | 'Escape';

const RESULT_LIMIT = 50;

export function rawInputSearchResults(
  problem: Pick<ProblemDto, 'items' | 'raw_input_candidates'>,
  rows: EditableExternalInput[],
  query: string,
  limit = RESULT_LIMIT,
): RawInputCatalogEntry[] {
  const suggestions = new Map((problem.raw_input_candidates ?? []).map((input, index) => [
    input.item_id,
    { input, index },
  ]));
  const existing = new Set(rows.map((row) => row.item_id));
  const byId = new Map<string, RawInputCatalogEntry>();

  const add = (id: string, kind: ExternalInputDto['kind'] | undefined, source?: ExternalInputDto['source'], defaultApproved = false) => {
    const suggestion = suggestions.get(id)?.input;
    const current = byId.get(id);
    byId.set(id, {
      item_id: id,
      kind: current?.kind ?? kind ?? suggestion?.kind ?? 'unknown',
      label: friendlyItemName(id),
      isStartupSuggestion: suggestions.has(id),
      isExisting: existing.has(id),
      source: suggestion?.source ?? source ?? current?.source,
      defaultApproved: suggestion?.default_approved ?? (defaultApproved || current?.defaultApproved || false),
    });
  };

  for (const item of problem.items) add(item.id, item.kind);
  for (const row of rows) add(row.item_id, row.kind, row.source, row.defaultApproved);
  for (const { input } of suggestions.values()) add(input.item_id, input.kind, input.source, input.default_approved ?? false);

  const normalizedQuery = query.trim().toLowerCase();
  const ranked = [...byId.values()].flatMap((entry) => {
    const id = entry.item_id.toLowerCase();
    const label = entry.label.toLowerCase();
    if (!normalizedQuery) return entry.isStartupSuggestion ? [{ entry, rank: 0 }] : [];
    const exact = id === normalizedQuery || label === normalizedQuery;
    const prefix = id.startsWith(normalizedQuery) || label.startsWith(normalizedQuery);
    const substring = id.includes(normalizedQuery) || label.includes(normalizedQuery);
    if (!substring) return [];
    return [{ entry, rank: entry.isStartupSuggestion ? 0 : exact ? 1 : prefix ? 2 : 3 }];
  });

  return ranked
    .sort((left, right) => left.rank - right.rank || suggestionOrder(left.entry, suggestions) - suggestionOrder(right.entry, suggestions) || left.entry.item_id.localeCompare(right.entry.item_id))
    .slice(0, limit)
    .map(({ entry }) => entry);
}

export function selectionAction(entry: RawInputCatalogEntry): RawInputSelectionAction {
  return entry.isExisting
    ? { type: 'focus', item_id: entry.item_id }
    : { type: 'add', item_id: entry.item_id, kind: entry.kind, source: entry.source, default_approved: entry.defaultApproved };
}

export function dropdownKeyTransition(state: DropdownState, key: DropdownKey, resultCount: number): DropdownState & { select: boolean } {
  if (key === 'Escape') return { open: false, activeIndex: -1, select: false };
  if (key === 'Enter') return { ...state, select: state.open && state.activeIndex >= 0 && state.activeIndex < resultCount };
  if (key === 'ArrowDown') {
    if (resultCount <= 0) return { open: true, activeIndex: -1, select: false };
    return { open: true, activeIndex: state.activeIndex < 0 ? 0 : (state.activeIndex + 1) % resultCount, select: false };
  }
  if (resultCount <= 0) return { open: true, activeIndex: -1, select: false };
  return { open: true, activeIndex: state.activeIndex < 0 ? resultCount - 1 : (state.activeIndex - 1 + resultCount) % resultCount, select: false };
}

export function dropdownClosedState(): DropdownState {
  return { open: false, activeIndex: -1 };
}

function suggestionOrder(entry: RawInputCatalogEntry, suggestions: Map<string, { input: ItemDto | ExternalInputDto; index: number }>): number {
  return suggestions.get(entry.item_id)?.index ?? Number.MAX_SAFE_INTEGER;
}
