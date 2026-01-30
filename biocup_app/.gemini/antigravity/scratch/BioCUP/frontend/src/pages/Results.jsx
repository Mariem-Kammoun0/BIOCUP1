import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { generateResults, getResultById } from "../services/revisions.service";

const Results = () => {
  const { state } = useLocation();
  const navigate = useNavigate();

  const patientId = state?.patientId || state?.patient_id || null;
  const revision = state?.revision ?? state?.revision_number ?? null;
  const resultIdFromState = state?.resultId || state?.result_id || null;

  const [loading, setLoading] = useState(true);
  const [resultDoc, setResultDoc] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      setError("");
      setLoading(true);

      try {
        // ✅ Prefer fetching by resultId (avoid re-running pipeline)
        if (resultIdFromState) {
          const doc = await getResultById(resultIdFromState);
          setResultDoc(doc);
          return;
        }

        // Fallback: run pipeline if no resultId was passed
        if (!patientId || revision == null) {
          setError("Missing patientId/revision (or pass resultId).");
          return;
        }

        const out = await generateResults(patientId, revision);
        const rid = out?.result_id || out?.resultId || out?.id;

        if (!rid) {
          setError("No result_id returned. Fix generateResults() to return res.data.");
          return;
        }

        const doc = await getResultById(rid);
        setResultDoc(doc);
      } catch (e) {
        console.error(e);
        setError(e?.response?.data?.detail || e?.message || "Failed to load results.");
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [patientId, revision, resultIdFromState]);

  const view = useMemo(() => {
    const pipeline = resultDoc?.pipeline || {};
    const outputs = pipeline?.outputs || {};
    const explain = outputs?.explain_json || {};

    // ✅ What you want:
    const llmExplanation = explain?.llm_explanation || "";

    // logs/search may exist in different places
    const logs = pipeline?.logs || resultDoc?.pipeline?.logs || {};
    const searchLog =
      logs?.search ||
      logs?.qdrant_search ||
      logs?.hybrid_search ||
      "";

    return {
      pipeline,
      llmExplanation,
      searchLog,
    };
  }, [resultDoc]);

  const headerLine = useMemo(() => {
    const pid = resultDoc?.patient_id || patientId || "—";
    const rev = resultDoc?.revision ?? revision ?? "—";
    return `Patient: ${pid} • Revision: ${rev}`;
  }, [resultDoc, patientId, revision]);

  if (loading) {
    return (
      <div className="p-6">
        <button
          className="flex items-center gap-2 text-sm opacity-80 hover:opacity-100"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft size={18} /> Back
        </button>
        <div className="mt-6 text-lg font-semibold">Loading results…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <button
          className="flex items-center gap-2 text-sm opacity-80 hover:opacity-100"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft size={18} /> Back
        </button>
        <div className="mt-6 text-lg font-semibold">Results not available</div>
        <div className="mt-2 text-sm text-red-500 whitespace-pre-wrap">{error}</div>
      </div>
    );
  }

  if (!resultDoc) {
    return (
      <div className="p-6">
        <button
          className="flex items-center gap-2 text-sm opacity-80 hover:opacity-100"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft size={18} /> Back
        </button>
        <div className="mt-6 text-lg font-semibold">No result document found</div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <button
          className="flex items-center gap-2 text-sm opacity-80 hover:opacity-100"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft size={18} /> Back
        </button>
        <div className="text-sm opacity-70">{headerLine}</div>
      </div>

      {/* Title */}
      <div className="mt-6">
        <h1 className="text-2xl font-semibold">BioCUP Results</h1>
        <div className="mt-1 text-sm opacity-70">
          Result id: <span className="font-mono">{resultDoc?._id || "—"}</span>
        </div>
      </div>

      {/* ✅ LLM explanation */}
      <div className="mt-6 rounded-2xl border p-5">
        <div className="text-lg font-semibold">LLM Explanation</div>
        {view.llmExplanation ? (
          <div className="mt-3 text-sm leading-relaxed opacity-90 whitespace-pre-wrap">
            {view.llmExplanation}
          </div>
        ) : (
          <div className="mt-3 text-sm opacity-70">No LLM explanation available.</div>
        )}
      </div>


      {/* ✅ Logs: Search */}
      <div className="mt-6 rounded-2xl border p-5">
        <div className="text-lg font-semibold">Search logs</div>
        {view.searchLog ? (
          <pre className="mt-3 text-xs overflow-auto rounded-xl border p-3 opacity-90 whitespace-pre-wrap">
            {typeof view.searchLog === "string"
              ? view.searchLog
              : JSON.stringify(view.searchLog, null, 2)}
          </pre>
        ) : (
          <div className="mt-3 text-sm opacity-70">No search logs available.</div>
        )}
      </div>
    </div>
  );
};

export default Results;