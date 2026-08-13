from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ApplicationViewSet,
    ImportApplicationsView,
    ExportApplicationsView,
    DownloadSampleTemplateView,
    GmailAuthUrlView,
    GmailConnectView,
    GmailStatusView,
    GmailSyncView,
    GmailDisconnectView,
    GmailMessagesView,
    ApproveEmailView,
    BulkApproveEmailsView,
    IgnoreEmailView,
    BulkIgnoreEmailsView,
)

router = DefaultRouter()
router.register(r'', ApplicationViewSet, basename='application')

urlpatterns = [
    path('sample-template/', DownloadSampleTemplateView.as_view(), name='application_sample_template'),
    path('import/', ImportApplicationsView.as_view(), name='application_import'),
    path('export/', ExportApplicationsView.as_view(), name='application_export'),
    path('gmail/auth-url/', GmailAuthUrlView.as_view(), name='gmail_auth_url'),
    path('gmail/connect/', GmailConnectView.as_view(), name='gmail_connect'),
    path('gmail/status/', GmailStatusView.as_view(), name='gmail_status'),
    path('gmail/sync/', GmailSyncView.as_view(), name='gmail_sync'),
    path('gmail/disconnect/', GmailDisconnectView.as_view(), name='gmail_disconnect'),
    path('gmail/messages/', GmailMessagesView.as_view(), name='gmail_messages'),
    path('gmail/emails/<int:email_id>/approve/', ApproveEmailView.as_view(), name='gmail_email_approve'),
    path('gmail/emails/bulk-approve/', BulkApproveEmailsView.as_view(), name='gmail_email_bulk_approve'),
    path('gmail/emails/<int:email_id>/ignore/', IgnoreEmailView.as_view(), name='gmail_email_ignore'),
    path('gmail/emails/bulk-ignore/', BulkIgnoreEmailsView.as_view(), name='gmail_email_bulk_ignore'),
    path('', include(router.urls)),
]
