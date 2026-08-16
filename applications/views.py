import datetime
import io
import os
import requests
import pandas as pd
from django.http import HttpResponse
from django.conf import settings
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Application, ApplicationStatus, ApplicationPlatform, GmailConnection, GmailCredential, EmailMessage, ApplicationEvent, EmailProcessingStatus
from .serializers import ApplicationSerializer, EmailMessageSerializer, ApplicationEventSerializer
from .services.gmail_service import GmailService
from .services.application_service import ApplicationService

class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Application.objects.filter(user=self.request.user)
        
        # Filtering by status
        status_param = self.request.query_params.get('status')
        if status_param and status_param != 'All':
            queryset = queryset.filter(status=status_param)

        # Filtering by platform
        platform_param = self.request.query_params.get('platform')
        if platform_param and platform_param != 'All':
            queryset = queryset.filter(platform=platform_param)

        # Search query
        search_query = self.request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(company_name__icontains=search_query) |
                Q(job_title__icontains=search_query) |
                Q(location__icontains=search_query) |
                Q(recruiter_name__icontains=search_query) |
                Q(recruiter_email__icontains=search_query) |
                Q(notes__icontains=search_query) |
                Q(platform__icontains=search_query)
            )

        # Ordering
        ordering = self.request.query_params.get('ordering')
        if ordering:
            if ordering == 'applied_date_asc':
                queryset = queryset.order_by('applied_date', 'id')
            elif ordering == 'applied_date_desc':
                queryset = queryset.order_by('-applied_date', '-id')
            elif ordering == 'company_asc':
                queryset = queryset.order_by('company_name')
            elif ordering == 'company_desc':
                queryset = queryset.order_by('-company_name')
            elif ordering in ['highest_salary', 'salary_desc']:
                queryset = queryset.order_by('-salary')
            else:
                queryset = queryset.order_by(ordering)
        return queryset

    def perform_destroy(self, instance):
        gmail_msg_id = instance.gmail_message_id
        user = instance.user
        instance.delete()

        # When application is removed from application table, unlock/reset EmailMessage status back to PENDING_REVIEW
        if gmail_msg_id:
            EmailMessage.objects.filter(
                user=user,
                gmail_message_id=gmail_msg_id
            ).update(
                processing_status=EmailProcessingStatus.PENDING_REVIEW,
                processed_at=None
            )

class ImportApplicationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        duplicate_action = request.data.get('duplicate_action', 'skip')

        if not file_obj:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        filename = file_obj.name.lower()
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(file_obj)
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_obj)
            else:
                return Response({'error': 'Unsupported file format. Please upload CSV or Excel (.xlsx).'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Failed to parse file: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Column Header Normalization Map
        column_map = {}
        for col in df.columns:
            clean_col = str(col).strip().lower()
            if clean_col in ['company', 'company name', 'company_name']:
                column_map[col] = 'company_name'
            elif clean_col in ['role', 'job title', 'job_title', 'title', 'position']:
                column_map[col] = 'job_title'
            elif clean_col in ['location', 'city']:
                column_map[col] = 'location'
            elif clean_col in ['applied date', 'date applied', 'applied_date', 'date']:
                column_map[col] = 'applied_date'
            elif clean_col in ['status', 'stage']:
                column_map[col] = 'status'
            elif clean_col in ['salary', 'compensation', 'pay']:
                column_map[col] = 'salary'
            elif clean_col in ['platform', 'source', 'source/platform']:
                column_map[col] = 'platform'
            elif clean_col in ['job url', 'url', 'link', 'job link', 'job_url']:
                column_map[col] = 'job_url'
            elif clean_col in ['recruiter', 'recruiter name', 'contact', 'people connected', 'recruiter_name']:
                column_map[col] = 'recruiter_name'
            elif clean_col in ['recruiter email', 'recruiter_email', 'contact email']:
                column_map[col] = 'recruiter_email'
            elif clean_col in ['notes', 'notes / call logs / next steps', 'notes/call logs/next steps']:
                column_map[col] = 'notes'

        df.rename(columns=column_map, inplace=True)

        imported_count = 0
        duplicate_count = 0
        invalid_count = 0
        errors = []

        valid_statuses = [choice[0] for choice in ApplicationStatus.choices]
        valid_platforms = [choice[0] for choice in ApplicationPlatform.choices]

        for index, row in df.iterrows():
            row_num = index + 2
            company_name = str(row.get('company_name', '')).strip() if pd.notna(row.get('company_name')) else ''
            job_title = str(row.get('job_title', '')).strip() if pd.notna(row.get('job_title')) else ''
            
            if not company_name or not job_title or company_name.lower() == 'nan' or job_title.lower() == 'nan':
                invalid_count += 1
                errors.append(f"Row {row_num}: Missing required fields Company Name or Job Title.")
                continue

            raw_date = row.get('applied_date')
            applied_date = None
            if pd.notna(raw_date):
                try:
                    if isinstance(raw_date, (datetime.date, datetime.datetime)):
                        applied_date = raw_date.date() if isinstance(raw_date, datetime.datetime) else raw_date
                    else:
                        parsed_dt = pd.to_datetime(raw_date, errors='coerce')
                        if pd.notna(parsed_dt):
                            applied_date = parsed_dt.date()
                except Exception:
                    pass

            if not applied_date:
                applied_date = datetime.date.today()

            raw_status = str(row.get('status', '')).strip() if pd.notna(row.get('status')) else 'Applied'
            matched_status = 'Applied'
            for s in valid_statuses:
                if s.lower() == raw_status.lower():
                    matched_status = s
                    break

            raw_platform = str(row.get('platform', '')).strip() if pd.notna(row.get('platform')) else 'LinkedIn'
            matched_platform = 'LinkedIn'
            for p in valid_platforms:
                if p.lower() == raw_platform.lower():
                    matched_platform = p
                    break
                elif raw_platform.lower() in p.lower():
                    matched_platform = p
                    break

            location = str(row.get('location', '')).strip() if pd.notna(row.get('location')) and str(row.get('location')).lower() != 'nan' else ''
            salary = str(row.get('salary', '')).strip() if pd.notna(row.get('salary')) and str(row.get('salary')).lower() != 'nan' else ''
            job_url = str(row.get('job_url', '')).strip() if pd.notna(row.get('job_url')) and str(row.get('job_url')).lower() != 'nan' else ''
            recruiter_name = str(row.get('recruiter_name', '')).strip() if pd.notna(row.get('recruiter_name')) and str(row.get('recruiter_name')).lower() != 'nan' else ''
            recruiter_email = str(row.get('recruiter_email', '')).strip() if pd.notna(row.get('recruiter_email')) and str(row.get('recruiter_email')).lower() != 'nan' else ''
            notes = str(row.get('notes', '')).strip() if pd.notna(row.get('notes')) and str(row.get('notes')).lower() != 'nan' else ''

            existing = Application.objects.filter(
                user=request.user,
                company_name__iexact=company_name,
                job_title__iexact=job_title,
                applied_date=applied_date
            ).first()

            if existing:
                duplicate_count += 1
                if duplicate_action == 'update':
                    existing.location = location or existing.location
                    existing.status = matched_status
                    existing.salary = salary or existing.salary
                    existing.platform = matched_platform
                    existing.job_url = job_url or existing.job_url
                    existing.recruiter_name = recruiter_name or existing.recruiter_name
                    existing.recruiter_email = recruiter_email or existing.recruiter_email
                    existing.notes = notes or existing.notes
                    existing.save()
                    imported_count += 1
            else:
                Application.objects.create(
                    user=request.user,
                    company_name=company_name,
                    job_title=job_title,
                    location=location,
                    applied_date=applied_date,
                    status=matched_status,
                    salary=salary,
                    platform=matched_platform,
                    job_url=job_url,
                    recruiter_name=recruiter_name,
                    recruiter_email=recruiter_email,
                    notes=notes
                )
                imported_count += 1

        return Response({
            'message': f"Import complete: {imported_count} imported/updated, {duplicate_count} duplicates found, {invalid_count} invalid rows.",
            'imported_count': imported_count,
            'duplicate_count': duplicate_count,
            'invalid_count': invalid_count,
            'errors': errors
        }, status=status.HTTP_200_OK)

class ExportApplicationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        applications = Application.objects.filter(user=request.user)
        
        data = []
        for app in applications:
            data.append({
                'Company Name': app.company_name,
                'Job Title': app.job_title,
                'Location': app.location,
                'Applied Date': app.applied_date.strftime('%Y-%m-%d') if app.applied_date else '',
                'Status': app.status,
                'Salary': app.salary,
                'Platform': app.platform,
                'Job URL': app.job_url,
                'Recruiter Name': app.recruiter_name,
                'Recruiter Email': app.recruiter_email,
                'Notes': app.notes,
                'Created At': app.created_at.strftime('%Y-%m-%d %H:%M'),
                'Updated At': app.updated_at.strftime('%Y-%m-%d %H:%M'),
            })

        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Job Applications')
        
        output.seek(0)
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="job_applications.xlsx"'
        return response

class DownloadSampleTemplateView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        data = [
            {
                'Company Name': 'VE3',
                'Job Title': 'Senior Python Developer',
                'Location': 'Pune Division (Hybrid)',
                'Applied Date': '2026-08-03',
                'Status': 'Applied',
                'Salary': '14 LPA',
                'Platform': 'LinkedIn',
                'Job URL': 'https://linkedin.com/jobs/view/12345',
                'Recruiter Name': 'Supriya (IT Recruiter)',
                'Recruiter Email': 'talent@ve3.global',
                'Notes': 'Date 03/08/2026 Received Email from Supriya asking additional questions.'
            },
            {
                'Company Name': 'EPG Group',
                'Job Title': 'Senior Software Engineer (Python/Django)',
                'Location': 'Fully Remote',
                'Applied Date': '2026-08-05',
                'Status': 'Applied',
                'Salary': '18 LPA',
                'Platform': 'LinkedIn',
                'Job URL': 'https://epggroup.com/careers/789',
                'Recruiter Name': '',
                'Recruiter Email': '',
                'Notes': 'Submitted application.'
            }
        ]
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sample Applications')
        
        output.seek(0)
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="sample_applications.xlsx"'
        return response


class GmailAuthUrlView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        redirect_uri = request.query_params.get('redirect_uri', 'http://localhost:3000/gmail/callback')
        state = request.query_params.get('state', '')
        auth_url = GmailService.get_auth_url(redirect_uri, state)
        return Response({'auth_url': auth_url}, status=status.HTTP_200_OK)


class GmailConnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        code = request.data.get('code')
        redirect_uri = request.data.get('redirect_uri', '')
        access_token = request.data.get('access_token')
        refresh_token = request.data.get('refresh_token', '')
        email_address = request.data.get('email_address', '')
        client_id = request.data.get('client_id', '') or getattr(settings, 'GOOGLE_CLIENT_ID', '')
        client_secret = request.data.get('client_secret', '') or getattr(settings, 'GOOGLE_CLIENT_SECRET', '')

        if code:
            token_url = "https://oauth2.googleapis.com/token"
            try:
                resp = requests.post(token_url, data={
                    'code': code,
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'redirect_uri': redirect_uri,
                    'grant_type': 'authorization_code',
                }, timeout=10)

                if resp.status_code == 200:
                    token_data = resp.json()
                    access_token = token_data.get('access_token')
                    refresh_token = token_data.get('refresh_token', refresh_token)
                    if 'id_token' in token_data:
                        try:
                            from google.oauth2 import id_token
                            from google.auth.transport import requests as google_requests
                            id_info = id_token.verify_oauth2_token(token_data['id_token'], google_requests.Request())
                            email_address = id_info.get('email', email_address)
                        except Exception:
                            pass
                else:
                    return Response({'error': f"Failed to exchange Google OAuth code: {resp.text}"}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({'error': f"OAuth code exchange failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        if not access_token:
            return Response({'error': 'access_token or authorization code is required.'}, status=status.HTTP_400_BAD_REQUEST)

        credential, created = GmailCredential.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': access_token,
                'refresh_token': refresh_token or '',
                'email_address': email_address or request.user.email or '',
                'client_id': client_id or '',
                'client_secret': client_secret or '',
                'is_active': True
            }
        )

        return Response({
            'message': 'Gmail connected successfully.',
            'connected': True,
            'email_address': credential.email_address,
            'last_synced_at': credential.last_synced_at
        }, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)



class GmailStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            credential = GmailCredential.objects.get(user=request.user, is_active=True)
            return Response({
                'connected': True,
                'email_address': credential.email_address,
                'last_synced_at': credential.last_synced_at,
                'created_at': credential.created_at
            }, status=status.HTTP_200_OK)
        except GmailCredential.DoesNotExist:
            return Response({
                'connected': False,
                'message': 'Gmail account is not connected.'
            }, status=status.HTTP_200_OK)


class GmailSyncView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        mock_emails = request.data.get('mock_emails')

        try:
            credential = GmailCredential.objects.get(user=request.user, is_active=True)
        except GmailCredential.DoesNotExist:
            if not mock_emails:
                return Response({'error': 'Gmail account is not connected.'}, status=status.HTTP_400_BAD_REQUEST)
            credential = GmailCredential.objects.create(
                user=request.user,
                access_token='mock_access_token',
                email_address=request.user.email or 'user@example.com'
            )

        from applications.tasks import sync_gmail_jobs_task

        try:
            # Offload sync task to Celery worker queue
            task = sync_gmail_jobs_task.delay(request.user.id, mock_emails=mock_emails)
            
            # If Celery is running in eager/synchronous mode (e.g. testing), extract result directly
            if hasattr(task, 'result') and isinstance(task.result, dict) and 'scanned_emails_count' in task.result:
                sync_results = task.result
                return Response({
                    'message': f"Gmail sync complete. Created: {sync_results['created_count']}, Updated: {sync_results['updated_count']}, Scanned: {sync_results['scanned_emails_count']}.",
                    'task_id': getattr(task, 'id', None),
                    'details': sync_results
                }, status=status.HTTP_200_OK)

            # Asynchronous response for active Celery worker
            return Response({
                'message': 'Gmail sync task offloaded to Celery background worker.',
                'task_id': getattr(task, 'id', None),
                'status': 'QUEUED'
            }, status=status.HTTP_202_ACCEPTED)

        except Exception:
            # Fallback to direct execution if Celery broker/worker is unavailable
            service = GmailService(credential)
            sync_results = service.sync_user_applications(emails_data=mock_emails)
            return Response({
                'message': f"Gmail sync complete. Created: {sync_results['created_count']}, Updated: {sync_results['updated_count']}, Scanned: {sync_results['scanned_emails_count']}.",
                'details': sync_results
            }, status=status.HTTP_200_OK)


class GmailDisconnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        deleted_count, _ = GmailCredential.objects.filter(user=request.user).delete()
        return Response({
            'message': 'Gmail account disconnected successfully.' if deleted_count else 'No active Gmail integration found.',
            'connected': False
        }, status=status.HTTP_200_OK)


class GmailMessagesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        queryset = EmailMessage.objects.filter(user=request.user)
        
        status_param = request.query_params.get('status')
        if status_param and status_param != 'All':
            queryset = queryset.filter(processing_status=status_param)

        is_job_param = request.query_params.get('is_job_related')
        if is_job_param is not None:
            if is_job_param.lower() in ('true', '1'):
                queryset = queryset.filter(is_job_related=True)
            elif is_job_param.lower() in ('false', '0'):
                queryset = queryset.filter(is_job_related=False)

        search_query = request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(subject__icontains=search_query) |
                Q(sender_name__icontains=search_query) |
                Q(sender_email__icontains=search_query) |
                Q(extracted_company_name__icontains=search_query) |
                Q(extracted_job_title__icontains=search_query)
            )

        queryset = queryset.order_by('-received_at', '-id')

        pending_count = EmailMessage.objects.filter(user=request.user, processing_status=EmailProcessingStatus.PENDING_REVIEW).count()
        processed_count = EmailMessage.objects.filter(user=request.user, processing_status=EmailProcessingStatus.PROCESSED).count()
        ignored_count = EmailMessage.objects.filter(user=request.user, processing_status=EmailProcessingStatus.IGNORED).count()

        # Pagination
        total_count = queryset.count()
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = min(100, max(1, int(request.query_params.get('page_size', 10))))
        except (ValueError, TypeError):
            page_size = 10

        total_pages = max(1, (total_count + page_size - 1) // page_size)
        page = min(page, total_pages)
        start = (page - 1) * page_size
        end = start + page_size

        paginated_qs = queryset[start:end]
        serializer = EmailMessageSerializer(paginated_qs, many=True, context={'request': request})

        return Response({
            'count': total_count,
            'total_pages': total_pages,
            'current_page': page,
            'page_size': page_size,
            'pending_review_count': pending_count,
            'processed_count': processed_count,
            'ignored_count': ignored_count,
            'messages': serializer.data
        }, status=status.HTTP_200_OK)


class ApproveEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, email_id, *args, **kwargs):
        try:
            email_msg = EmailMessage.objects.get(id=email_id, user=request.user)
        except EmailMessage.DoesNotExist:
            return Response({'error': 'Email message not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Allow overrides from request body
        company_name = request.data.get('company_name') or email_msg.extracted_company_name or 'Unknown Company'
        job_title = request.data.get('job_title') or email_msg.extracted_job_title or 'Software Engineer'
        app_status = request.data.get('status') or email_msg.extracted_status or ApplicationStatus.APPLIED
        platform = request.data.get('platform') or email_msg.extracted_platform or ApplicationPlatform.LINKEDIN
        recruiter_name = request.data.get('recruiter_name') or email_msg.extracted_recruiter_name or ''
        recruiter_email = request.data.get('recruiter_email') or email_msg.extracted_recruiter_email or email_msg.sender_email
        notes = request.data.get('notes') or f"Approved from Gmail email: {email_msg.subject}"

        extracted_data = {
            'gmail_message_id': email_msg.gmail_message_id,
            'gmail_thread_id': email_msg.gmail_thread_id,
            'company_name': company_name,
            'job_title': job_title,
            'status': app_status,
            'platform': platform,
            'recruiter_name': recruiter_name,
            'recruiter_email': recruiter_email,
            'applied_date': email_msg.received_at.date() if email_msg.received_at else datetime.date.today(),
            'notes': notes
        }

        app_record, is_created = ApplicationService.process_extracted_job_email(request.user, email_msg, extracted_data)

        email_msg.extracted_company_name = company_name
        email_msg.extracted_job_title = job_title
        email_msg.extracted_status = app_status
        email_msg.extracted_platform = platform
        email_msg.processing_status = EmailProcessingStatus.PROCESSED
        email_msg.processed_at = datetime.datetime.now(datetime.timezone.utc)
        email_msg.save()

        return Response({
            'message': f"Application {'created' if is_created else 'updated'} successfully.",
            'action': 'created' if is_created else 'updated',
            'application_id': app_record.id,
            'company_name': app_record.company_name,
            'job_title': app_record.job_title,
            'status': app_record.status
        }, status=status.HTTP_200_OK)


class BulkApproveEmailsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        email_ids = request.data.get('email_ids', [])
        if not email_ids or not isinstance(email_ids, list):
            return Response({'error': 'email_ids array is required.'}, status=status.HTTP_400_BAD_REQUEST)

        approved_count = 0
        created_count = 0
        updated_count = 0

        for email_id in email_ids:
            try:
                email_msg = EmailMessage.objects.get(id=email_id, user=request.user)
            except EmailMessage.DoesNotExist:
                continue

            extracted_data = {
                'gmail_message_id': email_msg.gmail_message_id,
                'gmail_thread_id': email_msg.gmail_thread_id,
                'company_name': email_msg.extracted_company_name or 'Unknown Company',
                'job_title': email_msg.extracted_job_title or 'Software Engineer',
                'status': email_msg.extracted_status or ApplicationStatus.APPLIED,
                'platform': email_msg.extracted_platform or ApplicationPlatform.LINKEDIN,
                'recruiter_name': email_msg.extracted_recruiter_name or '',
                'recruiter_email': email_msg.extracted_recruiter_email or email_msg.sender_email,
                'applied_date': email_msg.received_at.date() if email_msg.received_at else datetime.date.today(),
                'notes': f"Bulk approved from Gmail: {email_msg.subject}"
            }

            app_record, is_created = ApplicationService.process_extracted_job_email(request.user, email_msg, extracted_data)

            email_msg.processing_status = EmailProcessingStatus.PROCESSED
            email_msg.processed_at = datetime.datetime.now(datetime.timezone.utc)
            email_msg.save()

            approved_count += 1
            if is_created:
                created_count += 1
            else:
                updated_count += 1

        return Response({
            'message': f"Bulk approval complete. Approved {approved_count} emails ({created_count} created, {updated_count} updated).",
            'approved_count': approved_count,
            'created_count': created_count,
            'updated_count': updated_count
        }, status=status.HTTP_200_OK)


class IgnoreEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, email_id, *args, **kwargs):
        try:
            email_msg = EmailMessage.objects.get(id=email_id, user=request.user)
        except EmailMessage.DoesNotExist:
            return Response({'error': 'Email message not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Block ignore if active application exists in Application table
        if email_msg.gmail_message_id and Application.objects.filter(user=request.user, gmail_message_id=email_msg.gmail_message_id).exists():
            return Response({
                'error': 'Cannot ignore email because an active application exists in the Application table. Please delete the application first.'
            }, status=status.HTTP_400_BAD_REQUEST)

        email_msg.processing_status = EmailProcessingStatus.IGNORED
        email_msg.processed_at = datetime.datetime.now(datetime.timezone.utc)
        email_msg.save()

        return Response({'message': 'Email marked as ignored.'}, status=status.HTTP_200_OK)


class BulkIgnoreEmailsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        email_ids = request.data.get('email_ids', [])
        if not email_ids or not isinstance(email_ids, list):
            return Response({'error': 'email_ids array is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Filter out emails that have linked active applications in Application table
        eligible_email_ids = []
        for email_id in email_ids:
            try:
                msg = EmailMessage.objects.get(id=email_id, user=request.user)
                if msg.gmail_message_id and Application.objects.filter(user=request.user, gmail_message_id=msg.gmail_message_id).exists():
                    continue
                eligible_email_ids.append(msg.id)
            except EmailMessage.DoesNotExist:
                continue

        updated = EmailMessage.objects.filter(
            id__in=eligible_email_ids,
            user=request.user
        ).update(
            processing_status=EmailProcessingStatus.IGNORED,
            processed_at=datetime.datetime.now(datetime.timezone.utc)
        )

        return Response({'message': f"Ignored {updated} email messages."}, status=status.HTTP_200_OK)


