import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthBootstrap } from '../auth/AuthBootstrap';
import { AppShell } from '../components/AppShell';
import { ProtectedRoute } from '../components/ProtectedRoute';
import { CropsPage } from '../pages/CropsPage';
import { ConversionsPage } from '../pages/ConversionsPage';
import { DashboardPage } from '../pages/DashboardPage';
import { FarmPage } from '../pages/FarmPage';
import { FieldsPage } from '../pages/FieldsPage';
import { HarvestsPage } from '../pages/HarvestsPage';
import { LoginPage } from '../pages/LoginPage';
import { RegisterPage } from '../pages/RegisterPage';
import { SalesPage } from '../pages/SalesPage';
import { UnitsPage } from '../pages/UnitsPage';
import { VarietiesPage } from '../pages/VarietiesPage';

export function AppRoutes() {
  return (
    <AuthBootstrap>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/farm" element={<FarmPage />} />
            <Route path="/fields" element={<FieldsPage />} />
            <Route path="/crops" element={<CropsPage />} />
            <Route path="/varieties" element={<VarietiesPage />} />
            <Route path="/units" element={<UnitsPage />} />
            <Route path="/conversions" element={<ConversionsPage />} />
            <Route path="/harvests" element={<HarvestsPage />} />
            <Route path="/sales" element={<SalesPage />} />
          </Route>
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthBootstrap>
  );
}
