export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "通信に失敗しました" }));
    throw new Error(body.detail ?? "通信に失敗しました");
  }
  return response.json() as Promise<T>;
}

export function participantHeaders(): HeadersInit {
  const token = sessionStorage.getItem("participantToken");
  return token ? { Authorization: `Bearer ${token}` } : {};
}
