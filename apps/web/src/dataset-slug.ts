export function normalizeDatasetSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/-{2,}/g, "-");
}
