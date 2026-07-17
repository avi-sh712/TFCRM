import { createContext, useContext, useMemo, useState } from "react";
import { api } from "./api";

const Context = createContext(null);

function storeSession(result, setUser) {
  localStorage.setItem("talentforge_token", result.access_token);
  localStorage.setItem("talentforge_user", JSON.stringify(result.user));
  setUser(result.user);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem("talentforge_user") || "null"));
  const value = useMemo(() => ({
    user,
    async login(credentials) {
      const result = await api("/auth/login", { method: "POST", body: JSON.stringify(credentials) });
      storeSession(result, setUser);
    },
    async signup(account) {
      const result = await api("/auth/signup", { method: "POST", body: JSON.stringify(account) });
      storeSession(result, setUser);
    },
    async updateProfile(profile) {
      const result = await api("/auth/profile", { method: "PATCH", body: JSON.stringify(profile) });
      storeSession(result, setUser);
    },
    logout() {
      localStorage.removeItem("talentforge_token");
      localStorage.removeItem("talentforge_user");
      setUser(null);
    },
  }), [user]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export const useAuth = () => useContext(Context);
