import { useId, useState } from 'react'
import { Button } from './ui'

/**
 * Nota de 1 a 5 e comentário opcional de até 500 caracteres. Usado pelo prestador para avaliar
 * a empresa (US64) e pela empresa para avaliar o prestador (US63). A avaliação é definitiva.
 */
export default function RatingForm({
  legend,
  busy,
  onSubmit,
  onCancel,
}: {
  legend: string
  busy: boolean
  onSubmit: (rating: number, comment: string) => void
  onCancel: () => void
}) {
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const id = useId()
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (rating > 0) onSubmit(rating, comment)
      }}
    >
      <fieldset className="m-0 border-0 p-0">
        <legend>{legend}</legend>
        <div className="acoes">
          {[1, 2, 3, 4, 5].map((value) => (
            <label key={value}>
              <input
                type="radio"
                name={`nota-${id}`}
                value={value}
                checked={rating === value}
                onChange={() => setRating(value)}
              />{' '}
              {value} {value === 1 ? 'estrela' : 'estrelas'}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="field">
        <label htmlFor={`comentario-${id}`}>Comentário (opcional)</label>
        <textarea
          id={`comentario-${id}`}
          maxLength={500}
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
        <small>{comment.length}/500</small>
      </div>
      <p>A avaliação é definitiva e não pode ser editada depois de enviada.</p>
      <div className="acoes">
        <Button type="submit" busy={busy} disabled={rating === 0}>
          Enviar avaliação
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Voltar
        </Button>
      </div>
    </form>
  )
}
