import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmProvider, useConfirm } from './ConfirmDialog'
import { useState } from 'react'

function Harness() {
  const confirm = useConfirm()
  const [result, setResult] = useState('none')
  return (
    <div>
      <button onClick={() => void confirm({ title: 'Delete it', message: 'Sure?' }).then(ok => setResult(ok ? 'yes' : 'no'))}>
        open
      </button>
      <span data-testid="result">{result}</span>
    </div>
  )
}

describe('ConfirmDialog', () => {
  it('resolves true on confirm and false on cancel or Escape', async () => {
    const user = userEvent.setup()
    render(<ConfirmProvider><Harness /></ConfirmProvider>)

    await user.click(screen.getByText('open'))
    expect(screen.getByRole('dialog', { name: 'Delete it' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(screen.getByTestId('result')).toHaveTextContent('yes')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(screen.getByText('open'))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByTestId('result')).toHaveTextContent('no')

    await user.click(screen.getByText('open'))
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
