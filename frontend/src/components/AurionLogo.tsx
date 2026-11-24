import { cn } from '../lib/utils'

export function AurionLogo({ className }: { className?: string }) {
  return (
    <img src="/favicon.svg" alt="Aurion" width={40} height={40} className={cn('aurion-mark shrink-0', className)} />
  )
}
