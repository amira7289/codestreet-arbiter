import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import Dashboard from "./pages/Dashboard";
import CaseList from "./pages/CaseList";
import CaseDetail from "./pages/CaseDetail";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/cases" element={<CaseList />} />
        <Route path="/cases/:id" element={<CaseDetail />} />
      </Routes>
    </AppShell>
  );
}
