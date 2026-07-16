import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./lib/auth-context";
import ProtectedRoute from "./components/ProtectedRoute";
import Shell from "./components/Shell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Customers from "./pages/Customers";
import Deals from "./pages/Deals";
import AgentRuns from "./pages/AgentRuns";
import Campaigns from "./pages/Campaigns";
import Integrations from "./pages/Integrations";
import Admin from "./pages/Admin";
import Settings from "./pages/Settings";
import AppErrorBoundary from "./components/AppErrorBoundary";

const page = (Page) => <Shell><AppErrorBoundary resetKey={Page.name}><Page /></AppErrorBoundary></Shell>;
export default function App() { return <BrowserRouter><AuthProvider><Routes><Route path="/login" element={<Login />} /><Route element={<ProtectedRoute />}><Route path="/dashboard" element={page(Dashboard)} /><Route path="/customers" element={page(Customers)} /><Route path="/deals" element={page(Deals)} /><Route path="/agent-runs" element={page(AgentRuns)} /><Route path="/campaigns" element={page(Campaigns)} /><Route path="/integrations" element={page(Integrations)} /><Route path="/settings" element={page(Settings)} /><Route element={<ProtectedRoute role="admin" />}><Route path="/admin" element={page(Admin)} /></Route></Route><Route path="*" element={<Navigate to="/dashboard" replace />} /></Routes></AuthProvider></BrowserRouter>; }
