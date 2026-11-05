import { render } from 'preact';
import GradientText from '../rb/GradientText.jsx';

export default function mount(el) {
  const text = el.textContent.trim();
  el.textContent = '';
  render(<GradientText colors={['#ff2a1f', '#ffffff', '#e10600', '#ff7a70']} animationSpeed={6} angle={100}>{text}</GradientText>, el);
}
