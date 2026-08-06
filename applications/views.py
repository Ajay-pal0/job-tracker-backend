import datetime
import io
import os
import pandas as pd
from django.http import HttpResponse
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Application, ApplicationStatus, ApplicationPlatform
from .serializers import ApplicationSerializer

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
        else:
            queryset = queryset.order_by('-applied_date', '-created_at')

        return queryset

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
