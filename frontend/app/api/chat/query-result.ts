import { emptyResultPreview, type ResultPreview, type ResultRow } from "./normalize";

type UpstreamPayload = Record<string, unknown>;

function coerceColumns(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((column): column is string => typeof column === "string");
}

function coerceResultRows(value: unknown): ResultRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((row): row is ResultRow => row !== null && typeof row === "object" && !Array.isArray(row));
}

export async function loadResultPreview(payload: UpstreamPayload): Promise<ResultPreview> {
  const result = payload.result;
  if (result === null || typeof result !== "object" || Array.isArray(result)) {
    return emptyResultPreview();
  }

  const resultObject = result as Record<string, unknown>;
  const columns = coerceColumns(resultObject.columns);
  const rows = coerceResultRows(resultObject.rows);
  const rowCount = typeof resultObject.row_count === "number" ? resultObject.row_count : rows.length;

  return {
    columns,
    rows,
    row_count: rowCount,
  };
}
