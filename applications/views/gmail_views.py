import requests
from django.conf import settings
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from applications.models import GmailCredential
from applications.services.gmail_service import GmailService
from applications.services.sync_service import sync_all_gmail_applications, trigger_background_user_sync

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

        # Synchronous mode for testing/mock emails
        if mock_emails is not None:
            service = GmailService(credential)
            sync_results = service.sync_user_applications(emails_data=mock_emails)
            sync_results.setdefault('messages', sync_results.get('processed_applications', []))
            sync_results.setdefault('user_results', [])
            sync_results.setdefault('processed_applications', [])
            return Response({
                'message': f"Gmail sync complete. Created: {sync_results.get('created_count', 0)}, Scanned: {sync_results.get('scanned_emails_count', 0)}.",
                'scanned_emails_count': sync_results.get('scanned_emails_count', 0),
                'created_count': sync_results.get('created_count', 0),
                'updated_count': sync_results.get('updated_count', 0),
                'pending_review_count': sync_results.get('pending_review_count', 0),
                'messages': sync_results.get('messages', []),
                'user_results': [],
                'processed_applications': sync_results.get('processed_applications', []),
                'details': sync_results
            }, status=status.HTTP_200_OK)

        # Offload user Gmail sync to background thread in sync_service
        trigger_background_user_sync(credential.id)

        from applications.models import EmailMessage, EmailProcessingStatus
        pending_count = EmailMessage.objects.filter(
            user=request.user,
            processing_status=EmailProcessingStatus.PENDING_REVIEW
        ).count()

        details_payload = {
            'scanned_emails_count': 0,
            'staged_emails_count': pending_count,
            'created_count': 0,
            'updated_count': 0,
            'pending_review_count': pending_count,
            'skipped_count': 0,
            'messages': [],
            'user_results': [],
            'processed_applications': []
        }

        return Response({
            'message': 'Gmail sync process started in the background. New job emails will appear in your review queue shortly.',
            'status': 'STARTED',
            'scanned_emails_count': 0,
            'created_count': 0,
            'updated_count': 0,
            'pending_review_count': pending_count,
            'messages': [],
            'user_results': [],
            'processed_applications': [],
            'details': details_payload
        }, status=status.HTTP_202_ACCEPTED)


class GmailInternalCronSyncView(APIView):
    """
    Internal endpoint to trigger batch Gmail synchronization across all users.
    Secured via CRON_SECRET header or query param. Can be invoked by GitHub Actions or cron.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        expected_secret = getattr(settings, 'CRON_SECRET', 'default-jobtracker-cron-secret-123')
        provided_secret = request.headers.get('X-Cron-Secret') or request.query_params.get('secret')

        if not provided_secret or provided_secret != expected_secret:
            return Response({'error': 'Unauthorized: Invalid cron secret.'}, status=status.HTTP_401_UNAUTHORIZED)

        result = sync_all_gmail_applications()
        return Response(result, status=status.HTTP_200_OK)


class GmailDisconnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        deleted_count, _ = GmailCredential.objects.filter(user=request.user).delete()
        return Response({
            'message': 'Gmail account disconnected successfully.' if deleted_count else 'No active Gmail integration found.',
            'connected': False
        }, status=status.HTTP_200_OK)
