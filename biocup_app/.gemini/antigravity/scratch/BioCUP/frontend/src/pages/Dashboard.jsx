import React, { useEffect, useState } from "react";
import { Search, Filter, Plus, TrendingUp, Users, Activity } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { getPatients } from "../services/patients.service";

const Dashboard = () => {
  const navigate = useNavigate();
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);

  const calculateAge = (dob) => {
    if (!dob) return "";
    const birth = new Date(dob);
    if (Number.isNaN(birth.getTime())) return "";
    const today = new Date();
    let age = today.getFullYear() - birth.getFullYear();
    const m = today.getMonth() - birth.getMonth();
    if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
    return age;
  };

  const formatDate = (iso) => {
    if (!iso) return "";
    return String(iso).slice(0, 10);
  };

  useEffect(() => {
    const normalizePatients = (data) => {
      const arr = Array.isArray(data) ? data : data?.patients || [];
      return arr.map((p) => {
        // ✅ backend: active_revision is 0 or 1 (or could be string), normalize to number
        const activeRev = Number(p.active_revision ?? 0);
        const hasRevision = activeRev === 1;

        return {
          id: p.id,
          name: p.full_name || "Unknown",
          age: calculateAge(p.dob),
          sex: p.sex || "",
          diagnosis: hasRevision ? "Analyzed" : "Pending",
          last_updated: formatDate(p.updated_at || p.created_at),
          raw: { ...p, active_revision: activeRev },
          hasRevision,
        };
      });
    };

    const fetchPatients = async () => {
      try {
        const data = await getPatients();
        setPatients(normalizePatients(data));
      } catch (err) {
        console.error(err);
        setPatients([]);
      } finally {
        setLoading(false);
      }
    };

    fetchPatients();
  },[]);

  const stats = [
    { label: "Active Cases", value: "12", icon: Users, color: "text-medic-600", bg: "bg-medic-50" },
    { label: "Pending Analysis", value: "3", icon: Activity, color: "text-amber-600", bg: "bg-amber-50" },
    { label: "High Confidence", value: "87%", icon: TrendingUp, color: "text-emerald-600", bg: "bg-emerald-50" },
  ];

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between md:items-center gap-4">
        <div>
          <h2 className="text-3xl font-display font-bold text-slate-800">Patient Discovery</h2>
          <p className="text-slate-500 mt-1 font-medium">Manage cases and initialize multimodal analysis.</p>
        </div>
        <button
          onClick={() => navigate("/patient-intake")}
          className="bg-medic-600 hover:bg-medic-700 text-white px-6 py-3 rounded-xl font-semibold flex items-center gap-2 transition-all shadow-lg shadow-medic-500/20 hover:shadow-medic-500/30 hover:-translate-y-0.5"
        >
          <Plus size={20} />
          New Patient
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {stats.map((stat, i) => (
          <div
            key={i}
            className="glass-card p-6 flex items-center gap-5 hover:border-medic-200 transition-colors cursor-default"
          >
            <div className={`w-14 h-14 rounded-2xl ${stat.bg} ${stat.color} flex items-center justify-center`}>
              <stat.icon size={28} />
            </div>
            <div>
              <div className="text-3xl font-bold text-slate-800">{stat.value}</div>
              <div className="text-sm text-slate-500 font-semibold uppercase tracking-wide">{stat.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Main Content */}
      <div className="space-y-4">
        {/* Toolbar */}
        <div className="flex flex-col md:flex-row gap-4 justify-between items-center bg-white/60 p-2 rounded-xl border border-white/60 shadow-sm backdrop-blur-sm">
          <div className="relative w-full md:w-96">
            <Search className="absolute left-4 top-3 text-slate-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search patients..."
              className="w-full pl-12 pr-4 py-2.5 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-medic-500/20 focus:border-medic-500 text-slate-800 placeholder-slate-400 font-medium transition-all"
            />
          </div>
          <button className="px-4 py-2.5 text-slate-600 hover:text-medic-600 hover:bg-medic-50/50 border border-transparent hover:border-medic-100 rounded-lg flex items-center gap-2 transition-colors font-medium">
            <Filter size={18} />
            <span>Filter View</span>
          </button>
        </div>

        {/* Table */}
        <div className="glass-card overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/50">
                <th className="px-6 py-5 font-bold text-slate-500 text-xs uppercase tracking-wider">Patient ID</th>
                <th className="px-6 py-5 font-bold text-slate-500 text-xs uppercase tracking-wider">Demographics</th>
                <th className="px-6 py-5 font-bold text-slate-500 text-xs uppercase tracking-wider">Status</th>
                <th className="px-6 py-5 font-bold text-slate-500 text-xs uppercase tracking-wider">Last Updated</th>
                <th className="px-6 py-5 text-right font-bold text-slate-500 text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan="5" className="p-12 text-center text-slate-400 font-medium">
                    Loading records...
                  </td>
                </tr>
              ) : (
                patients.map((patient) => {
                  const hasRevision = Number(patient.raw?.active_revision ?? 0) === 1;

                  return (
                    <tr key={patient.id} className="hover:bg-medic-50/30 transition-colors group">
                      <td className="px-6 py-4 font-mono font-semibold text-medic-600">
                        #{String(patient.id || "").toUpperCase()}
                      </td>

                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-500 font-bold text-xs">
                            {String(patient.name || "")
                              .split(" ")
                              .filter(Boolean)
                              .map((n) => n[0])
                              .join("")
                              .slice(0, 2)
                              .toUpperCase()}
                          </div>
                          <div>
                            <div className="font-bold text-slate-800">{patient.name}</div>
                            <div className="text-xs text-slate-500 font-medium">
                              {patient.age !== "" ? `${patient.age} years` : "Age N/A"} •{" "}
                              {patient.sex === "F" ? "Female" : patient.sex === "M" ? "Male" : "N/A"}
                            </div>
                          </div>
                        </div>
                      </td>

                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold border ${
                            patient.diagnosis === "Pending"
                              ? "bg-amber-50 text-amber-700 border-amber-200"
                              : "bg-emerald-50 text-emerald-700 border-emerald-200"
                          }`}
                        >
                          <div
                            className={`w-1.5 h-1.5 rounded-full mr-2 ${
                              patient.diagnosis === "Pending" ? "bg-amber-500" : "bg-emerald-500"
                            }`}
                          ></div>
                          {patient.diagnosis || "Analysis Required"}
                        </span>
                      </td>

                      <td className="px-6 py-4 text-slate-500 text-sm font-medium">{patient.last_updated || ""}</td>

                      {/* ✅ Actions (FIXED) */}
                      <td className="px-6 py-4 text-right">
                        {hasRevision ? (
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() =>
                                navigate("/results", {
                                  state: { patientId: patient.id, revision: 1 },
                                })
                              }
                              className="px-3 py-2 text-sm font-bold rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 transition-colors"
                            >
                              View Results
                            </button>

                            <button
                              onClick={() =>
                                navigate("/revision", {
                                  state: { patientId: patient.id, mode: "edit", revision: 1 },
                                })
                              }
                              className="px-3 py-2 text-sm font-bold rounded-lg border border-medic-200 bg-medic-50 hover:bg-medic-100 text-medic-700 transition-colors"
                            >
                              Update Data
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() =>
                              navigate("/revision", { state: { patientId: patient.id, mode: "create" } })
                            }
                            className="px-3 py-2 text-sm font-bold rounded-lg border border-medic-200 bg-medic-50 hover:bg-medic-100 text-medic-700 transition-colors"
                          >
                            Create Revision
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
