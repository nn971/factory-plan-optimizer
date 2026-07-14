export function friendlyItemName(itemId: string): string {
  return itemId
    .split('-')
    .map((part) => (part ? `${part[0].toUpperCase()}${part.slice(1)}` : part))
    .join(' ');
}
