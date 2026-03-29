export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
export const WS_BASE = API_BASE.replace(/^http/, "ws");
