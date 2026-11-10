import { Navigate, Route, Routes } from "react-router-dom";
import { useMe } from "@/features/auth/useMe";
import { AppShellLayout } from "@/app/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { FinancePage } from "@/features/finance/FinancePage";
import { LoansPage } from "@/features/finance/LoansPage";
import { DebtsPage } from "@/features/finance/DebtsPage";
import { CarsPage } from "@/features/cars/CarsPage";
import { HealthPage } from "@/features/health/HealthPage";
import { Loading } from "@/components/Loading";

export function App() {
  const me = useMe();

  if (me.isLoading) return <Loading />;
  if (!me.data) {
    return (
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
        <Route path="/cars" element={<CarsPage />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/auth/*" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShellLayout>
  );
}
