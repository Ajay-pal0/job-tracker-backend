from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from applications.models import Application, ApplicationStatus

class DashboardSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        qs = Application.objects.filter(user=request.user)
        total = qs.count()

        applied_count = qs.filter(status__in=[ApplicationStatus.APPLIED, ApplicationStatus.WISHLIST]).count()
        interviewing_count = qs.filter(status__in=[
            ApplicationStatus.INTERVIEW_SCHEDULED,
            ApplicationStatus.INTERVIEWING
        ]).count()
        offers_count = qs.filter(status__in=[
            ApplicationStatus.OFFER,
            ApplicationStatus.JOINED
        ]).count()
        rejected_count = qs.filter(status=ApplicationStatus.REJECTED).count()
        
        responses = interviewing_count + offers_count + rejected_count
        response_rate = round((responses / total * 100), 1) if total > 0 else 0.0

        return Response({
            'total_applications': total,
            'applied_count': applied_count,
            'interviewing_count': interviewing_count,
            'offers_count': offers_count,
            'rejected_count': rejected_count,
            'response_rate': response_rate
        })
