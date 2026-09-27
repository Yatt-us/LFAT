import { useMemo, useState } from 'react';
import './student-directory.css';

const collator = new Intl.Collator('fr', { sensitivity: 'base', numeric: true });

function Icon({ name }) {
  if (name === 'plus') {
    return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" strokeLinecap="round" /></svg>;
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m16 16 4 4" strokeLinecap="round" /></svg>;
}

function Avatar({ student }) {
  const [failed, setFailed] = useState(false);
  const initials = [student.prenom, student.nom]
    .filter(Boolean).map((part) => part.trim().charAt(0).toLocaleUpperCase('fr'))
    .slice(0, 2).join('');
  return (
    <span className="directory-avatar" aria-hidden="true">
      {student.photoUrl && !failed
        ? <img src={student.photoUrl} alt="" loading="lazy" onError={() => setFailed(true)} />
        : initials || 'É'}
    </span>
  );
}

function Status({ value }) {
  const variants = { Actif: 'active', Suspendu: 'paused', Ancien: 'former', Radié: 'former' };
  return <span className={'directory-status directory-status--' + (variants[value] || 'former')}>
    <span className="directory-status-dot" aria-hidden="true" />{value || 'Non défini'}
  </span>;
}

function Actions({ student }) {
  const name = [student.prenom, student.nom].filter(Boolean).join(' ');
  return <div className="directory-actions">
    <a className="directory-action directory-action--primary" href={student.detailUrl} aria-label={'Voir le dossier de ' + name}>Voir</a>
    <a className="directory-action" href={student.editUrl} aria-label={'Modifier le dossier de ' + name}>Modifier</a>
    {student.archiveUrl && <a className="directory-action directory-action--muted" href={student.archiveUrl} aria-label={'Archiver le dossier de ' + name}>Archiver</a>}
  </div>;
}

function StudentIdentity({ student, mobile = false }) {
  return <div className="directory-person">
    <Avatar student={student} />
    <div>
      <a className="directory-person-name" href={student.detailUrl}>{student.prenom} {student.nom}</a>
      <span className="directory-person-caption">{mobile ? student.matricule || 'Sans matricule' : 'Dossier élève'}</span>
    </div>
  </div>;
}

export default function StudentDirectory({ data }) {
  const students = data?.students || [];
  const classes = data?.classes || [];
  const initiallyFiltered = data?.selectedClassId != null;
  const [query, setQuery] = useState('');
  const [classId, setClassId] = useState(String(data?.selectedClassId ?? ''));

  const visibleStudents = useMemo(() => {
    const search = query.trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fr');
    return students
      .filter((student) => !classId || String(student.classeId ?? '') === classId)
      .filter((student) => {
        if (!search) return true;
        const text = [student.prenom, student.nom, student.matricule, student.classeNom, student.anneeInscription].join(' ')
          .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fr');
        return text.includes(search);
      })
      .sort((a, b) => collator.compare(a.classeNom || '', b.classeNom || '')
        || collator.compare(a.nom || '', b.nom || '')
        || collator.compare(a.prenom || '', b.prenom || ''));
  }, [students, query, classId]);

  function changeClass(nextClassId) {
    const nextUrl = new URL(window.location.href);
    if (nextClassId) nextUrl.searchParams.set('classe', nextClassId);
    else nextUrl.searchParams.delete('classe');
    const path = nextUrl.pathname + nextUrl.search + nextUrl.hash;
    if (initiallyFiltered) {
      window.location.assign(path);
    } else {
      setClassId(nextClassId);
      window.history.replaceState(null, '', path);
    }
  }

  const emptyAll = students.length === 0 && !query.trim() && !classId;

  return <div className="directory">
    <header className="directory-hero">
      <div className="directory-hero-copy">
        <span className="directory-eyebrow">SCOLARITÉ <span aria-hidden="true">/</span> ÉLÈVES</span>
        <h1>Annuaire des élèves</h1>
        <p>Retrouvez les dossiers, les classes et les statuts de votre établissement en un seul endroit.</p>
      </div>
      <a className="directory-create" href={data.createUrl}><Icon name="plus" /><span>Ajouter un élève</span></a>
      <span className="directory-hero-orb" aria-hidden="true" />
    </header>

    <div className="directory-overview" aria-label="Vue d’ensemble">
      <div className="directory-overview-item"><span className="directory-overview-label">Élèves dans la sélection</span><strong>{students.length}</strong><span className="directory-overview-note">Dossiers disponibles</span></div>
      <div className="directory-overview-item"><span className="directory-overview-label">Classes</span><strong>{classes.length}</strong><span className="directory-overview-note">Pour l’année active</span></div>
      <div className="directory-overview-item"><span className="directory-overview-label">Année scolaire</span><strong className="directory-overview-year">{data.year || 'Non définie'}</strong><span className="directory-overview-note">{data.year ? 'Année active' : 'À configurer'}</span></div>
    </div>

    <section className="directory-panel" aria-labelledby="directory-list-title">
      <div className="directory-panel-head">
        <div><span className="directory-section-kicker">RÉPERTOIRE</span><h2 id="directory-list-title">Liste des élèves</h2><p>Recherchez un dossier ou affinez la liste par classe.</p></div>
        <span className="directory-count" aria-live="polite">{visibleStudents.length} {visibleStudents.length > 1 ? 'résultats' : 'résultat'}</span>
      </div>
      <div className="directory-filters">
        <label className="directory-search" htmlFor="directory-search-input">
          <Icon name="search" /><span className="directory-visually-hidden">Rechercher un élève</span>
          <input id="directory-search-input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nom, prénom ou matricule…" autoComplete="off" />
        </label>
        <div className="directory-select-wrap">
          <label htmlFor="directory-class-select">Classe</label>
          <select id="directory-class-select" value={classId} onChange={(event) => changeClass(event.target.value)} disabled={classes.length === 0}>
            <option value="">Toutes les classes</option>
            {classes.map((schoolClass) => <option key={schoolClass.id} value={schoolClass.id}>{schoolClass.nom}</option>)}
          </select>
        </div>
      </div>

      {visibleStudents.length ? <>
        <div className="directory-table-wrap">
          <table className="directory-table">
            <thead><tr><th scope="col">Élève</th><th scope="col">Matricule</th><th scope="col">Classe</th><th scope="col">Année scolaire</th><th scope="col">Statut</th><th scope="col"><span className="directory-visually-hidden">Actions</span></th></tr></thead>
            <tbody>{visibleStudents.map((student) => <tr key={student.id}>
              <td><StudentIdentity student={student} /></td>
              <td><span className="directory-matricule">{student.matricule || '—'}</span></td>
              <td>{student.classeNom || 'Sans classe'}</td>
              <td>{student.anneeInscription || '—'}</td>
              <td><Status value={student.statut} /></td>
              <td><Actions student={student} /></td>
            </tr>)}</tbody>
          </table>
        </div>
        <div className="directory-mobile-list">
          {visibleStudents.map((student) => <article className="directory-mobile-card" key={student.id}>
            <div className="directory-mobile-top"><StudentIdentity student={student} mobile /><Status value={student.statut} /></div>
            <div className="directory-mobile-meta">
              <div><span>Classe</span><strong>{student.classeNom || 'Sans classe'}</strong></div>
              <div><span>Année scolaire</span><strong>{student.anneeInscription || '—'}</strong></div>
            </div>
            <Actions student={student} />
          </article>)}
        </div>
      </> : <div className="directory-empty">
        <span className="directory-empty-icon"><Icon name="search" /></span>
        <h3>{emptyAll ? 'Aucun élève pour le moment' : 'Aucun élève trouvé'}</h3>
        <p>{emptyAll ? 'Commencez par ajouter un élève à votre établissement.' : 'Essayez un autre nom, matricule ou filtre de classe.'}</p>
        {emptyAll
          ? <a href={data.createUrl} className="directory-empty-link">Ajouter un élève</a>
          : <button type="button" className="directory-empty-link" onClick={() => { setQuery(''); if (classId) changeClass(''); }}>Effacer les filtres</button>}
      </div>}
    </section>
  </div>;
}
