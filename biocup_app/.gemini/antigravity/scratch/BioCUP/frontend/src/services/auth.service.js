import api from "./api";

// POST /auth/register
export const register = async (data) => {
  const res = await api.post("/auth/register", data);
  return res.data;
};

// POST /auth/login  ✅ OAuth2-compliant

export const login = async ({ email, password }) => {
  const res = await api.post("/auth/login", { email, password });
  localStorage.setItem("token", res.data.access_token);
  return res.data;
};