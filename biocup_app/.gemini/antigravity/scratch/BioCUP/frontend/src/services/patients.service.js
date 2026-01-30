import api from "./api";

// GET /patients
export const getPatients = async () => {
  const res = await api.get("/patients");
  return res.data;
};

// POST /patients
export const createPatient = async (payload) => {
  const res = await api.post("/patients", payload);
  return res.data;
};

// PUT /patients/{id}
export const updatePatient = async (id, payload) => {
  const res = await api.put(`/patients/${id}`, payload);
  return res.data;
};

// DELETE /patients/{id}
export const deletePatient = async (id) => {
  const res = await api.delete(`/patients/${id}`);
  return res.data;
};
