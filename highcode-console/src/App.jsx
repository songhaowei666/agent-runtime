import { Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import ConsolePage from "./pages/ConsolePage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/console" element={<ConsolePage />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
