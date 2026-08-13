import datetime
import io
import pandas as pd
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from applications.models import Application, ApplicationStatus, ApplicationPlatform, EmailMessage, ApplicationEvent

class ApplicationTrackerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='Password123!',
            email='test@example.com'
        )
        # Login to get JWT
        login_res = self.client.post('/api/accounts/login/', {
            'username': 'testuser',
            'password': 'Password123!'
        })
        self.token = login_res.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def test_create_and_list_application(self):
        payload = {
            'company_name': 'Google',
            'job_title': 'Senior Software Engineer',
            'location': 'Mountain View, CA',
            'applied_date': '2026-08-01',
            'status': 'Applied',
            'salary': '$180,000',
            'platform': 'LinkedIn',
            'job_url': 'https://careers.google.com/jobs/123',
            'recruiter_name': 'Sarah Smith',
            'recruiter_email': 'sarah@google.com',
            'notes': 'Submitted resume on referral link'
        }
        res = self.client.post('/api/applications/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['company_name'], 'Google')

        list_res = self.client.get('/api/applications/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)

    def test_dashboard_summary_and_analytics(self):
        Application.objects.create(
            user=self.user,
            company_name='Company A',
            job_title='Dev',
            applied_date=datetime.date(2026, 8, 1),
            status=ApplicationStatus.APPLIED
        )
        Application.objects.create(
            user=self.user,
            company_name='Company B',
            job_title='Dev',
            applied_date=datetime.date(2026, 8, 2),
            status=ApplicationStatus.INTERVIEWING
        )
        
        dash_res = self.client.get('/api/dashboard/')
        self.assertEqual(dash_res.status_code, status.HTTP_200_OK)
        self.assertEqual(dash_res.data['total_applications'], 2)
        self.assertEqual(dash_res.data['interviewing_count'], 1)

        analytics_res = self.client.get('/api/analytics/')
        self.assertEqual(analytics_res.status_code, status.HTTP_200_OK)
        self.assertEqual(analytics_res.data['total_applications'], 2)

    def test_import_excel_with_duplicate_skip_and_update(self):
        df = pd.DataFrame([
            {
                'Company Name': 'VE3',
                'Job Title': 'Senior Python Developer',
                'Location': 'Pune',
                'Applied Date': '2026-08-03',
                'Status': 'Applied',
                'Salary': '14 LPA',
                'Platform': 'LinkedIn',
                'Recruiter Name': 'Supriya',
                'Notes': 'Initial response'
            },
            {
                'Company Name': 'EPG Group',
                'Job Title': 'Senior Software Engineer',
                'Location': 'Remote',
                'Applied Date': '2026-08-05',
                'Status': 'Applied',
                'Salary': '20 LPA',
                'Platform': 'LinkedIn',
                'Recruiter Name': 'John',
                'Notes': 'Submitted application'
            }
        ])
        
        excel_file = io.BytesIO()
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        excel_file.seek(0)
        excel_file.name = 'applications.xlsx'

        # Import first time
        res = self.client.post('/api/applications/import/', {
            'file': excel_file,
            'duplicate_action': 'skip'
        }, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['imported_count'], 2)

        # Import second time with 'skip' (should find 2 duplicates, 0 newly imported)
        excel_file.seek(0)
        res_dup = self.client.post('/api/applications/import/', {
            'file': excel_file,
            'duplicate_action': 'skip'
        }, format='multipart')
        self.assertEqual(res_dup.status_code, status.HTTP_200_OK)
        self.assertEqual(res_dup.data['duplicate_count'], 2)
        self.assertEqual(res_dup.data['imported_count'], 0)

    def test_export_excel(self):
        Application.objects.create(
            user=self.user,
            company_name='Amazon',
            job_title='Backend Engineer',
            applied_date=datetime.date(2026, 8, 4),
            status=ApplicationStatus.APPLIED
        )
        res = self.client.get('/api/applications/export/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_gmail_auth_url_and_status(self):
        # Initial status should be not connected
        status_res = self.client.get('/api/applications/gmail/status/')
        self.assertEqual(status_res.status_code, status.HTTP_200_OK)
        self.assertFalse(status_res.data['connected'])

        # Get auth url
        auth_res = self.client.get('/api/applications/gmail/auth-url/')
        self.assertEqual(auth_res.status_code, status.HTTP_200_OK)
        self.assertIn('auth_url', auth_res.data)

    def test_gmail_connect_sync_and_disconnect(self):
        # Connect Gmail credentials
        connect_payload = {
            'access_token': 'mock_access_token_123',
            'refresh_token': 'mock_refresh_token_456',
            'email_address': 'candidate@example.com'
        }
        conn_res = self.client.post('/api/applications/gmail/connect/', connect_payload, format='json')
        self.assertIn(conn_res.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])
        self.assertTrue(conn_res.data['connected'])

        # Verify status endpoint shows connected
        status_res = self.client.get('/api/applications/gmail/status/')
        self.assertEqual(status_res.status_code, status.HTTP_200_OK)
        self.assertTrue(status_res.data['connected'])
        self.assertEqual(status_res.data['email_address'], 'candidate@example.com')

        # Sync mock job emails
        mock_emails = [
            {
                'id': 'msg_001',
                'thread_id': 'thread_001',
                'subject': 'Your application to Stripe for Senior Software Engineer',
                'from': 'Stripe Recruiting <recruiting@stripe.com>',
                'date': 'Mon, 10 Aug 2026 10:00:00 +0000',
                'body': 'Thank you for applying to Stripe for the Senior Software Engineer position. We have received your application.'
            },
            {
                'id': 'msg_002',
                'thread_id': 'thread_002',
                'subject': 'Interview Invitation with Netflix',
                'from': 'Sarah <sarah@netflix.com>',
                'date': 'Tue, 11 Aug 2026 14:00:00 +0000',
                'body': 'We would like to schedule a technical interview for the Lead Backend Developer role.'
            }
        ]

        sync_res = self.client.post('/api/applications/gmail/sync/', {'mock_emails': mock_emails}, format='json')
        self.assertEqual(sync_res.status_code, status.HTTP_200_OK)
        # Verify sync stages 2 emails for review without creating Application entries automatically
        self.assertEqual(sync_res.data['details']['created_count'], 0)
        self.assertEqual(sync_res.data['details']['pending_review_count'], 2)
        self.assertEqual(Application.objects.filter(user=self.user).count(), 0)

        # Verify staged EmailMessage records
        msg_res = self.client.get('/api/applications/gmail/messages/?status=PENDING_REVIEW')
        self.assertEqual(msg_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(msg_res.data['messages']), 2)

        # Explicitly approve the 2 staged email messages
        messages = msg_res.data['messages']
        for msg in messages:
            app_res = self.client.post(f"/api/applications/gmail/emails/{msg['id']}/approve/")
            self.assertEqual(app_res.status_code, status.HTTP_200_OK)

        # Verify applications table is now populated after explicit review approval
        apps = Application.objects.filter(user=self.user)
        self.assertEqual(apps.count(), 2)

        stripe_app = apps.get(company_name='Stripe')
        self.assertEqual(stripe_app.status, ApplicationStatus.APPLIED)

        netflix_app = apps.get(company_name='Netflix')
        self.assertEqual(netflix_app.status, ApplicationStatus.INTERVIEW_SCHEDULED)

        # Verify ApplicationEvent records created for history tracking
        events = ApplicationEvent.objects.filter(application=netflix_app)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().event_type, "APPLICATION_CREATED")

        # Disconnect Gmail
        disc_res = self.client.post('/api/applications/gmail/disconnect/')
        self.assertEqual(disc_res.status_code, status.HTTP_200_OK)
        self.assertFalse(disc_res.data['connected'])

    def test_gmail_email_review_and_approval(self):
        # Stage email message for review
        email_msg = EmailMessage.objects.create(
            user=self.user,
            gmail_message_id='msg_test_review_1',
            gmail_thread_id='thread_review_1',
            sender_name='Acme Recruiting',
            sender_email='recruiting@acme.com',
            subject='Application status for Senior Django Developer at Acme Corp',
            received_at=datetime.datetime.now(datetime.timezone.utc),
            body_text='Thank you for applying to Acme Corp.',
            snippet='Thank you for applying to Acme Corp.',
            is_job_related=True,
            extracted_company_name='Acme Corp',
            extracted_job_title='Senior Django Developer',
            extracted_status='Applied',
            extracted_platform='LinkedIn',
            confidence_score=0.92,
            processing_status='PENDING_REVIEW'
        )

        # 1. Test fetch messages review endpoint
        res_list = self.client.get('/api/applications/gmail/messages/?status=PENDING_REVIEW')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(res_list.data['pending_review_count'], 1)
        self.assertEqual(len(res_list.data['messages']), 1)

        # 2. Test single approve endpoint with field override
        approve_res = self.client.post(f'/api/applications/gmail/emails/{email_msg.id}/approve/', {
            'company_name': 'Acme Corporation',
            'job_title': 'Lead Backend Engineer',
            'status': 'Interview Scheduled'
        }, format='json')
        self.assertEqual(approve_res.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_res.data['company_name'], 'Acme Corporation')

        # Verify application was created in main Application table
        app = Application.objects.get(user=self.user, company_name='Acme Corporation')
        self.assertEqual(app.job_title, 'Lead Backend Engineer')
        self.assertEqual(app.status, ApplicationStatus.INTERVIEW_SCHEDULED)

        # 3. Verify ignoring is BLOCKED while active application exists in Application table
        blocked_ignore_res = self.client.post(f'/api/applications/gmail/emails/{email_msg.id}/ignore/')
        self.assertEqual(blocked_ignore_res.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Delete application from main Application table
        del_res = self.client.delete(f'/api/applications/{app.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)

        # Verify email message status was reset to PENDING_REVIEW upon application deletion
        email_msg.refresh_from_db()
        self.assertEqual(email_msg.processing_status, 'PENDING_REVIEW')

        # 5. Test ignore endpoint now succeeds after application deletion
        ignore_res = self.client.post(f'/api/applications/gmail/emails/{email_msg.id}/ignore/')
        self.assertEqual(ignore_res.status_code, status.HTTP_200_OK)

        email_msg.refresh_from_db()
        self.assertEqual(email_msg.processing_status, 'IGNORED')
