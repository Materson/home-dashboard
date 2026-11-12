import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Group,
  Paper,
  ScrollArea,
  Select,
  Stack,
  Table,
  Title,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useMutation, useQuery } from "@tanstack/react-query";
import { isoDate, parseIsoDate } from "@/lib/format";
import { useTranslation } from "react-i18next";
import { AmountInput, isPositiveAmount } from "@/components/AmountInput";

import { financeApi, type Loan, type OverpaymentComparison, type Schedule } from "./api";

export function LoansPage() {
  const { t } = useTranslation();
  const loans = useQuery({ queryKey: ["finance", "loans"], queryFn: () => financeApi.listLoans() });
  const [selected, setSelected] = useState<string | null>(null);

  const loanId = selected ?? loans.data?.[0]?.id ?? null;
  const schedule = useQuery({
    queryKey: ["finance", "loans", loanId, "schedule"],
    queryFn: () => financeApi.schedule(loanId!),
    enabled: !!loanId,
  });

  return (
    <Stack gap="lg">
      <Title order={2}>{t("loans.title")}</Title>

      {loans.isSuccess && !loans.data.length && <Alert color="gray">{t("loans.empty")}</Alert>}

      {!!loans.data?.length && (
        <Group>
          <Select
            label={t("loans.loan")}
            data={loans.data.map((l: Loan) => ({
              value: l.id,
              label: `${l.name} — ${l.principal} ${l.currency}`,
            }))}
            value={loanId}
            onChange={setSelected}
            w={380}
          />
        </Group>
      )}

      {schedule.data && loanId && (
        <>
          <ScheduleTable schedule={schedule.data} title={t("loans.current")} />
          <OverpaymentSimulator loanId={loanId} />
        </>
      )}
    </Stack>
  );
}

function ScheduleTable({ schedule, title }: { schedule: Schedule; title: string }) {
  const { t } = useTranslation();
  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <Title order={5}>{title}</Title>
        <Group gap="xs">
          <Badge color="gray">{t("loans.months", { value: schedule.months })}</Badge>
          <Badge color="gray">{t("loans.totalInterest", { value: schedule.total_interest })}</Badge>
          <Badge color="gray">{t("loans.totalPaid", { value: schedule.total_installments })}</Badge>
        </Group>
      </Group>
      <ScrollArea h={320}>
        <Table striped highlightOnHover stickyHeader>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>{t("loans.col.due")}</Table.Th>
              <Table.Th ta="right">{t("loans.col.opening")}</Table.Th>
              <Table.Th ta="right">{t("loans.col.installment")}</Table.Th>
              <Table.Th ta="right">{t("loans.col.principal")}</Table.Th>
              <Table.Th ta="right">{t("loans.col.interest")}</Table.Th>
              <Table.Th ta="right">{t("loans.col.overpay")}</Table.Th>
              <Table.Th ta="right">{t("loans.col.closing")}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {schedule.rows.map((r) => (
              <Table.Tr key={r.index}>
                <Table.Td>{r.index}</Table.Td>
                <Table.Td>{r.due_date}</Table.Td>
                <Table.Td ta="right">{r.opening_balance}</Table.Td>
                <Table.Td ta="right">{r.installment}</Table.Td>
                <Table.Td ta="right">{r.principal_part}</Table.Td>
                <Table.Td ta="right">{r.interest_part}</Table.Td>
                <Table.Td ta="right">{r.overpayment}</Table.Td>
                <Table.Td ta="right">{r.closing_balance}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Paper>
  );
}

function OverpaymentSimulator({ loanId }: { loanId: string }) {
  const { t } = useTranslation();
  const [date, setDate] = useState<string>(isoDate(new Date()));
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<"shorten_term" | "reduce_installment">("shorten_term");
  const [result, setResult] = useState<OverpaymentComparison | null>(null);

  const simulate = useMutation({
    mutationFn: () => financeApi.simulate(loanId, { date, amount, mode }),
    onSuccess: setResult,
  });

  return (
    <Stack gap="md">
      <Paper withBorder p="md">
        <Title order={5} mb="sm">
          {t("loans.sim.title")}
        </Title>
        <Group align="flex-end">
          <DatePickerInput
            label={t("finance.field.date")}
            value={parseIsoDate(date)}
            onChange={(d) => setDate(isoDate(d ?? new Date()))}
          />
          <AmountInput label={t("finance.field.amount")} value={amount} onChange={setAmount} />
          <Select
            label={t("loans.sim.mode")}
            data={[
              { value: "shorten_term", label: t("loans.sim.shortenTerm") },
              { value: "reduce_installment", label: t("loans.sim.reduceInstallment") },
            ]}
            value={mode}
            onChange={(v) => setMode((v as typeof mode) ?? "shorten_term")}
          />
          <Button
            loading={simulate.isPending}
            disabled={!isPositiveAmount(amount)}
            onClick={() => simulate.mutate()}
          >
            {t("loans.sim.run")}
          </Button>
        </Group>
        {result && (
          <Group mt="md" gap="md">
            <Badge color="green" size="lg">
              {t("loans.sim.savedInterest", { value: result.saved_interest })}
            </Badge>
            <Badge color="green" size="lg">
              {t("loans.sim.savedMonths", { value: result.months_saved })}
            </Badge>
          </Group>
        )}
      </Paper>

      {result && (
        <Group grow align="flex-start">
          <ScheduleTable schedule={result.base} title={t("loans.sim.without")} />
          <ScheduleTable schedule={result.with_overpayment} title={t("loans.sim.with")} />
        </Group>
      )}
    </Stack>
  );
}
