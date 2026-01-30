import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Activity, User, Mail, Lock, ArrowRight, ShieldCheck } from 'lucide-react';
import { register } from '../services/auth.service.js';

const Register = () => {
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);

    const handleRegister = async (e) => {
  e.preventDefault();
  setLoading(true);

  try {
    await register({
      first_name: "Jane",
      last_name: "Doe",
      email: "doctor@hospital.org",
      password: "password",
      license_id: "LIC-XXXX"
    });
    navigate("/dashboard");
  } catch (err) {
    console.error(err);
  } finally {
    setLoading(false);
  }
};


    return (
        <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
            {/* Ambient Background Elements */}
            <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-medic-200/40 rounded-full blur-[100px] animate-pulse"></div>
            <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-indigo-200/40 rounded-full blur-[100px] animate-pulse" style={{ animationDelay: '1s' }}></div>

            <div className="glass-card w-full max-w-lg p-10 relative z-10 animate-fade-in">
                <div className="text-center mb-8">
                    <div className="mx-auto w-16 h-16 bg-gradient-to-tr from-medic-500 to-indigo-500 rounded-2xl rotate-3 flex items-center justify-center mb-6 shadow-lg shadow-medic-500/20">
                        <Activity className="text-white w-8 h-8 -rotate-3" />
                    </div>
                    <h1 className="text-3xl font-display font-bold text-slate-800 mb-2">
                        Create Account
                    </h1>
                    <p className="text-slate-500 text-sm tracking-wide font-medium">Join the BioCUP Discovery Network</p>
                </div>

                <form onSubmit={handleRegister} className="space-y-5">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider">First Name</label>
                            <input
                                type="text"
                                className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl focus:border-medic-500 focus:ring-4 focus:ring-medic-500/10 text-slate-900 placeholder-slate-400 outline-none transition-all font-medium"
                                placeholder="Jane"
                                required
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider">Last Name</label>
                            <input
                                type="text"
                                className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl focus:border-medic-500 focus:ring-4 focus:ring-medic-500/10 text-slate-900 placeholder-slate-400 outline-none transition-all font-medium"
                                placeholder="Doe"
                                required
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider">Medical License ID</label>
                        <div className="relative group">
                            <ShieldCheck className="absolute left-4 top-3.5 text-slate-400 w-5 h-5 group-focus-within:text-medic-500 transition-colors" />
                            <input
                                type="text"
                                className="w-full pl-12 pr-4 py-3 bg-white border border-slate-200 rounded-xl focus:border-medic-500 focus:ring-4 focus:ring-medic-500/10 text-slate-900 placeholder-slate-400 outline-none transition-all font-medium"
                                placeholder="LIC-XXXX-YYYY"
                                required
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider">Email Address</label>
                        <div className="relative group">
                            <Mail className="absolute left-4 top-3.5 text-slate-400 w-5 h-5 group-focus-within:text-medic-500 transition-colors" />
                            <input
                                type="email"
                                className="w-full pl-12 pr-4 py-3 bg-white border border-slate-200 rounded-xl focus:border-medic-500 focus:ring-4 focus:ring-medic-500/10 text-slate-900 placeholder-slate-400 outline-none transition-all font-medium"
                                placeholder="doctor@hospital.org"
                                required
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider">Password</label>
                        <div className="relative group">
                            <Lock className="absolute left-4 top-3.5 text-slate-400 w-5 h-5 group-focus-within:text-medic-500 transition-colors" />
                            <input
                                type="password"
                                className="w-full pl-12 pr-4 py-3 bg-white border border-slate-200 rounded-xl focus:border-medic-500 focus:ring-4 focus:ring-medic-500/10 text-slate-900 placeholder-slate-400 outline-none transition-all font-medium"
                                placeholder="••••••••"
                                required
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-medic-600 hover:bg-medic-700 text-white font-semibold py-4 rounded-xl shadow-lg shadow-medic-500/20 flex items-center justify-center gap-2 transition-all transform active:scale-[0.98] group mt-4"
                    >
                        {loading ? (
                            <span className="animate-pulse">Validating Credentials...</span>
                        ) : (
                            <>
                                Register Account <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                            </>
                        )}
                    </button>
                </form>

                <div className="mt-8 text-center border-t border-slate-200 pt-6">
                    <p className="text-sm text-slate-500">
                        Already have an account?{' '}
                        <Link to="/login" className="text-medic-600 font-bold hover:text-medic-700 transition-colors">
                            Sign In
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
};

export default Register;
