import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthBootstrap } from '../auth/AuthBootstrap';
import { AppShell } from '../components/AppShell';
import { ProtectedRoute } from '../components/ProtectedRoute';
// Crop cycle screens (issue #45).
import { CropCyclesPage } from '../pages/CropCyclesPage';
import { CropsPage } from '../pages/CropsPage';
import { ConversionsPage } from '../pages/ConversionsPage';
import { DashboardPage } from '../pages/DashboardPage';
import { FarmPage } from '../pages/FarmPage';
import { FieldsPage } from '../pages/FieldsPage';
import { LoginPage } from '../pages/LoginPage';
import { RegisterPage } from '../pages/RegisterPage';
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
            {/* Crop cycle screens (issue #45). */}
            <Route path="/cycles" element={<CropCyclesPage />} />
          </Route>
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthBootstrap>
  );
}
