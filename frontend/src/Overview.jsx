import React from 'react';
import './overview.css';

const iconShapes = {
  students: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19v-1.3A4.7 4.7 0 0 1 8.2 13h1.6a4.7 4.7 0 0 1 4.7 4.7V19" />
      <path d="M16.5 5.5a3 3 0 0 1 0 5.8M17 13a4.5 4.5 0 0 1 3.5 4.4V19" />
    </>
  ),
  classes: (
    <>
      <rect x="3" y="4" width="18" height="14" rx="2" />
      <path d="M7 21h10M12 18v3M7 8h10M7 12h6" />
    </>
  ),
  attendance: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M7 3v4M17 3v4M3 10h18m-13 5 2.5 2.5L16 13" />
    </>
  ),
  book: (
    <>
      <path d="M12 6.5C9.4 5 6.5 5 3 5v14c3.5 0 6.4 0 9 1.5 2.6-1.5 5.5-1.5 9-1.5V5c-3.5 0-6.4 0-9 1.5Z" />
      <path d="M12 6.5v14" />
    </>
  ),
  wallet: (
    <>
      <rect x="3" y="6" width="18" height="14" rx="2" />
      <path d="M3 9h18M6 6V4h12v2" />
      <circle cx="16.5" cy="14.5" r="1" />
    </>
  ),
  plus: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v8M8 12h8" />
    </>
  ),
  document: (
    <>
      <path d="M6 3h8l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5M8 12h8M8 16h8" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M7 3v4M17 3v4M3 10h18M8 15h3" />
    </>
  ),
  notes: (
    <>
      <path d="M5 3h10l4 4v14H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5M7 12h8M7 16h5" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m16 16 5 5" />
    </>
  ),
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
};

function Icon({ name, size = 21 }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {iconShapes[name] || iconShapes.arrow}
    </svg>
  );
}

function displayValue(value) {
  return typeof value === 'number'
    ? new Intl.NumberFormat('fr-FR').format(value)
    : value;
}

function initials(name) {
  return (name || '')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toLocaleUpperCase('fr-FR'))
    .join('');
}

function MetricCard({ metric }) {
  return (
    <article className={"overview-metric overview-metric--" + metric.tone}>
      <div className="overview-metric-top">
        <span className="overview-metric-icon"><Icon name={metric.icon} /></span>
        <span className="overview-metric-hint">{metric.hint}</span>
      </div>
      <p className="overview-metric-value">
        {displayValue(metric.value)}
        {metric.unit && <span className="overview-metric-unit">{metric.unit}</span>}
      </p>
      <h3 className="overview-metric-label">{metric.label}</h3>
    </article>
  );
}

function ActionCard({ action }) {
  return (
    <a className="overview-action" href={action.href}>
      <span className="overview-action-icon"><Icon name={action.icon} /></span>
      <span className="overview-action-copy">
        <strong>{action.label}</strong>
        <small>{action.description}</small>
      </span>
      <span className="overview-action-arrow"><Icon name="arrow" size={18} /></span>
    </a>
  );
}

function RecentStudents({ students, allUrl }) {
  return (
    <section className="overview-activity" aria-labelledby="overview-activity-title">
      <div className="overview-section-heading">
        <div>
          <span className="overview-kicker">Suivi des inscriptions</span>
          <h2 id="overview-activity-title">Élèves récemment inscrits</h2>
        </div>
        {allUrl && <a className="overview-text-link" href={allUrl}>Voir tous <Icon name="arrow" size={17} /></a>}
      </div>
      {students.length ? (
        <div className="overview-list">
          {students.map((student) => (
            <a className="overview-list-row" href={student.href} key={student.href}>
              <span className="overview-avatar">{initials(student.name)}</span>
              <span className="overview-list-main">
                <strong>{student.name}</strong>
                <small>{student.className}</small>
              </span>
              <span className="overview-list-date">{student.date}</span>
              <Icon name="arrow" size={17} />
            </a>
          ))}
        </div>
      ) : (
        <div className="overview-empty-list">
          <span className="overview-empty-icon"><Icon name="students" size={25} /></span>
          <strong>Aucune inscription récente</strong>
          <p>Les nouveaux élèves de cette année apparaîtront ici.</p>
        </div>
      )}
    </section>
  );
}

