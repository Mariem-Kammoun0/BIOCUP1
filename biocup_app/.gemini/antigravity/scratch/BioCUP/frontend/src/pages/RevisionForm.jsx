import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  submitPatientForm,
  getRevision,
  updateRevision,
  submitPatientFormWithImages,
  updateRevisionWithImages,
  generateResults, // ✅ NEW: triggers CSV → Qdrant → LLM and stores results
} from "../services/revisions.service";

/**
 * ✅ RevisionForm (Minimal changes)
 * - Keeps create/edit flow
 * - Uses services ONLY
 * - Uses multipart endpoints when images exist
 * - Prefills form from form_data
 * - On Generate:
 *    1) Save/update revision (stores generated_report_text server-side)
 *    2) Trigger pipeline (CSV → Qdrant → LLM)
 *    3) Go to Results (read-only page)
 */

const RevisionForm = () => {
  const navigate = useNavigate();
  const { state } = useLocation();

  const patientId = state?.patientId;
  const mode = state?.mode || "create"; // "create" | "edit"
  const rev = state?.revision ?? null;

  const [loading, setLoading] = useState(false);

  // PatientForm fields
  const [histology, setHistology] = useState("");
  const [metastasisSites, setMetastasisSites] = useState(""); // comma-separated
  const [lymph, setLymph] = useState("");
  const [tnm, setTnm] = useState("");
  const [notes, setNotes] = useState("");

  const [ihc, setIhc] = useState({
    CK7: "",
    CK20: "",
    TTF1: "",
    CDX2: "",
  });

  // Images
  const [images, setImages] = useState([]); // new File[]
  const [existingImages, setExistingImages] = useState([]); // backend images metadata

  // ---------- Helpers ----------
  const buildPayload = () => ({
    histology: histology || null,
    metastasis_sites: metastasisSites
      ? metastasisSites
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : [],
    lymph_nodes_summary: lymph || null,
    tnm: tnm || null,
    ihc: {
      CK7: ihc.CK7 || null,
      CK20: ihc.CK20 || null,
      "TTF-1": ihc.TTF1 || null,
      CDX2: ihc.CDX2 || null,
    },
    notes: notes || null,
  });

  const resetNewImages = () => setImages([]);

  const onPickImages = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    // accept only image/*
    const filtered = files.filter((f) => f.type?.startsWith("image/"));
    if (filtered.length !== files.length) {
      console.warn("Some non-image files were ignored.");
    }

    setImages((prev) => [...prev, ...filtered]);
    e.target.value = ""; // allow re-pick same file
  };

  const removeNewImage = (idx) => {
    setImages((prev) => prev.filter((_, i) => i !== idx));
  };

  // previews for new images
  const newImagePreviews = useMemo(() => {
    return images.map((file) => ({
      file,
      url: URL.createObjectURL(file),
    }));
  }, [images]);

  // cleanup previews
  useEffect(() => {
    return () => {
      newImagePreviews.forEach((p) => URL.revokeObjectURL(p.url));
    };
  }, [newImagePreviews]);

  // ---------- Load revision on edit ----------
  useEffect(() => {
    const load = async () => {
      if (!patientId) return;
      if (mode !== "edit") return;
      if (rev === null || rev === undefined) return;

      setLoading(true);
      try {
        const data = await getRevision(patientId, rev);
        const f = data?.form_data || {};

        setHistology(f.histology || "");
        setMetastasisSites((f.metastasis_sites || []).join(", "));
        setLymph(f.lymph_nodes_summary || "");
        setTnm(f.tnm || "");
        setNotes(f.notes || "");

        setIhc({
          CK7: f.ihc?.CK7 || "",
          CK20: f.ihc?.CK20 || "",
          TTF1: f.ihc?.["TTF-1"] || f.ihc?.TTF1 || "",
          CDX2: f.ihc?.CDX2 || "",
        });

        setExistingImages(data?.images || []);
      } catch (e) {
        console.error(e);
        alert("Failed to load revision.");
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [mode, patientId, rev]);

  // ---------- Submit ----------
  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!patientId) {
      alert("Missing patientId");
      return;
    }

    setLoading(true);
    try {
      const payload = buildPayload();
      const isEdit = mode === "edit" && rev !== null && rev !== undefined;

      let revisionNumber = rev;

      // ✅ Images => multipart services
      if (images.length > 0) {
        if (isEdit) {
          await updateRevisionWithImages(patientId, rev, payload, images);
          revisionNumber = rev;
        } else {
          const out = await submitPatientFormWithImages(patientId, payload, images);
          revisionNumber = out?.revision;
        }

        resetNewImages();

        // ✅ NEW: Trigger pipeline + store results
        const out = await generateResults(patientId, revisionNumber);
        navigate("/results", { state: { patientId, revision: revisionNumber, resultId: out.result_id } });

        return;
      }

      // ✅ No images => JSON services
      if (isEdit) {
        await updateRevision(patientId, rev, payload);
        revisionNumber = rev;
      } else {
        const out = await submitPatientForm(patientId, payload);
        revisionNumber = out?.revision;
      }

      // ✅ NEW: Trigger pipeline + store results
      await generateResults(patientId, revisionNumber);

      navigate("/results", { state: { patientId, revision: revisionNumber } });
    } catch (err) {
      console.error(err);
      alert(err?.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-slide-up">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-display font-bold text-slate-800">
            {mode === "edit" ? "Update Revision" : "Create Revision"}
          </h2>
          <p className="text-slate-500 mt-1 font-medium">
            Add reports, biomarkers, structured data, and optional images, then generate Results.
          </p>
        </div>

        <button
          type="button"
          onClick={() => navigate("/dashboard")}
          className="px-4 py-2.5 text-slate-600 hover:text-medic-600 hover:bg-medic-50/50 rounded-lg font-medium"
        >
          Back
        </button>
      </div>

      <form onSubmit={handleGenerate} className="glass-panel p-6 rounded-2xl space-y-6">
        <div className="grid md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Histology</label>
            <input
              value={histology}
              onChange={(e) => setHistology(e.target.value)}
              className="w-full p-3 bg-white border border-slate-200 rounded-xl outline-none"
              placeholder="e.g. Adenocarcinoma"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Metastasis Sites</label>
            <input
              value={metastasisSites}
              onChange={(e) => setMetastasisSites(e.target.value)}
              className="w-full p-3 bg-white border border-slate-200 rounded-xl outline-none"
              placeholder="e.g. liver, bone, lymph nodes"
            />
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Lymph Nodes Summary</label>
            <input
              value={lymph}
              onChange={(e) => setLymph(e.target.value)}
              className="w-full p-3 bg-white border border-slate-200 rounded-xl outline-none"
              placeholder='e.g. "0/6 negative"'
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">TNM</label>
            <input
              value={tnm}
              onChange={(e) => setTnm(e.target.value)}
              className="w-full p-3 bg-white border border-slate-200 rounded-xl outline-none"
              placeholder="e.g. pT2N0M1"
            />
          </div>
        </div>

        <div className="space-y-3">
          <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">IHC</label>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {["CK7", "CK20", "TTF1", "CDX2"].map((k) => (
              <input
                key={k}
                value={ihc[k]}
                onChange={(e) => setIhc((prev) => ({ ...prev, [k]: e.target.value }))}
                className="p-3 bg-white border border-slate-200 rounded-xl outline-none"
                placeholder={k}
              />
            ))}
          </div>
          <div className="text-[11px] text-slate-500">
            Note: TTF1 is stored as <b>TTF-1</b> in backend payload.
          </div>
        </div>

        {/* Images */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Images (optional)</label>

            <label className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-slate-200 cursor-pointer hover:bg-slate-50">
              <span className="text-sm font-semibold text-slate-700">Add images</span>
              <input type="file" accept="image/*" multiple onChange={onPickImages} className="hidden" />
            </label>
          </div>

          {/* Existing images */}
          {existingImages?.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-semibold text-slate-500">Existing images</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {existingImages.map((img, idx) => (
                  <a
                    key={idx}
                    href={img.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block rounded-xl overflow-hidden border border-slate-200 bg-white"
                    title={img.filename || "image"}
                  >
                    <img src={img.url} alt={img.filename || "existing"} className="w-full h-28 object-cover" />
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* New selected images */}
          {newImagePreviews.length > 0 ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {newImagePreviews.map((p, idx) => (
                <div key={idx} className="rounded-xl overflow-hidden border border-slate-200 bg-white relative">
                  <img src={p.url} alt={p.file.name} className="w-full h-28 object-cover" />
                  <button
                    type="button"
                    onClick={() => removeNewImage(idx)}
                    className="absolute top-2 right-2 bg-white/90 hover:bg-white text-slate-700 text-xs font-bold px-2 py-1 rounded-lg shadow"
                    title="Remove"
                  >
                    ✕
                  </button>
                  <div className="p-2">
                    <div className="text-[11px] font-semibold text-slate-700 truncate">{p.file.name}</div>
                    <div className="text-[10px] text-slate-500">{(p.file.size / 1024).toFixed(0)} KB</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-slate-500">
              You can upload IHC slides, imaging snapshots, or pathology images (PNG/JPG).
            </div>
          )}
        </div>

        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Notes</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full p-3 bg-white border border-slate-200 rounded-xl outline-none resize-none"
            rows={4}
            placeholder="Additional clinical comments..."
          />
        </div>

        <div className="flex justify-end pt-2">
          <button
            type="submit"
            disabled={loading}
            className="bg-medic-600 hover:bg-medic-700 text-white px-8 py-3 rounded-xl font-bold shadow-lg"
          >
            {loading ? "Generating..." : "Generate Results"}
          </button>
        </div>
      </form>
    </div>
  );
};

export default RevisionForm;