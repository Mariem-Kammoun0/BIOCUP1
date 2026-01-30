import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, Lock, User, ArrowRight } from 'lucide-react';
import { login } from '../services/auth.service.js';

const Login = () => {
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);

    // 🔐 Champs contrôlés
    const [email, setEmail] = useState("admin@hospital.org");
    const [password, setPassword] = useState("password");

    const handleLogin = async (e) => {
        e.preventDefault();
        setLoading(true);

        try {
            await login({ email, password });
            navigate("/dashboard");
        } catch (err) {
            console.error("Login error:", err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
            {/* Ambient Background Elements */}
            <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-medic-200/40 rounded-full blur-[100px] animate-pulse"></div>
            <div
                className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-indigo-200/40 rounded-full blur-[100px] animate-pulse"
                style={{ animationDelay: '1s' }}
            ></div>

            <div className="glass-card w-full max-w-md p-10 relative z-10 animate-fade-in">
                <div className="text-center mb-10">
                    <div className="mx-auto w-20 h-20 bg-gradient-to-tr from-medic-500 to-indigo-500 rounded-2xl rotate-3 flex items-center justify-center mb-6 shadow-lg shadow-medic-500/20">
                        <Activity className="text-white w-10 h-10 -rotate-3" />
                    </div>
                    <h1 className="text-4xl font-display font-bold text-slate-800 mb-2">
                        BioCUP
                    </h1>
                    <p className="text-slate-500 text-sm tracking-wide uppercase font-medium">
                        Discovery Intelligence Portal
                    </p>
                </div>

                <form onSubmit={handleLogin} className="space-y-6">
                    {/* Email */}
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider">
                            Email
                        </label>
                        <div className="relative group">
                            <User className="absolute left-4 top-3.5 text-slate-400 w-5 h-5 group-focus-within:text-medic-500 transition-colors" />
                            <input
                                type="email"
                                className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:border-medic-500 focus:ring-4 focus:ring-medic-500/10 text-slate-900 placeholder-slate-400 outline-none transition-all font-medium"
                                placeholder="doctor@hospital.org"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                            />
                        </div>
                    </div>

                    {/* Password */}
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider">
                            Password
                        </label>
                        <div className="relative group">
                            <Lock className="absolute left-4 top-3.5 text-slate-400 w-5 h-5 group-focus-within:text-medic-500 transition-colors" />
                            <input
                                type="password"
                                className="w-full pl-12 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:border-medic-500 focus:ring-4 focus:ring-medic-500/10 text-slate-900 placeholder-slate-400 outline-none transition-all font-medium"
                                placeholder="••••••••"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-medic-600 hover:bg-medic-700 text-white font-semibold py-4 rounded-xl shadow-lg shadow-medic-500/20 flex items-center justify-center gap-2 transition-all transform active:scale-[0.98] group"
                    >
                        {loading ? (
                            <span className="animate-pulse">Authenticating...</span>
                        ) : (
                            <>
                                Secure Access
                                <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                            </>
                        )}
                    </button>
                </form>

                <div className="mt-8 text-center border-t border-slate-200 pt-6">
                    <p className="text-sm text-slate-500 mb-2">
                        Don't have an account?{' '}
                        <span
                            onClick={() => navigate('/register')}
                            className="text-medic-600 font-bold hover:text-medic-700 transition-colors cursor-pointer"
                        >
                            Create Registration
                        </span>
                    </p>
                    <p className="text-xs text-slate-400 font-medium">
                        System v2.4.0 • Authorized Personnel Only
                    </p>
                </div>
            </div>
        </div>
    );
};

export default Login;
