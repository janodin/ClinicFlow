from django.http import HttpResponse


def privacy_policy(request):
    from django.template.loader import get_template
    template = get_template("privacy_policy.html")
    return HttpResponse(template.render(), content_type="text/html; charset=utf-8")