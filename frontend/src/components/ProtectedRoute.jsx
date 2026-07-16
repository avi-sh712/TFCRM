import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth-context";
export default function ProtectedRoute({ role }) { const { user } = useAuth(); if (!user) return <Navigate to="/login" replace />; return role && user.role !== role ? <Navigate to="/dashboard" replace /> : <Outlet />; }
