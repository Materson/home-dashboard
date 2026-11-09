import { useQuery } from "@tanstack/react-query";

export type Me = {
  id: number;
  email: string;
  locale: string;
  first_name: string;
  last_name: string;
};

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      const resp = await fetch("/api/me/", { credentials: "include" });
      if (resp.status === 401 || resp.status === 403) return null;
      if (!resp.ok) throw new Error("me failed");
      return (await resp.json()) as Me;
    },
    retry: false,
    staleTime: 60_000,
  });
}
