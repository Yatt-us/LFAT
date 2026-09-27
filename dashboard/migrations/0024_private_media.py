"""Move confidential school records out of the public media directory."""
import filecmp
import shutil
from pathlib import Path

import dashboard.private_media
from django.conf import settings
from django.db import migrations, models


PRIVATE_DIRECTORIES = (
    'photos_profil_eleves', 'dossiers_inscription',
    'certificats_frequentation', 'certificats', 'settings/assets',
)
PRIVATE_FIELDS = (
    ('EcoleSettings', 'cachet_admin'),
    ('EcoleSettings', 'signature_directeur'),
    ('Etudiant', 'photo_profil'),
    ('DossierInscriptionImage', 'image'),
    ('CertificatFrequentation', 'fichier_pdf'),
    ('CertificatFrequentation', 'cachet_utilise'),
    ('CertificatFrequentation', 'signature_utilisee'),
    ('CertificatFrequentation', 'qr_code'),
)


def move_existing_files(apps, schema_editor):
    public_root = Path(settings.MEDIA_ROOT).resolve()
    private_root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
    if private_root == public_root or public_root in private_root.parents:
        raise RuntimeError('PRIVATE_MEDIA_ROOT doit être hors de MEDIA_ROOT.')

    paths = set()
    for directory in PRIVATE_DIRECTORIES:
        source_dir = public_root / directory
        if source_dir.is_dir():
            for source in source_dir.rglob('*'):
                if source.is_file():
                    paths.add(source.relative_to(public_root).as_posix())

    for model_name, field_name in PRIVATE_FIELDS:
        model = apps.get_model('dashboard', model_name)
        for name in model.objects.values_list(field_name, flat=True).iterator():
            if name:
                paths.add(name)

    # The old upload path mixed logos with seals and signatures. Move each
    # referenced logo to a public logo-only path before clearing that directory.
    school_model = apps.get_model('dashboard', 'EcoleSettings')
    for school in school_model.objects.exclude(logo__isnull=True).exclude(logo='').iterator():
        name = school.logo.name
        if name not in paths and not any(name.startswith(directory + '/') for directory in PRIVATE_DIRECTORIES):
            continue
        source = public_root / name
        logo_name = f'ecoles/logos/migrated_{school.pk}{Path(name).suffix}'
        target = public_root / logo_name
        if source.exists():
            if source.is_symlink() or not source.is_file():
                raise RuntimeError('Logo invalide : ' + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if not filecmp.cmp(source, target, shallow=False):
                    raise RuntimeError('Conflit de logo : ' + logo_name)
            else:
                shutil.copy2(source, target)
                if not filecmp.cmp(source, target, shallow=False):
                    raise RuntimeError('Copie de logo incomplète : ' + logo_name)
        elif not target.is_file():
            # The database may reference an already missing legacy upload.
            continue
        school.logo = logo_name
        school.save(update_fields=['logo'])

    to_delete = []
    for name in sorted(paths):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Chemin média invalide : ' + name)
        source = public_root / relative
        target = private_root / relative
        if not source.exists():
            continue
        if source.is_symlink() or not source.is_file():
            raise RuntimeError('Fichier média invalide : ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not filecmp.cmp(source, target, shallow=False):
                raise RuntimeError('Conflit de fichier privé : ' + name)
        else:
            shutil.copy2(source, target)
            if not filecmp.cmp(source, target, shallow=False):
                raise RuntimeError('Copie incomplète : ' + name)
        to_delete.append(source)

    # Remove old public copies only after every private copy has been verified.
    for source in to_delete:
        source.unlink()


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0023_creances_scolaires')]

    operations = [
        migrations.RunPython(move_existing_files, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='ecolesettings', name='logo',
            field=models.ImageField(upload_to='ecoles/logos/', blank=True, null=True, verbose_name="Logo de l'École"),
        ),
        migrations.AlterField(
            model_name='ecolesettings', name='cachet_admin',
            field=models.ImageField(upload_to='settings/assets/', storage=dashboard.private_media.PrivateMediaStorage(), blank=True, null=True, verbose_name="Cachet (Sceau) de l'Administration"),
        ),
        migrations.AlterField(
            model_name='ecolesettings', name='signature_directeur',
            field=models.ImageField(upload_to='settings/assets/', storage=dashboard.private_media.PrivateMediaStorage(), blank=True, null=True, verbose_name='Signature du Directeur/Responsable'),
        ),
        migrations.AlterField(
            model_name='etudiant', name='photo_profil',
            field=models.ImageField(upload_to='photos_profil_eleves/', storage=dashboard.private_media.PrivateMediaStorage(), blank=True, null=True, verbose_name='Photo de Profil'),
        ),
        migrations.AlterField(
            model_name='dossierinscriptionimage', name='image',
            field=models.ImageField(upload_to='dossiers_inscription/', storage=dashboard.private_media.PrivateMediaStorage(), verbose_name='Fichier (Image ou PDF)'),
        ),
        migrations.AlterField(
            model_name='certificatfrequentation', name='fichier_pdf',
            field=models.FileField(upload_to='certificats_frequentation/', storage=dashboard.private_media.PrivateMediaStorage(), blank=True, null=True, verbose_name='Fichier PDF du Certificat'),
        ),
        migrations.AlterField(
            model_name='certificatfrequentation', name='cachet_utilise',
            field=models.FileField(upload_to='certificats/assets/', storage=dashboard.private_media.PrivateMediaStorage(), blank=True, null=True, verbose_name='Cachet (Sceau) utilisé'),
        ),
        migrations.AlterField(
            model_name='certificatfrequentation', name='signature_utilisee',
            field=models.FileField(upload_to='certificats/assets/', storage=dashboard.private_media.PrivateMediaStorage(), blank=True, null=True, verbose_name='Signature utilisée'),
        ),
        migrations.AlterField(
            model_name='certificatfrequentation', name='qr_code',
            field=models.ImageField(upload_to='certificats/qrcodes/', storage=dashboard.private_media.PrivateMediaStorage(), blank=True, null=True, verbose_name='QR Code de vérification'),
        ),
    ]
