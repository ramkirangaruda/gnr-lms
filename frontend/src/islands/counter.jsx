import { render } from 'preact';
import Counter from '../rb/Counter.jsx';

export default function mount(el) {
  const value = Number(el.dataset.value ?? el.textContent.replace(/[^\d.]/g, ''));
  if (Number.isNaN(value)) return;
  el.textContent = '';
  render(<Counter value={value} fontSize="1em" suffix={el.dataset.suffix || undefined} />, el);
}
