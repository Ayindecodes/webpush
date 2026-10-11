export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(ApiError.describe(detail, status));
  }

  static describe(detail: unknown, status: number): string {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: string[]; msg?: string }) => {
          const field = d.loc?.filter((x) => x !== "body").join(".");
          return field ? `${field}: ${d.msg}` : (d.msg ?? "Invalid input");
        })
        .join("; ");
    }
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    return `Request failed (${status})`;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export const fetcher = <T>(path: string) => api.get<T>(path);
