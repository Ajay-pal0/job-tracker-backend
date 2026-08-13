from rest_framework import serializers
from .models import Application, ApplicationEvent, EmailMessage, GmailConnection

class ApplicationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationEvent
        fields = ['id', 'application', 'email', 'event_type', 'event_date', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class EmailMessageSerializer(serializers.ModelSerializer):
    has_linked_application = serializers.SerializerMethodField()
    gmail_url = serializers.SerializerMethodField()

    class Meta:
        model = EmailMessage
        fields = [
            'id', 'gmail_message_id', 'gmail_thread_id', 'sender_name',
            'sender_email', 'subject', 'received_at', 'body_text', 'snippet',
            'is_job_related', 'extracted_company_name', 'extracted_job_title',
            'extracted_status', 'extracted_platform', 'extracted_recruiter_name',
            'extracted_recruiter_email', 'confidence_score',
            'processing_status', 'processed_at', 'created_at',
            'has_linked_application', 'gmail_url'
        ]
        read_only_fields = ['id', 'created_at', 'processed_at']

    def get_has_linked_application(self, obj) -> bool:
        if not obj.gmail_message_id:
            return False
        request = self.context.get('request')
        user = request.user if request and hasattr(request, 'user') else obj.user
        return Application.objects.filter(user=user, gmail_message_id=obj.gmail_message_id).exists()

    def get_gmail_url(self, obj) -> str:
        if obj.gmail_message_id:
            return f"https://mail.google.com/mail/u/0/#inbox/{obj.gmail_message_id}"
        return ""


class ApplicationSerializer(serializers.ModelSerializer):
    events = ApplicationEventSerializer(many=True, read_only=True)

    class Meta:
        model = Application
        fields = [
            'id', 'company_name', 'job_title', 'location', 'applied_date',
            'status', 'salary', 'platform', 'job_url', 'recruiter_name',
            'recruiter_email', 'notes', 'gmail_message_id', 'gmail_thread_id',
            'source_email', 'last_event_at', 'events', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
