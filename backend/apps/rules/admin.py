from django.contrib import admin
from .models import Placeholder, ReplyTemplate, Rule

admin.site.register(Placeholder)
admin.site.register(ReplyTemplate)
admin.site.register(Rule)
