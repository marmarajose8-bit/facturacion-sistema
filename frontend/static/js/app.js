// Configuración central de la API.
// Por defecto usa el MISMO dominio donde se sirve el frontend (funciona
// tanto en local con nginx+backend en el mismo host como en Railway,
// donde frontend y backend van en un solo servicio).
// Si el backend vive en otro host, define window.API_BASE antes de cargar
// este archivo, ej: <script>window.API_BASE = "https://api.tudominio.com";</script>
const API_BASE = window.API_BASE || "";

const Auth = {
  getToken: () => localStorage.getItem("fa_token"),
  setToken: (t) => localStorage.setItem("fa_token", t),
  setUsuario: (u) => localStorage.setItem("fa_usuario", JSON.stringify(u)),
  getUsuario: () => JSON.parse(localStorage.getItem("fa_usuario") || "null"),
  logout: () => {
    localStorage.removeItem("fa_token");
    localStorage.removeItem("fa_usuario");
    window.location.href = "index.html";
  },
  requireAuth: () => {
    if (!Auth.getToken()) window.location.href = "index.html";
  },
};

async function api(path, { method = "GET", body = null, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && Auth.getToken()) headers["Authorization"] = `Bearer ${Auth.getToken()}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  if (res.status === 401) {
    Auth.logout();
    return;
  }

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail || `Error ${res.status}`);
  }
  return data;
}

const fmt = {
  money: (n) => new Intl.NumberFormat("es-DO", { style: "currency", currency: "DOP" }).format(n || 0),
  date: (d) => new Date(d).toLocaleDateString("es-DO", { year: "numeric", month: "short", day: "numeric" }),
};

function toast(msg, tipo = "info") {
  const el = document.createElement("div");
  el.className = `fixed bottom-6 right-6 panel px-5 py-3 shadow-lg z-50 text-sm`;
  el.style.borderColor = tipo === "error" ? "var(--danger-2)" : "var(--accent)";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
