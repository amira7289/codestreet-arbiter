import { Route, Routes } from "react-router-dom";
import CaseList from "./pages/CaseList";
import CaseDetail from "./pages/CaseDetail";

export default function App() {
  return (
    // Widened from 900 so the two party panels have room to sit side by side on a
    // laptop; below that width .split-view stacks them.
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 16px", fontFamily: "system-ui, sans-serif" }}>
      <Routes>
        <Route path="/" element={<CaseList />} />
        <Route path="/cases/:id" element={<CaseDetail />} />
      </Routes>
    </div>
  );
}
