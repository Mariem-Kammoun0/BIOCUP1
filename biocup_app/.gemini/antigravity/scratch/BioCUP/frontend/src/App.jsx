import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import PatientIntake from "./pages/PatientIntake.jsx";
import Results from "./pages/Results.jsx";
import RevisionForm from "./pages/RevisionForm.jsx";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Default route */}
        <Route path="/" element={<Navigate to="/login" replace />} />

        {/* Auth */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Core pages */}
        <Route path="/dashboard" element={<Dashboard />} />

        {/* Create patient ONLY */}
        <Route path="/patient-intake" element={<PatientIntake />} />

        {/* Create / Update revision */}
        {/* 
          state expected:
          - patientId
          - mode: "create" | "edit"
          - revision (only for edit)
        */}
        <Route path="/revision" element={<RevisionForm />} />

        {/* Results */}
        {/* 
          state expected:
          - patientId
          - revision
        */}
        <Route path="/results" element={<Results />} />

        {/* 404 */}
        <Route path="*" element={<h1>404 - Page not found</h1>} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
