import { Route, Routes } from "react-router-dom";
import CaseList from "./pages/CaseList";
import CaseDetail from "./pages/CaseDetail";

export default function App() {
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 16px", fontFamily: "system-ui, sans-serif" }}>
      <Routes>
        <Route path="/" element={<CaseList />} />
        <Route path="/cases/:id" element={<CaseDetail />} />
      </Routes>
    </div>
  );
}
