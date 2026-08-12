from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    UserProfileView,
    EmailOrUsernameTokenObtainPairView,
    SSOLoginView,
    GoogleLoginView,
    SetChangePasswordView,
    ForgotPasswordView,
    ResetPasswordView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', EmailOrUsernameTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', UserProfileView.as_view(), name='user_profile'),

    # Unified SSO endpoints
    path('sso/', SSOLoginView.as_view(), name='sso_login_generic'),
    path('sso/<str:provider_name>/', SSOLoginView.as_view(), name='sso_login_provider'),

    # Legacy / specific provider shortcut routes
    path('google/', GoogleLoginView.as_view(), name='google_login'),

    # Password management
    path('set-password/', SetChangePasswordView.as_view(), name='set_password'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
]
