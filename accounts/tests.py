from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

class AccountsTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='Password123!',
            first_name='Test',
            last_name='User'
        )
        self.google_email = 'googleuser@example.com'

    def test_login_with_email_success(self):
        url = reverse('token_obtain_pair')
        response = self.client.post(url, {
            'username': 'testuser@example.com',
            'password': 'Password123!'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_with_username_success(self):
        url = reverse('token_obtain_pair')
        response = self.client.post(url, {
            'username': 'testuser',
            'password': 'Password123!'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_google_login_new_user(self, mock_verify):
        mock_verify.return_value = {
            'email': self.google_email,
            'given_name': 'Google',
            'family_name': 'Person',
            'sub': '1234567890'
        }

        url = reverse('google_login')
        response = self.client.post(url, {'id_token': 'fake-id-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], self.google_email)
        self.assertFalse(response.data['user']['has_password'])

        new_user = User.objects.get(email=self.google_email)
        self.assertFalse(new_user.has_usable_password())

    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_google_login_existing_user(self, mock_verify):
        mock_verify.return_value = {
            'email': 'testuser@example.com',
            'given_name': 'Test',
            'family_name': 'User',
            'sub': '1234567890'
        }

        url = reverse('google_login')
        response = self.client.post(url, {'id_token': 'fake-id-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertEqual(response.data['user']['email'], 'testuser@example.com')
        self.assertTrue(response.data['user']['has_password'])

    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_google_login_invalid_token(self, mock_verify):
        mock_verify.side_effect = ValueError('Token expired')

        url = reverse('google_login')
        response = self.client.post(url, {'id_token': 'invalid-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    @patch('accounts.sso.GitHubSSOProvider.verify_token')
    def test_sso_github_login(self, mock_github_verify):
        mock_github_verify.return_value = {
            'email': 'githubuser@example.com',
            'first_name': 'Octo',
            'last_name': 'Cat',
            'provider': 'github',
            'provider_id': '998877'
        }

        url = reverse('sso_login_provider', kwargs={'provider_name': 'github'})
        response = self.client.post(url, {'token': 'fake-github-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['provider'], 'github')
        self.assertEqual(response.data['user']['email'], 'githubuser@example.com')

    def test_unsupported_sso_provider(self):
        url = reverse('sso_login_provider', kwargs={'provider_name': 'unsupported_provider'})
        response = self.client.post(url, {'token': 'some-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_set_password_for_google_sso_user(self):
        google_user = User.objects.create_user(
            username='google_user',
            email='google_user@example.com',
            first_name='Google',
            last_name='User'
        )
        google_user.set_unusable_password()
        google_user.save()

        self.client.force_authenticate(user=google_user)
        url = reverse('set_password')

        data = {
            'new_password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!'
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        google_user.refresh_from_db()
        self.assertTrue(google_user.has_usable_password())
        self.assertTrue(google_user.check_password('NewPassword123!'))

    def test_change_password_for_existing_password_user(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('set_password')

        wrong_data = {
            'old_password': 'WrongPassword!',
            'new_password': 'BrandNewPassword123!',
            'confirm_password': 'BrandNewPassword123!'
        }
        response = self.client.post(url, wrong_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        correct_data = {
            'old_password': 'Password123!',
            'new_password': 'BrandNewPassword123!',
            'confirm_password': 'BrandNewPassword123!'
        }
        response = self.client.post(url, correct_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPassword123!'))

    def test_forgot_and_reset_password_flow(self):
        forgot_url = reverse('forgot_password')
        response = self.client.post(forgot_url, {'email': self.user.email}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('uidb64', response.data)
        self.assertIn('token', response.data)

        uidb64 = response.data['uidb64']
        token = response.data['token']

        reset_url = reverse('reset_password')
        reset_data = {
            'uidb64': uidb64,
            'token': token,
            'new_password': 'ResetPassword123!',
            'confirm_password': 'ResetPassword123!'
        }
        reset_response = self.client.post(reset_url, reset_data, format='json')

        self.assertEqual(reset_response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('ResetPassword123!'))
