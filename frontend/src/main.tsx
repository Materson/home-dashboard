import React from "react";
import ReactDOM from "react-dom/client";
import { MantineProvider, createTheme } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { Notifications } from "@mantine/notifications";
import { useTranslation } from "react-i18next";
import "dayjs/locale/pl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/charts/styles.css";

import "@/i18n";
import { App } from "@/app/App";

const theme = createTheme({ primaryColor: "indigo", defaultRadius: "md" });
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

// Date pickers follow the UI language (month/day names, Monday-first weeks).
function LocalizedDates({ children }: { children: React.ReactNode }) {
  const { i18n } = useTranslation();
  const locale = i18n.language.startsWith("pl") ? "pl" : "en";
  return (
    <DatesProvider settings={{ locale, firstDayOfWeek: 1 }}>{children}</DatesProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <LocalizedDates>
        <Notifications position="top-right" />
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </LocalizedDates>
    </MantineProvider>
  </React.StrictMode>,
);
