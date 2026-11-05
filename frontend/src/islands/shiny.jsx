import { render } from 'preact';
import ShinyText from '../rb/ShinyText.jsx';

export default function mount(el) {
  const text = el.textContent.trim();
  const d = el.dataset;
  el.textContent = '';
  render(<ShinyText text={text} color={d.color || '#b8b8b8'} shineColor={d.shine || '#ffffff'} speed={3} />, el);
}
