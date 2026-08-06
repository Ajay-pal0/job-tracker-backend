from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.db.models import Count
from django.db.models.functions import TruncMonth
from applications.models import Application, ApplicationStatus, ApplicationPlatform

class AnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        qs = Application.objects.filter(user=request.user)
        total = qs.count()

        # Status breakdown
        status_counts = dict(qs.values_list('status').annotate(count=Count('id')))
        by_status = []
        for status_choice, _ in ApplicationStatus.choices:
            cnt = status_counts.get(status_choice, 0)
            pct = round((cnt / total * 100), 1) if total > 0 else 0.0
            by_status.append({
                'status': status_choice,
                'count': cnt,
                'percentage': pct
            })

        # Platform breakdown
        platform_counts = dict(qs.values_list('platform').annotate(count=Count('id')))
        by_platform = []
        for platform_choice, _ in ApplicationPlatform.choices:
            cnt = platform_counts.get(platform_choice, 0)
            if cnt > 0: # only include platforms that have applications or standard ones
                pct = round((cnt / total * 100), 1) if total > 0 else 0.0
                by_platform.append({
                    'platform': platform_choice,
                    'count': cnt,
                    'percentage': pct
                })

        # Monthly breakdown
        monthly_qs = qs.annotate(month=TruncMonth('applied_date')).values('month').annotate(count=Count('id')).order_by('month')
        by_month = []
        for entry in monthly_qs:
            if entry['month']:
                by_month.append({
                    'month': entry['month'].strftime('%b %Y'),
                    'count': entry['count']
                })

        interviewing_cnt = qs.filter(status__in=[ApplicationStatus.INTERVIEW_SCHEDULED, ApplicationStatus.INTERVIEWING]).count()
        offers_cnt = qs.filter(status__in=[ApplicationStatus.OFFER, ApplicationStatus.JOINED]).count()
        rejections_cnt = qs.filter(status=ApplicationStatus.REJECTED).count()
        
        responses = interviewing_cnt + offers_cnt + rejections_cnt
        response_rate = round((responses / total * 100), 1) if total > 0 else 0.0

        return Response({
            'total_applications': total,
            'by_status': by_status,
            'by_platform': by_platform,
            'by_month': by_month,
            'response_rate': response_rate,
            'offers_count': offers_cnt,
            'rejections_count': rejections_cnt
        })
