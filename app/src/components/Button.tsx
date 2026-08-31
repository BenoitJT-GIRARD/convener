import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'outline' | 'ghost';
type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant };

export function Button({ variant = 'primary', className = '', ...rest }: Props) {
  const base = 'inline-flex items-center gap-2 px-4 py-2 rounded-md font-medium text-sm transition-colors disabled:opacity-50';
  const styles = {
    primary: 'bg-dominant text-paper hover:bg-dominant-hover',
    outline: 'border border-border bg-surface hover:bg-paper',
    ghost: 'hover:bg-paper',
  }[variant];
  return <button className={`${base} ${styles} ${className}`} {...rest} />;
}
