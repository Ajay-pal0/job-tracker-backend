from rest_framework import serializers
from django.contrib.auth.models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class UserSerializer(serializers.ModelSerializer):
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'has_password']

    def get_has_password(self, obj):
        return obj.has_usable_password()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'password', 'confirm_password']

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"password": "Password fields do not match."})
        if attrs.get('email') and User.objects.filter(email=attrs.get('email')).exists():
            raise serializers.ValidationError({"email": "User with this email already exists."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user

class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        login_id = attrs.get('email') or attrs.get('username')

        if not login_id:
            raise serializers.ValidationError({'detail': 'Email or username is required.'})

        if '@' in login_id:
            try:
                user_obj = User.objects.get(email__iexact=login_id)
                username = user_obj.username
            except User.DoesNotExist:
                username = login_id
            except User.MultipleObjectsReturned:
                user_obj = User.objects.filter(email__iexact=login_id).first()
                username = user_obj.username if user_obj else login_id
        else:
            username = login_id

        attrs['username'] = username
        return super().validate(attrs)

class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True)

class SSOLoginSerializer(serializers.Serializer):
    provider = serializers.CharField(required=False, default='google')
    token = serializers.CharField(required=True)

class SetChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    new_password = serializers.CharField(required=True, min_length=6, write_only=True)
    confirm_password = serializers.CharField(required=True, min_length=6, write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})

        if user.has_usable_password():
            if not attrs.get('old_password'):
                raise serializers.ValidationError({"old_password": "Old password is required to change password."})
            if not user.check_password(attrs['old_password']):
                raise serializers.ValidationError({"old_password": "Old password is incorrect."})

        return attrs

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class ResetPasswordSerializer(serializers.Serializer):
    uidb64 = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6, write_only=True)
    confirm_password = serializers.CharField(required=True, min_length=6, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs
