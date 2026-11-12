/** Files of one test result, in a window (see components/Attachments). */
import { Modal } from "@mantine/core";

import { Attachments } from "@/components/Attachments";

export function ResultFiles(props: {
  resultId: string | null;
  title: string;
  canEdit: boolean;
  onClose: () => void;
  /** Called after files change so the table's file count refreshes. */
  onChanged: () => void;
}) {
  return (
    <Modal opened={!!props.resultId} onClose={props.onClose} title={props.title} size="lg">
      {props.resultId && (
        <Attachments
          subjectType="health.testresult"
          subjectId={props.resultId}
          canEdit={props.canEdit}
          onChanged={props.onChanged}
        />
      )}
    </Modal>
  );
}
