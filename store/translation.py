from modeltranslation.translator import translator, TranslationOptions
from .models import Category, Product, Governorate, AboutUs, TermsAndCondition

class CategoryTranslationOptions(TranslationOptions):
    fields = ('name',)

class ProductTranslationOptions(TranslationOptions):
    fields = ('name', 'description')

class GovernorateTranslationOptions(TranslationOptions):
    fields = ('name',)

class AboutUsTranslationOptions(TranslationOptions):
    fields = ('content',)

class TermsAndConditionTranslationOptions(TranslationOptions):
    fields = ('title', 'content')

# تسجيل الموديلات في مكتبة الترجمة
translator.register(Category, CategoryTranslationOptions)
translator.register(Product, ProductTranslationOptions)
translator.register(Governorate, GovernorateTranslationOptions)
translator.register(AboutUs, AboutUsTranslationOptions)
translator.register(TermsAndCondition, TermsAndConditionTranslationOptions)