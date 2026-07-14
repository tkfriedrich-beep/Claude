// Shared WAI-ARIA keyboard helpers.

/**
 * WAI-ARIA radio-group arrow-key handling. Given the current index, resolves the next index
 * for ArrowRight/Down (next, wrapping), ArrowLeft/Up (previous, wrapping), Home (first) and
 * End (last), calls `onSelect`, and prevents default. Returns true if it handled the key.
 * Callers own selection + roving focus (move focus to the newly selected control).
 */
export function handleRadioKeys(
  event: { key: string; preventDefault: () => void },
  count: number,
  currentIndex: number,
  onSelect: (index: number) => void,
): boolean {
  if (count <= 0) return false;
  const from = currentIndex < 0 ? 0 : currentIndex;
  let next: number;
  switch (event.key) {
    case "ArrowRight":
    case "ArrowDown":
      next = (from + 1) % count;
      break;
    case "ArrowLeft":
    case "ArrowUp":
      next = (from - 1 + count) % count;
      break;
    case "Home":
      next = 0;
      break;
    case "End":
      next = count - 1;
      break;
    default:
      return false;
  }
  event.preventDefault();
  onSelect(next);
  return true;
}
