from modeltranslation.translator import translator, TranslationOptions 

from .models import Category, Governorate, TermsAndCondition, AboutUs

class CategoryTranslationOptions(TranslationOptions):
    fields = ('name',)

class GovernorateTranslationOptions(TranslationOptions):
    fields = ('name',)

class TermsTranslationOptions(TranslationOptions):
    fields = ('title', 'content')

class AboutUsTranslationOptions(TranslationOptions):
    fields = ('content',)

# تسجيل الموديلات في المترجم
translator.register(Category, CategoryTranslationOptions)
translator.register(Governorate, GovernorateTranslationOptions)
translator.register(TermsAndCondition, TermsTranslationOptions)
translator.register(AboutUs, AboutUsTranslationOptions)