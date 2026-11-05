import { render } from 'preact';
import SpotlightCard from '../rb/SpotlightCard.jsx';

// Adds the spotlight glow as a layer *behind* the card's existing (server-rendered) content.
export default function mount(el) {
  if (!window.matchMedia('(hover: hover)').matches) return; // no hover on touch screens
  const dark = el.classList.contains('card-dark');
  const layer = document.createElement('div');
  layer.className = 'rb-spot-layer';
  layer.setAttribute('aria-hidden', 'true');
  el.prepend(layer);
  el.classList.add('rb-spot');
  render(<SpotlightCard className="rb-spot-inner" theme={dark ? 'dark' : 'light'} proximity={0}
                        spotlightColor={dark ? 'rgba(255, 70, 60, 0.9)' : 'rgba(225, 6, 0, 0.55)'}
                        intensity={dark ? 0.25 : 0.5} spotlightSize={dark ? 320 : 260} />, layer);
}
