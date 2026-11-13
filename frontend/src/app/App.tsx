import { useQuery } from "@tanstack/react-query";
import { Navigate, Route, Routes, useMatch } from "react-router-dom";
import { useMe } from "@/features/auth/useMe";
import { AppShellLayout } from "@/app/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { FinancePage } from "@/features/finance/FinancePage";
import { LoansPage } from "@/features/finance/LoansPage";
import { DebtsPage } from "@/features/finance/DebtsPage";
import { ChartsPage } from "@/features/finance/ChartsPage";
import { CategoriesPage } from "@/features/finance/CategoriesPage";
import { InvestmentsPage } from "@/features/investments/InvestmentsPage";
import { CarsPage } from "@/features/cars/CarsPage";
import { HealthChooserPage } from "@/features/health/HealthChooserPage";
import { HealthPersonPage } from "@/features/health/HealthPersonPage";
import { HouseholdPage } from "@/features/household/HouseholdPage";
import { NotesPage } from "@/features/notes/NotesPage";
import { AssistantPage } from "@/features/assistant/AssistantPage";
import { AISettingsPage } from "@/features/assistant/AISettingsPage";
import { PeoplePage } from "@/features/people/PeoplePage";
import { PersonPage } from "@/features/people/PersonPage";
import { CabinetPage } from "@/features/health/CabinetPage";
import { Loading } from "@/components/Loading";
import { AccountPage } from "@/features/settings/AccountPage";
import { setupApi } from "@/features/settings/api";
import { FamilyStep } from "@/features/settings/FamilyStep";
import { InvitePage } from "@/features/settings/InvitePage";
import { useSettingsHome } from "@/features/settings/parts";
import { RolesPage } from "@/features/settings/RolesPage";
import { SetupPage } from "@/features/settings/SetupPage";
import { UsersPage } from "@/features/settings/UsersPage";

export function App() {
  const me = useMe();
  // A fresh install (no account yet) opens first-time setup instead of login.
  const setup = useQuery({
    queryKey: ["setup"],
    queryFn: setupApi.status,
    enabled: me.isSuccess && !me.data,
    retry: false,
  });
  // A one-time link opens on its own, logged in or not.
  const invite = useMatch("/invite/:token");

  if (invite) {
    return (
      <Routes>
        <Route path="/invite/:token" element={<InvitePage />} />
      </Routes>
    );
  }
  if (me.isLoading || (!me.data && setup.isLoading)) return <Loading />;
  if (!me.data) {
    return setup.data?.needs_setup ? (
      <Routes>
        <Route path="/setup" element={<SetupPage />} />
        <Route path="*" element={<Navigate to="/setup" replace />} />
      </Routes>
    ) : (
      <Routes>
        <Route path="/auth/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/auth/login" replace />} />
      </Routes>
    );
  }

  return (
    <AppShellLayout>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/finance" element={<FinancePage />} />
        <Route path="/finance/loans" element={<LoansPage />} />
        <Route path="/finance/debts" element={<DebtsPage />} />
        <Route path="/finance/charts" element={<ChartsPage />} />
        <Route path="/finance/categories" element={<CategoriesPage />} />
        <Route path="/finance/investments" element={<InvestmentsPage />} />
        <Route path="/cars" element={<CarsPage />} />
        <Route path="/health" element={<HealthChooserPage />} />
        <Route path="/health/cabinet" element={<CabinetPage />} />
        <Route path="/health/:personId" element={<HealthPersonPage />} />
        <Route path="/household" element={<HouseholdPage />} />
        <Route path="/notes" element={<NotesPage />} />
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/settings" element={<SettingsHome />} />
        <Route path="/settings/users" element={<UsersPage />} />
        <Route path="/settings/roles" element={<RolesPage />} />
        <Route path="/settings/ai" element={<AISettingsPage />} />
        <Route path="/settings/account" element={<AccountPage />} />
        {/* Right after first-time setup: the family step. */}
        <Route path="/setup" element={<Navigate to="/setup/family" replace />} />
        <Route path="/setup/family" element={<FamilyStep />} />
        <Route path="/people" element={<PeoplePage />} />
        <Route path="/people/:personId" element={<PersonPage />} />
        <Route path="/auth/*" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShellLayout>
  );
}

/** "Settings" opens accounts for an admin, one's own account for others. */
function SettingsHome() {
  const home = useSettingsHome();
  return home ? <Navigate to={home} replace /> : <Loading />;
}
