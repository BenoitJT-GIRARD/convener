import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react';

type Props = {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  as?: 'input' | 'textarea';
} & Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value' | 'type'>
  & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange' | 'value'>;

export function Field({ label, value, onChange, type = 'text', as = 'input', ...rest }: Props) {
  const cls = 'mt-1 w-full px-3 py-2 border border-border rounded-md bg-surface text-sm';
  return (
    <label className="block mb-3">
      <span className="text-xs uppercase tracking-wider text-ink-muted">{label}</span>
      {as === 'textarea'
        ? <textarea className={cls} value={value} onChange={e => onChange(e.target.value)} rows={3} {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)} />
        : <input className={cls} type={type} value={value} onChange={e => onChange(e.target.value)} {...(rest as InputHTMLAttributes<HTMLInputElement>)} />
      }
    </label>
  );
}