function TeacherClasses({ classes }) {
  return (
    <section className="overview-activity" aria-labelledby="overview-classes-title">
      <div className="overview-section-heading">
        <div>
          <span className="overview-kicker">Mon enseignement</span>
          <h2 id="overview-classes-title">Classes affectées</h2>
        </div>
      </div>
      {classes.length ? (
        <div className="overview-class-grid">
          {classes.map((item) => (
            <a className="overview-class" href={item.href} key={item.href}>
              <span className="overview-class-symbol"><Icon name="classes" /></span>
              <span>
                <strong>{item.name}</strong>
                <small>Suivi des présences</small>
              </span>
              <Icon name="arrow" size={17} />
            </a>
          ))}
        </div>
      ) : (
        <div className="overview-empty-list">
          <span className="overview-empty-icon"><Icon name="classes" size={25} /></span>
          <strong>Aucune classe affectée</strong>
          <p>La direction peut vous attribuer des classes depuis les programmes de matières.</p>
        </div>
      )}
    </section>
  );
}

export default function Overview({ data }) {
  const isTeacher = data.variant === 'teacher';
  const metrics = data.metrics || [];
  const actions = data.actions || [];
  const hasYear = Boolean(data.year);
  const hasRecentStudents = Array.isArray(data.recentStudents);

  return (
    <div className="overview">
      <header className="overview-hero">
        <div className="overview-hero-content">
          <span className="overview-hero-eyebrow"><span className="overview-status-dot" /> {isTeacher ? 'Espace enseignant' : 'Vue d’ensemble'}</span>
          <h1>Bonjour, {data.personName}</h1>
          <p>
            {isTeacher
              ? 'Vos classes, vos élèves et vos outils de suivi au même endroit.'
              : 'L’essentiel de votre établissement, en un coup d’œil.'}
          </p>
          <div className="overview-hero-chips">
            <span><Icon name="classes" size={16} /> {data.schoolName}</span>
            <span><Icon name="calendar" size={16} /> {hasYear ? 'Année scolaire ' + data.year : 'Aucune année active'}</span>
          </div>
        </div>
        <div className="overview-hero-side" aria-label="Votre espace">
          <span className="overview-hero-side-label">Votre espace</span>
          <strong>{data.roleLabel}</strong>
          <span className="overview-hero-side-line" />
          <span>{hasYear ? 'Année scolaire en cours' : 'Année scolaire à configurer'}</span>
          <b>{hasYear ? data.year : '—'}</b>
        </div>
      </header>

      {!hasYear && (
        <section className="overview-year-notice" aria-labelledby="overview-year-title">
          <span className="overview-year-notice-icon"><Icon name="calendar" size={24} /></span>
          <div>
            <h2 id="overview-year-title">Aucune année scolaire active</h2>
            <p>{isTeacher
              ? 'Contactez la direction pour activer l’année scolaire et afficher vos classes.'
              : 'Activez une année scolaire pour afficher les indicateurs et les inscriptions de votre établissement.'}</p>
          </div>
          {data.yearAction && (
            <a href={data.yearAction.href} className="overview-button">
              {data.yearAction.label}<Icon name="arrow" size={17} />
            </a>
          )}
        </section>
      )}

      {hasYear && (
        <section className="overview-section" aria-labelledby="overview-metrics-title">
          <div className="overview-section-heading">
            <div>
              <span className="overview-kicker">{'Année scolaire ' + data.year}</span>
              <h2 id="overview-metrics-title">{isTeacher ? 'Mon activité' : 'Indicateurs clés'}</h2>
            </div>
          </div>
          <div className="overview-metrics">
            {metrics.map((metric) => <MetricCard key={metric.label} metric={metric} />)}
          </div>
        </section>
      )}

      <section className="overview-section" aria-labelledby="overview-actions-title">
        <div className="overview-section-heading">
          <div>
            <span className="overview-kicker">Accès direct</span>
            <h2 id="overview-actions-title">Actions rapides</h2>
          </div>
        </div>
        <div className="overview-actions">
          {actions.map((action) => <ActionCard key={action.href} action={action} />)}
        </div>
      </section>

      {isTeacher && hasYear && <TeacherClasses classes={data.classes || []} />}
      {!isTeacher && hasYear && hasRecentStudents && (
        <RecentStudents students={data.recentStudents} allUrl={data.studentsUrl} />
      )}
    </div>
  );
}
