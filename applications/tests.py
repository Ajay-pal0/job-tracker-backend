import datetime
import io
import pandas as pd
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from applications.models import Application, ApplicationStatus, ApplicationPlatform

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
