import React, { createContext, useContext, useState, useEffect } from 'react';
import type { UserRole } from '../types';

interface AuthContextType {
  role: UserRole;
  setRole: (role: UserRole) => void;
  roleLabel: string;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const ROLE_LABELS: Record<UserRole, string> = {
  manager: 'Store Manager',
  camera: 'Live Camera Vision',
  staff: 'Floor Staff',
  owner: 'Executive / Owner',
  queue: 'Queue Intelligence',
  inventory: 'Shelf Inventory',
  calibration: 'Camera Calibration',
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [role, setRoleState] = useState<UserRole>(() => {
    const saved = localStorage.getItem('intellisales_role') as UserRole;
    return saved || 'manager';
  });

  const setRole = (newRole: UserRole) => {
    setRoleState(newRole);
    localStorage.setItem('intellisales_role', newRole);
  };

  useEffect(() => {
    localStorage.setItem('intellisales_role', role);
  }, [role]);

  return (
    <AuthContext.Provider value={{ role, setRole, roleLabel: ROLE_LABELS[role] }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};
