import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url
from django.contrib.messages import constants as messages
from datetime import timedelta
from django.utils.translation import gettext_lazy as _

# ==========================================
# 1. BASE DIRECTORY & ENVIRONMENT VARIABLES
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))

# ==========================================
# 2. CORE SETTINGS
# ==========================================
SECRET_KEY = 'django-insecure-2=@6ne*bhsuw#t^inbg*7fs5h5*@&h)(1f90mp45jp1oh+f(o@'
DEBUG = True
# ALLOWED_HOSTS = ['elbazaare.com', 'www.elbazaare.com', '147.93.56.140','127.0.0.1']
ALLOWED_HOSTS = ['*']
ROOT_URLCONF = 'bazarna.urls'
WSGI_APPLICATION = 'bazarna.wsgi.application'
SITE_ID = 1

# ==========================================
# 3. SECURITY & CORS SETTINGS
# ==========================================
SESSION_COOKIE_AGE = 1209600 # الجلسة تفضل شغالة لمدة أسبوعين (بالثواني)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False # يمنع مسح الجلسة لما التطبيق يتقفل
PREPEND_WWW = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    'https://elbazaare.com',
    'https://www.elbazaare.com',
    'https://pluvious-ejectively-violet.ngrok-free.dev'
]

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
# ==========================================
# 4. APPLICATIONS & MIDDLEWARE
# ==========================================
INSTALLED_APPS = [
    'modeltranslation',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    
    # Third-Party Apps
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',    
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework.authtoken',
    'corsheaders',

    # Local Apps
    'accounts',
    'store',
    'support',
    'merchant_panel',
    'supervisor',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',      # 👈 بتحدد اللغة من اللينك (/ar/)
    'django.middleware.common.CommonMiddleware',      # 👈 بتعالج اللينك بناءً على اللغة (لازم تكون هنا!)
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.middleware.BanMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

# ==========================================
# 5. TEMPLATES
# ==========================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'store.context_processors.site_settings',
                'support.context_processors.support_tickets_processor',
                'accounts.context_processors.mobile_app_detector',
                'store.context_processors.active_promo_popup'
            ],
        },
    },
]

# ==========================================
# 6. DATABASE & CACHING
# ==========================================
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'bazarna_db',
#         'USER': 'bazarna_user',
#         'PASSWORD': 'BazarnaPass2024',
#         'HOST': 'localhost',
#         'PORT': '5432',
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache_table',
    }
}






USE_I18N = True
USE_L10N = True

LANGUAGE_CODE = 'ar'

LANGUAGES = (
    ('ar', _('Arabic')),
    ('en', _('English')),
)

MODELTRANSLATION_DEFAULT_LANGUAGE = 'ar'

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]
# ==========================================
# 7. AUTHENTICATION & ALLAUTH
# ==========================================
AUTH_USER_MODEL = 'accounts.User'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'accounts.backends.EmailPhoneUsernameBackend', 
    'allauth.account.auth_backends.AuthenticationBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Accounts & AllAuth Settings
ACCOUNT_ADAPTER = 'accounts.adapters.MyAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'accounts.adapters.MySocialAccountAdapter'
ACCOUNT_RATE_LIMITS = {}
LOGIN_REDIRECT_URL = '/'  
LOGOUT_REDIRECT_URL = '/accounts/login/' 

ACCOUNT_EMAIL_REQUIRED = False 
ACCOUNT_USERNAME_REQUIRED = False 
ACCOUNT_AUTHENTICATION_METHOD = 'username_email' 
ACCOUNT_EMAIL_VERIFICATION = 'none' 

SOCIALACCOUNT_AUTO_SIGNUP = True 
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_FORMS = {'signup': 'accounts.forms.MySocialSignupForm'}

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'key': ''
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'VERIFIED_EMAIL': True
    }
}

# ==========================================
# 8. DJANGO REST FRAMEWORK
# ==========================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication', # الاعتماد الأساسي لتطبيق الموبايل
        'rest_framework.authentication.SessionAuthentication', # نحتاجها فقط للوحة تحكم جانجو (Admin)
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}




SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),  # مدة صلاحية التوكن الأساسي (يوم واحد)
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30), # مدة صلاحية توكن التجديد (شهر)
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}
# ==========================================
# 9. INTERNATIONALIZATION & TIME
# ==========================================
LANGUAGE_CODE = 'ar'     # 👈 خليها عربي هنا كمان للضمان
TIME_ZONE = 'Africa/Cairo'
USE_TZ = True
USE_L10N = True

DATE_FORMAT = 'Y-m-d' 
TIME_FORMAT = 'P' 
DATETIME_FORMAT = 'Y-m-d P'

# ==========================================
# 10. STATIC & MEDIA FILES
# ==========================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')] 
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ==========================================
# 11. THIRD-PARTY & EXTRA CONFIGURATIONS
# ==========================================
# Paymob Configuration
PAYMOB_API_KEY = os.getenv('PAYMOB_API_KEY')
PAYMOB_INTEGRATION_ID_CARD = os.getenv('PAYMOB_INTEGRATION_ID_CARD')
PAYMOB_INTEGRATION_ID_WALLET = os.getenv('PAYMOB_INTEGRATION_ID_WALLET')
PAYMOB_IFRAME_ID = os.getenv('PAYMOB_IFRAME_ID')

# Upload Limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 20971520  
FILE_UPLOAD_MAX_MEMORY_SIZE = 20971520

# Message Tags (Bootstrap Integration)
MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger', 
}


import os
import firebase_admin
from firebase_admin import credentials

# 🔥 مسار ملف الجيسون اللي نزلناه من فايربيز
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, 'firebase-key.json')

# تهيئة فايربيز لو مش متهيئة قبل كده
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)


