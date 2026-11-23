import { useId } from 'react'

/** Cores do gradiente da marca em hexadecimal, para o SVG (o mesmo do favicon e do logo.svg). */
const BRAND_STOPS = ['#4A74C9', '#8C5DC0', '#D9637A']

/**
 * Símbolo da marca: um pino de localização com o check dentro.
 * O lugar do turno e o pagamento garantido, as duas promessas do Conecta Já.
 */
export function LogoMark({ className = 'size-7', title }: { className?: string; title?: string }) {
  const gradientId = useId()
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          {BRAND_STOPS.map((color, index) => (
            <stop key={color} offset={index / (BRAND_STOPS.length - 1)} stopColor={color} />
          ))}
        </linearGradient>
      </defs>
      <path
        d="M32 2C47.5 2 58 13.2 58 27.4 58 45 32 62 32 62S6 45 6 27.4C6 13.2 16.5 2 32 2Z"
        fill={`url(#${gradientId})`}
      />
      <path
        d="M21 28.5 28.5 36 43 21.5"
        fill="none"
        stroke="#fff"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Logo completa: símbolo + nome, com o "Já" no gradiente da marca. */
export default function Logo({ markClassName = 'size-6' }: { markClassName?: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <LogoMark className={markClassName} />
      <span>
        Conecta <span className="gradiente-texto">Já</span>
      </span>
    </span>
  )
}
