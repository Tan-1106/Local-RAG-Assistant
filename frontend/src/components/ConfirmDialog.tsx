interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Xác nhận',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onCancel}>
      <section
        className="glass-panel dialog-panel"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
        onMouseDown={event => event.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="text-lg font-bold">{title}</h2>
        <p id="confirm-dialog-message" className="text-sm text-muted">{message}</p>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>Hủy</button>
          <button type="button" className="btn btn-primary" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </section>
    </div>
  );
}
