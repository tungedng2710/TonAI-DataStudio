export function repositoryPathForUpload(file: File): string {
  const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
  const pathParts = relative?.split("/") ?? [];
  return pathParts.length > 1 ? pathParts.slice(1).join("/") : file.name;
}
