"""
أمر نسخ احتياطي لقاعدة البيانات.
الاستخدام:
    python manage.py backup_db
"""

import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "نسخ احتياطي لقاعدة البيانات"

    MAX_BACKUPS = 7

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES["default"]["NAME"])
        if not db_path.exists():
            self.stdout.write(self.style.ERROR(f"قاعدة البيانات غير موجودة: {db_path}"))
            return

        backup_dir = Path(settings.BASE_DIR) / "backups"
        backup_dir.mkdir(exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = backup_dir / f"db_{stamp}.sqlite3"

        shutil.copy2(db_path, target)
        size_mb = target.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f"✔ نسخة احتياطية: {target.name} ({size_mb:.2f} MB)"
        ))

        backups = sorted(backup_dir.glob("db_*.sqlite3"))
        if len(backups) > self.MAX_BACKUPS:
            to_delete = backups[:-self.MAX_BACKUPS]
            for old in to_delete:
                old.unlink()
                self.stdout.write(f"  حُذفت النسخة القديمة: {old.name}")