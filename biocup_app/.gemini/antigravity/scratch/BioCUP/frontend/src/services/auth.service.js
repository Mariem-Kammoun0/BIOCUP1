import api from "./api";

// POST /auth/register
export const register = async (data) => {
  const res = await api.post("/auth/register", data);
  return res.data;
};

// POST /auth/login
export const login = async (data) => {
  const res = await api.post("/auth/login", data);

  // Sauvegarder le token
  localStorage.setItem("token", res.data.access_token);

  return res.data;
};
