import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthBootstrap } from '../auth/AuthBootstrap';
import { AppShell } from '../components/AppShell';
import { ProtectedRoute } from '../components/ProtectedRoute';
import { ActivitiesPage } from '../pages/ActivitiesPage';
import { ActivityTemplatesPage } from '../pages/ActivityTemplatesPage';
import { ChatPage } from '../pages/ChatPage';
// Crop cycle screens (issue #45).
import { CropCyclesPage } from '../pages/CropCyclesPage';
import { CropsPage } from '../pages/CropsPage';
import { ExpensesPage } from '../pages/ExpensesPage';
import { PaymentsPage } from '../pages/PaymentsPage';
import { ConversionsPage } from '../pages/ConversionsPage';
import { DashboardPage } from '../pages/DashboardPage';
import { FarmPage } from '../pages/FarmPage';
import { GuidedSetupPage } from '../pages/GuidedSetupPage';
import { FieldsPage } from '../pages/FieldsPage';
import { HarvestsPage } from '../pages/HarvestsPage';
import { InventoryPage } from '../pages/InventoryPage';
import { ImportWizardPage } from '../pages/ImportWizardPage';
import { LoginPage } from '../pages/LoginPage';
import { RegisterPage } from '../pages/RegisterPage';
import { ReportsPage } from '../pages/ReportsPage';
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
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/farm" element={<FarmPage />} />
            <Route path="/setup" element={<GuidedSetupPage />} />
            <Route path="/fields" element={<FieldsPage />} />
            <Route path="/crops" element={<CropsPage />} />
            <Route path="/varieties" element={<VarietiesPage />} />
            <Route path="/units" element={<UnitsPage />} />
            <Route path="/expenses" element={<ExpensesPage />} />
            <Route path="/payments" element={<PaymentsPage />} />
            <Route path="/conversions" element={<ConversionsPage />} />
            <Route path="/harvests" element={<HarvestsPage />} />
            <Route path="/sales" element={<SalesPage />} />
            <Route path="/inventory" element={<InventoryPage />} />
            <Route path="/imports" element={<ImportWizardPage />} />
            {/* Activity planning screens (issue #46). */}
            <Route path="/activities" element={<ActivitiesPage />} />
            <Route
              path="/activity-templates"
              element={<ActivityTemplatesPage />}
            />
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
