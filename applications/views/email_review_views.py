import datetime
from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from applications.models import Application, ApplicationStatus, ApplicationPlatform, EmailMessage, EmailProcessingStatus
from applications.serializers import EmailMessageSerializer
from applications.services.application_service import ApplicationService

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
