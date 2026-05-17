from django import template

from clinics.tenant import get_active_membership

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.simple_tag(takes_context=True)
def active_membership_role(context):
    request = context.get("request")
    if not request or not request.user.is_authenticated:
        return ""
    membership = get_active_membership(request.user)
    return membership.role if membership else ""
