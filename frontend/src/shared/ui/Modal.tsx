import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { Button } from './ui';

const FOCAVEIS = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  subtitle?: ReactNode;
}

/** Diálogo acessível: foco preso dentro, Esc fecha, foco volta ao elemento que abriu, rolagem do fundo travada. */
export default function Modal({ title, onClose, children, footer, wide, subtitle }: ModalProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    const anterior = document.activeElement as HTMLElement | null;
    const raiz = ref.current;
    const inicial = raiz?.querySelector<HTMLElement>('[data-autofocus]')
      ?? raiz?.querySelector<HTMLElement>(`.modal-body ${FOCAVEIS.split(',').join(', .modal-body ')}`)
      ?? raiz?.querySelector<HTMLElement>(FOCAVEIS);
    inicial?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose(); return; }
      if (e.key !== 'Tab' || !raiz) return;
      const itens = Array.from(raiz.querySelectorAll<HTMLElement>(FOCAVEIS));
      if (itens.length === 0) return;
      const primeiro = itens[0];
      const ultimo = itens[itens.length - 1];
      if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus(); }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      anterior?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} className={`modal${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="modal-head">
          <div>
            <div className="modal-title" id={titleId}>{title}</div>
            {subtitle && <div className="page-sub">{subtitle}</div>}
          </div>
          <Button variant="ghost" icon="x" aria-label="Fechar" onClick={onClose} />
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

interface ConfirmProps {
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ title, message, confirmLabel = 'Confirmar', danger, loading, onConfirm, onCancel }: ConfirmProps) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>Cancelar</Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} loading={loading} data-autofocus>{confirmLabel}</Button>
        </>
      }
    >
      <div>{message}</div>
    </Modal>
  );
}
