import json
from django.core.management.base import BaseCommand
from applications.services.sync_service import sync_all_gmail_applications

class Command(BaseCommand):
    help = 'Executes Gmail synchronization for all active user connections (Celery-free background job).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Starting batch Gmail sync...'))
        
        result = sync_all_gmail_applications()
        
        if result.get('status') == 'skipped':
            self.stdout.write(self.style.WARNING(f"Sync skipped: {result.get('reason')}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Sync completed! Total users: {result.get('total_users')}, "
                f"Success: {result.get('synced_users')}, Failed: {result.get('failed_users')}"
            ))
            self.stdout.write(json.dumps(result, indent=2))
