import api from "./api";

/* =====================================================
   JSON endpoints (sans images)
   ===================================================== */

/**
 * POST /patients/{id}/submit
 * Crée une révision (ou version initiale)
 */
export const submitPatientForm = async (patientId, form) => {
  const res = await api.post(`/patients/${patientId}/submit`, form);
  return res.data;
};

/**
 * GET /patients/{id}/revisions
 * Liste des révisions (si tu gardes plusieurs revisions)
 */
export const getRevisions = async (patientId) => {
  const res = await api.get(`/patients/${patientId}/revisions`);
  return res.data;
};

/**
 * GET /patients/{id}/revisions/{rev}
 * Récupère UNE révision complète (form_data, chunks, images…)
 */
export const getRevision = async (patientId, rev) => {
  const res = await api.get(`/patients/${patientId}/revisions/${rev}`);
  return res.data;
};

/**
 * PUT /patients/{id}/revisions/{rev}
 * Update révision sans images
 */
export const updateRevision = async (patientId, rev, form) => {
  const res = await api.put(`/patients/${patientId}/revisions/${rev}`, form);
  return res.data;
};

/* =====================================================
   Multipart endpoints (avec images)
   ===================================================== */

/**
 * POST /patients/{id}/submit-multipart
 * Crée une révision avec images
 */
export const submitPatientFormWithImages = async (patientId, form, images = []) => {
  const formData = new FormData();
  formData.append("form", JSON.stringify(form));

  images.forEach((file) => {
    formData.append("images", file);
  });

  const res = await api.post(
    `/patients/${patientId}/submit-multipart`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );

  return res.data;
};

/**
 * PUT /patients/{id}/revisions/{rev}/multipart
 * Update révision + ajout d’images
 */
export const updateRevisionWithImages = async (patientId, rev, form, images = []) => {
  const formData = new FormData();
  formData.append("form", JSON.stringify(form));

  images.forEach((file) => {
    formData.append("images", file);
  });

  const res = await api.put(
    `/patients/${patientId}/revisions/${rev}/multipart`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );

  return res.data;
};

/* =====================================================
   OPTIONAL – si tu passes à "UNE SEULE REVISION"
   ===================================================== */

/**
 * GET /patients/{id}/revision
 * (si tu décides d’avoir une seule révision par patient)
 */
// export const getSingleRevision = async (patientId) => {
//   const res = await api.get(`/patients/${patientId}/revision`);
//   return res.data;
// };

// revisions.service.js
export const generateResults = (patientId, revision) =>
  api.post(`/results/${patientId}/${revision}`).then((r) => r.data);


export const getResultById = (resultId) =>
  api.get(`/results/${resultId}`).then((r) => r.data);  
