import { useQuery } from "@tanstack/react-query";

export type ModuleKey =
  | "finance"
  | "cars"
  | "health"
  | "household"
  | "calendar"
  | "notes"
  | "assistant"
  | "people"
  | "admin";

export type Level = "view" | "edit" | "manage";

export type Permissions = {
  modules: Record<ModuleKey, Record<Level, boolean>>;
  person_ids: string[];
  is_admin: boolean;
};

export function usePermissions() {
  const q = useQuery<Permissions>({
    queryKey: ["me", "permissions"],
    queryFn: async () => {
      const resp = await fetch("/api/me/permissions", { credentials: "include" });
      if (!resp.ok) throw new Error("permissions failed");
      return (await resp.json()) as Permissions;
    },
    staleTime: 60_000,
  });
  const data = q.data;

  return {
    data,
    isLoading: q.isLoading,
    canView: (m: ModuleKey) => data?.modules?.[m]?.view ?? false,
    canEdit: (m: ModuleKey) => data?.modules?.[m]?.edit ?? false,
    canManage: (m: ModuleKey) => data?.modules?.[m]?.manage ?? false,
  };
}
