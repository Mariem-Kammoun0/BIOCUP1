import React from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { LayoutDashboard, FilePlus, LogOut, Activity } from 'lucide-react';

const Layout = () => {
    const location = useLocation();
    const navigate = useNavigate();

    const isActive = (path) => location.pathname.includes(path);


    return (
        <div className="flex h-screen text-slate-800 overflow-hidden">

            {/* Sidebar */}
            <aside className="w-64 flex flex-col glass-card rounded-none h-full z-20 border-r border-white/60 bg-white/80">
                <div className="p-6 border-b border-slate-100">
                    <h1 className="text-2xl font-display font-bold flex items-center gap-2 text-slate-800">
                        <Activity className="text-medic-500" />
                        BioCUP
                    </h1>
                    <p className="text-xs text-slate-500 mt-1 uppercase tracking-wider font-semibold">Discovery Intelligence</p>
                </div>

                <nav className="flex-1 p-4 space-y-2">
                    <Link
                        to="/dashboard"
                        className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all font-semibold ${isActive('dashboard') ? 'bg-medic-50 text-medic-700 shadow-sm border border-medic-100' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'}`}
                    >
                        <LayoutDashboard size={20} />
                        Dashboard
                    </Link>
                    <Link
                        to="/intake"
                        className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all font-semibold ${isActive('intake') ? 'bg-medic-50 text-medic-700 shadow-sm border border-medic-100' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'}`}
                    >
                        <FilePlus size={20} />
                        New Analysis
                    </Link>
                </nav>

                <div className="p-4 border-t border-slate-100 bg-slate-50/50">
                    <div
                        onClick={() => navigate('/login')}
                        className="flex items-center gap-3 px-4 py-3 text-slate-500 hover:text-slate-800 cursor-pointer transition-colors font-medium"
                    >
                        <LogOut size={20} />
                        <span>Sign Out</span>
                    </div>
                    <div className="mt-4 px-4 text-xs text-slate-400 font-mono font-medium">
                        Dr. Sarah Conner<br />
                        Oncology Dept.
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 overflow-auto relative">
                {/* Header */}
                <header className="px-8 py-5 sticky top-0 z-30 flex justify-between items-center backdrop-blur-xl bg-white/80 border-b border-white/60 shadow-sm">
                    <h2 className="text-xl font-bold text-slate-800 tracking-tight">
                        {isActive('dashboard') && 'Patient Dashboard'}
                        {isActive('intake') && 'Case Ingestion'}
                        {isActive('results') && 'Analysis Results'}
                    </h2>
                    <div className="flex items-center gap-4">
                        <div className="text-right hidden md:block">
                            <div className="text-sm font-bold text-slate-800">Dr. Conner</div>
                            <div className="text-xs text-slate-500 font-medium h-4">Chief Oncologist</div>
                        </div>
                        <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-medic-500 to-indigo-500 flex items-center justify-center text-white font-bold shadow-md shadow-medic-500/20 border-2 border-white">
                            SC
                        </div>
                    </div>
                </header>

                <div className="p-8 max-w-7xl mx-auto pb-20">
                    <Outlet />
                </div>
            </main>
        </div>
    );
};

export default Layout;
