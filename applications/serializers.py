from rest_framework import serializers
from .models import Application, ApplicationStatus, ApplicationPlatform

class ApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = [
            'id', 'company_name', 'job_title', 'location', 'applied_date',
            'status', 'salary', 'platform', 'job_url', 'recruiter_name',
            'recruiter_email', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
