from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ApplicationViewSet, ImportApplicationsView, ExportApplicationsView, DownloadSampleTemplateView

router = DefaultRouter()
router.register(r'', ApplicationViewSet, basename='application')

urlpatterns = [
    path('sample-template/', DownloadSampleTemplateView.as_view(), name='application_sample_template'),
    path('import/', ImportApplicationsView.as_view(), name='application_import'),
    path('export/', ExportApplicationsView.as_view(), name='application_export'),
    path('', include(router.urls)),
]
