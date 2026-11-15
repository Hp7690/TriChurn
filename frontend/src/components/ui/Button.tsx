import type { ButtonHTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: 'md' | 'sm';
}

/** Thin wrapper over the `.btn` classes in index.css, which pages without this component also use directly. */
export function Button({ variant = 'primary', size = 'md', type = 'button', className, ...rest }: ButtonProps) {
  return <button type={type} className={cn('btn', `btn-${variant}`, size === 'sm' && 'btn-sm', className)} {...rest} />;
}
