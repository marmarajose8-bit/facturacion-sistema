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
  if (auth) headers["Authorization"] = `Bearer ${Auth.getToken()}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    Auth.logout();
    throw new Error("Sesión expirada");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Error en la solicitud");
  return data;
}

const fmt = {
  money: (n) => new Intl.NumberFormat("es-DO", { style: "currency", currency: "DOP" }).format(n || 0),
  date: (d) => {
    if (!d) return "";
    // Construye la fecha con los componentes locales en vez de dejar que
    // "new Date(...)" la interprete como medianoche UTC — eso es lo que
    // causaba que se mostrara un dia antes en la hora de RD (UTC-4).
    const soloFecha = String(d).split("T")[0];
    const [y, m, day] = soloFecha.split("-").map(Number);
    return new Date(y, m - 1, day).toLocaleDateString("es-DO", { year: "numeric", month: "short", day: "numeric" });
  },
};

// Descarga el PDF de una factura (autenticado) y dispara la descarga en el navegador.
async function descargarPDFFactura(facturaId, numeroFactura) {
  const res = await fetch(`${API_BASE}/api/facturas/${facturaId}/pdf`, {
    headers: { Authorization: `Bearer ${Auth.getToken()}` },
  });
  if (!res.ok) throw new Error("No se pudo generar el PDF");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `factura_${numeroFactura}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

function abrirWhatsapp(telefono, mensaje) {
  const numero = telefono.replace(/[^\d]/g, "");
  const numeroConCodigo = numero.length === 10 ? `1${numero}` : numero;
  const url = `https://wa.me/${numeroConCodigo}?text=${encodeURIComponent(mensaje)}`;
  window.open(url, "_blank");
}

function toast(msg, tipo = "info") {
  const el = document.createElement("div");
  el.textContent = msg;
  el.style.cssText = `
    position: fixed; bottom: 20px; right: 20px; z-index: 9999;
    padding: 12px 20px; border-radius: 8px; color: white;
    background: ${tipo === "error" ? "#dc2626" : "#16a34a"};
    box-shadow: 0 4px 12px rgba(0,0,0,0.2); font-size: 14px;
    max-width: 320px;
  `;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
