import { render } from 'preact';
import Threads from '../rb/Threads.jsx';

export default function mount(el) {
  const small = window.innerWidth < 768;
  const conn = navigator.connection;
  if (conn && (conn.saveData || /2g/.test(conn.effectiveType || ''))) return; // stay static on slow networks
  render(<Threads color="#c8323b" accentColor="#e8666d" amplitude={small ? 1.2 : 1.6} distance={0.3}
                  lineCount={small ? 40 : 70} speed={0.5} brightness={1.6} enableMouseInteraction={!small} />, el);
  requestAnimationFrame(() => el.classList.add('is-live'));
}
