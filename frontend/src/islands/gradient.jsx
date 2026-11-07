import { render } from 'preact';
import GradientText from '../rb/GradientText.jsx';

export default function mount(el) {
  const text = el.textContent.trim();
  el.textContent = '';
  render(<GradientText colors={['#e8666d', '#ffffff', '#f4a3a7', '#e8666d']} animationSpeed={6} angle={100}>{text}</GradientText>, el);
}
