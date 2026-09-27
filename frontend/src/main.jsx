import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Overview from './Overview.jsx';
import StudentDirectory from './StudentDirectory.jsx';

const paths = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
  layers: <><path d="m12 2 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 17l9 5 9-5"/></>,
  briefcase: <><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M2 12a20 20 0 0 0 20 0"/></>,
  book: <><path d="M12 7c-2-2-5-2-9-2v15c4 0 7 0 9 2 2-2 5-2 9-2V5c-4 0-7 0-9 2ZM12 7v15"/></>,
  list: <><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></>,
  edit: <><path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4L16.5 3.5Z"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  wallet: <><rect x="3" y="6" width="18" height="15" rx="2"/><path d="M3 10h18M16 16h2M5 6V4a1 1 0 0 1 1-1h12"/></>,
  file: <><path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10l-7-7ZM13 3v7h7M8 15h8M8 18h6"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2 2-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21h-3v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-2-2 .1-.1A1.7 1.7 0 0 0 7.2 15a1.7 1.7 0 0 0-1.5-1H5v-3h.7a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9L6.8 8l2-2 .1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5V4h3v.9a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 2 2-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1H21v3h-.1a1.7 1.7 0 0 0-1.5 1Z"/></>,
  logout: <><path d="M10 17l5-5-5-5M15 12H3M12 3h6a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3h-6"/></>,
};

function Icon({ name }) {
  return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.grid}</svg>;
}

function Navigation({ data }) {
  const [open, setOpen] = useState(() => window.matchMedia('(max-width: 1060px)').matches && window.location.hash === '#nav-root');
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 1060px)').matches);
  const closeRef = useRef(null);
  const sidebarRef = useRef(null);
  const wasOpenRef = useRef(false);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1060px)');
    const onChange = (event) => {
      setCompact(event.matches);
      if (!event.matches) setOpen(false);
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    const host = document.getElementById('nav-root');
    const toggle = document.getElementById('mobile-menu-toggle');
    const main = document.querySelector('.saas-main');
    const skipLink = document.querySelector('.saas-skip-link');
    const onToggle = (event) => { event.preventDefault(); setOpen(value => !value); };
    const onKeyDown = (event) => {
      if (!compact || !open) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
      }
      if (event.key !== 'Tab') return;
      const sidebar = sidebarRef.current;
      if (!sidebar) return;
      const focusable = [...sidebar.querySelectorAll('a[href], button:not([disabled])')]
        .filter((element) => element.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === sidebar)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    toggle?.addEventListener('click', onToggle);
    window.addEventListener('keydown', onKeyDown);
    host?.classList.toggle('is-open', open);
    document.body.classList.toggle('saas-drawer-open', open && compact);
    if (main) main.inert = open && compact;
    if (skipLink) skipLink.inert = open && compact;
    toggle?.setAttribute('aria-expanded', String(open && compact));
    toggle?.setAttribute('aria-label', open && compact ? 'Fermer la navigation' : 'Ouvrir la navigation');
    const focusTimer = compact && open && !wasOpenRef.current
      ? window.setTimeout(() => closeRef.current?.focus(), 250)
      : null;
    if (compact && !open && wasOpenRef.current) toggle?.focus();
    wasOpenRef.current = open && compact;
    if (!open && window.location.hash === '#nav-root') {
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
    return () => {
      toggle?.removeEventListener('click', onToggle);
      window.removeEventListener('keydown', onKeyDown);
      host?.classList.remove('is-open');
      document.body.classList.remove('saas-drawer-open');
      if (main) main.inert = false;
      if (skipLink) skipLink.inert = false;
      if (focusTimer !== null) window.clearTimeout(focusTimer);
    };
  }, [open, compact]);

  return <>
    {open && compact && <button type="button" className="saas-nav-scrim" tabIndex={-1} aria-hidden="true" onClick={() => setOpen(false)} />}
    <aside ref={sidebarRef} className="saas-sidebar" aria-label="Navigation principale" role={compact ? 'dialog' : undefined} aria-modal={compact && open ? 'true' : undefined} inert={compact && !open}>
      <button ref={closeRef} type="button" className="saas-drawer-close" aria-label="Fermer la navigation" onClick={() => setOpen(false)}><span aria-hidden="true">×</span></button>
      <a className="saas-brand" href={data.sections?.[0]?.items?.[0]?.href || '/'} onClick={() => setOpen(false)}>
        <span className="saas-brand-mark">{data.school_logo_url ? <img src={data.school_logo_url} alt="" /> : <span>É</span>}</span>
        <span className="saas-brand-copy"><strong>{data.school_name}</strong><small>Espace scolaire</small></span>
      </a>
      <div className="saas-school-year"><span className="saas-status-dot" />{data.year}</div>
      <nav className="saas-menu" aria-label="Sections">
        {(data.sections || []).map(section => <div className="saas-menu-section" key={section.label}>
          <span className="saas-menu-label">{section.label}</span>
          {section.items.map(item => <a key={item.id} className={`saas-nav-link${item.active ? ' active' : ''}`} href={item.href} aria-current={item.active ? 'page' : undefined} onClick={() => setOpen(false)}><Icon name={item.icon} />{item.label}</a>)}
        </div>)}
      </nav>
      <div className="saas-sidebar-bottom">
        <div className="saas-account"><span className="saas-avatar">{data.user_initials}</span><span><strong>{data.user_name}</strong><small>{data.role}</small></span></div>
        <a className="saas-logout" href={data.password_url}>Modifier mon mot de passe</a>
        <form method="post" action={data.logout_url}><input type="hidden" name="csrfmiddlewaretoken" value={data.csrf_token} /><button className="saas-logout" type="submit"><Icon name="logout" />Déconnexion</button></form>
      </div>
    </aside>
  </>;
}

function dataFrom(id) {
  const script = document.getElementById(id);
  return script ? JSON.parse(script.textContent) : null;
}

const navigationRoot = document.getElementById('nav-root');
const navigationData = dataFrom('navigation-data');
if (navigationRoot && navigationData?.sections) {
  createRoot(navigationRoot).render(<Navigation data={navigationData} />);
}

const overviewRoot = document.getElementById('overview-root');
const overviewData = dataFrom('overview-data');
if (overviewRoot && overviewData) {
  createRoot(overviewRoot).render(<Overview data={overviewData} />);
}

const studentsRoot = document.getElementById('students-root');
const studentsData = dataFrom('students-data');
if (studentsRoot && studentsData) {
  createRoot(studentsRoot).render(<StudentDirectory data={studentsData} />);
}
