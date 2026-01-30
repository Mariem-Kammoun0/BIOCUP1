import axios from "axios";

const api = axios.create({
  baseURL: "http://127.0.0.1:8000", // FastAPI
  headers: {
    "Content-Type": "application/json",
  },
});

// 🔐 Ajouter automatiquement le token
api.interceptors.request.use((config) => {
  const token =
    localStorage.getItem("access_token") ||
    localStorage.getItem("token") ||
    localStorage.getItem("jwt");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
