import React, { useState } from 'react';
import { Activity, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { createPatient } from "../services/patients.service";

const PatientIntake = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const [fullName, setFullName] = useState("");
  const [dob, setDob] = useState(""); // YYYY-MM-DD
  const [sex, setSex] = useState("F");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const payload = {
        full_name: fullName,
        dob: dob || null,
        sex: sex || null,
        phone: phone || null,
        notes: notes || null,
      };

      await createPatient(payload);
      navigate("/dashboard");
    } catch (err) {
      console.error("Create patient error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-slide-up">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-display font-bold text-slate-800">Add Patient</h2>
          <p className="text-slate-500 mt-1 font-medium">Create a patient record (revisions are added separately).</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="glass-panel p-6 rounded-2xl relative overflow-hidden group border-l-4 border-l-medic-500">
          <h3 className="font-bold text-slate-700 flex items-center gap-2 mb-6 text-lg">
            <Activity size={20} className="text-medic-500" /> Patient Information
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Full Name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full p-3 bg-white border border-slate-200 rounded-xl focus:ring-4 focus:ring-medic-500/10 focus:border-medic-500 outline-none text-slate-800 placeholder-slate-400 font-medium transition-all"
                placeholder="e.g. Leila Mansour"
                required
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Date of Birth</label>
              <input
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                className="w-full p-3 bg-white border border-slate-200 rounded-xl focus:ring-4 focus:ring-medic-500/10 focus:border-medic-500 outline-none text-slate-800 placeholder-slate-400 font-medium transition-all"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Sex</label>
              <select
                value={sex}
                onChange={(e) => setSex(e.target.value)}
                className="w-full p-3 bg-white border border-slate-200 rounded-xl focus:ring-4 focus:ring-medic-500/10 focus:border-medic-500 outline-none text-slate-800 font-medium transition-all"
              >
                <option value="F">Female</option>
                <option value="M">Male</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Phone</label>
              <input
                type="text"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full p-3 bg-white border border-slate-200 rounded-xl focus:ring-4 focus:ring-medic-500/10 focus:border-medic-500 outline-none text-slate-800 placeholder-slate-400 font-medium transition-all"
                placeholder="+216..."
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Notes</label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full p-3 bg-white border border-slate-200 rounded-xl focus:ring-4 focus:ring-medic-500/10 focus:border-medic-500 outline-none text-slate-800 placeholder-slate-400 font-medium transition-all"
                placeholder="Optional clinical notes"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end pt-4 pb-10">
          <button
            type="submit"
            disabled={loading}
            className="bg-gradient-to-r from-medic-600 to-indigo-600 hover:from-medic-700 hover:to-indigo-700 text-white px-10 py-4 rounded-xl font-bold shadow-xl shadow-medic-500/20 flex items-center gap-3 transition-all transform active:scale-[0.98] group"
          >
            {loading ? (
              <>
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                Saving...
              </>
            ) : (
              <>
                Create Patient <ArrowRight size={20} className="group-hover:translate-x-1 transition-transform" />
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default PatientIntake;
