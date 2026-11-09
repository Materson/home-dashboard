import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Group,
  NumberInput,
  Paper,
  ScrollArea,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useMutation, useQuery } from "@tanstack/react-query";

import { financeApi, type Loan, type OverpaymentComparison, type Schedule } from "./api";

export function LoansPage() {
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
      <Title order={2}>Loans</Title>

      {!loans.data?.length && (
        <Alert color="gray">
          No loans yet. Create one in the Django admin (<Text component="span" ff="monospace">/admin/finance/loan/</Text>)
          — the API form will arrive in M8.
        </Alert>
      )}

      {!!loans.data?.length && (
        <Group>
          <Select
            label="Loan"
            data={loans.data.map((l: Loan) => ({ value: l.id, label: `${l.name} — ${l.principal} ${l.currency}` }))}
            value={loanId}
            onChange={setSelected}
            w={380}
          />
        </Group>
      )}

      {schedule.data && loanId && (
        <>
          <ScheduleTable schedule={schedule.data} title="Current schedule" />
          <OverpaymentSimulator loanId={loanId} currency={schedule.data.rows[0]?.nominal_rate_p_a ? "PLN" : "PLN"} />
        </>
      )}
    </Stack>
  );
}

function ScheduleTable({ schedule, title }: { schedule: Schedule; title: string }) {
  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <Title order={5}>{title}</Title>
        <Group gap="xs">
          <Badge color="gray">Months: {schedule.months}</Badge>
          <Badge color="gray">Total interest: {schedule.total_interest}</Badge>
          <Badge color="gray">Total paid: {schedule.total_installments}</Badge>
        </Group>
      </Group>
      <ScrollArea h={320}>
        <Table striped highlightOnHover stickyHeader>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>Due</Table.Th>
              <Table.Th ta="right">Opening</Table.Th>
              <Table.Th ta="right">Installment</Table.Th>
              <Table.Th ta="right">Principal</Table.Th>
              <Table.Th ta="right">Interest</Table.Th>
              <Table.Th ta="right">Overpay</Table.Th>
              <Table.Th ta="right">Closing</Table.Th>
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

function OverpaymentSimulator({ loanId }: { loanId: string; currency: string }) {
  const [date, setDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [amount, setAmount] = useState<number>(10000);
  const [mode, setMode] = useState<"shorten_term" | "reduce_installment">("shorten_term");
  const [result, setResult] = useState<OverpaymentComparison | null>(null);

  const simulate = useMutation({
    mutationFn: () => financeApi.simulate(loanId, { date, amount: String(amount), mode }),
    onSuccess: setResult,
  });

  return (
    <Stack gap="md">
      <Paper withBorder p="md">
        <Title order={5} mb="sm">
          Overpayment simulator
        </Title>
        <Group align="flex-end">
          <DatePickerInput
            label="Date"
            value={new Date(date)}
            onChange={(d) => setDate((d ?? new Date()).toISOString().slice(0, 10))}
          />
          <NumberInput
            label="Amount"
            decimalScale={2}
            fixedDecimalScale
            value={amount}
            onChange={(v) => setAmount(Number(v ?? 0))}
            min={0}
          />
          <Select
            label="Mode"
            data={[
              { value: "shorten_term", label: "Shorten term" },
              { value: "reduce_installment", label: "Reduce installment" },
            ]}
            value={mode}
            onChange={(v) => setMode((v as typeof mode) ?? "shorten_term")}
          />
          <Button loading={simulate.isPending} onClick={() => simulate.mutate()}>
            Simulate
          </Button>
        </Group>
        {result && (
          <Group mt="md" gap="md">
            <Badge color="green" size="lg">
              Interest saved: {result.saved_interest}
            </Badge>
            <Badge color="green" size="lg">
              Months saved: {result.months_saved}
            </Badge>
          </Group>
        )}
      </Paper>

      {result && (
        <Group grow align="flex-start">
          <ScheduleTable schedule={result.base} title="Without overpayment" />
          <ScheduleTable schedule={result.with_overpayment} title="With overpayment" />
        </Group>
      )}
    </Stack>
  );
}
