export function createClientFileId(file: File): string {
  const randomPart =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

  return `${file.name}-${file.size}-${file.lastModified}-${randomPart}`;
}
