import type { ExplorerItemDto, ExplorerRecipeDto, ExplorerResponseDto } from '../api/dtos';

export type ExplorerSelection =
  | { type: 'item'; id: string }
  | { type: 'recipe'; id: string }
  | null;

export type ExplorerKindFilter = 'all' | 'item' | 'fluid' | 'unknown';

export function filterExplorerItems(
  items: ExplorerItemDto[],
  search: string,
  kind: ExplorerKindFilter,
  category: string,
): ExplorerItemDto[] {
  const normalized = search.trim().toLowerCase();
  return items.filter((item) => {
    const matchesSearch = normalized === '' || item.id.toLowerCase().includes(normalized);
    const matchesKind = kind === 'all' || item.kind === kind;
    const matchesCategory = category === 'all' || item.category === category;
    return matchesSearch && matchesKind && matchesCategory;
  });
}

export function filterExplorerRecipes(
  recipes: ExplorerRecipeDto[],
  search: string,
  category: string,
): ExplorerRecipeDto[] {
  const normalized = search.trim().toLowerCase();
  return recipes.filter((recipe) => {
    const matchesSearch = normalized === '' || recipe.id.toLowerCase().includes(normalized);
    const matchesCategory = category === 'all' || recipe.category === category;
    return matchesSearch && matchesCategory;
  });
}

export function selectionExists(selection: ExplorerSelection, explorer: ExplorerResponseDto): boolean {
  if (!selection) return true;
  if (selection.type === 'item') return explorer.items.some((item) => item.id === selection.id);
  return explorer.recipes.some((recipe) => recipe.id === selection.id);
}

export function selectedItem(selection: ExplorerSelection, explorer: ExplorerResponseDto | null) {
  if (!explorer || selection?.type !== 'item') return undefined;
  return explorer.items.find((item) => item.id === selection.id);
}

export function selectedRecipe(selection: ExplorerSelection, explorer: ExplorerResponseDto | null) {
  if (!explorer || selection?.type !== 'recipe') return undefined;
  return explorer.recipes.find((recipe) => recipe.id === selection.id);
}
