"""
URL configuration for iot_platform project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.views.generic import RedirectView
from django.contrib import admin
from django.urls import path, include
from iotcore import views as v
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/charts/', permanent=False)),

    # 先放“具体路径”，避免被 include('iotcore.urls') 截胡
    path("api/dev/thresholds/", v.device_thresholds, name="device-thresholds"),
    path("api/alerts/recent/", v.recent_alerts, name="alerts-recent"),

    # 再接入 iotcore 里其他路由/DRF router
    path('', include('iotcore.urls')),

    # 文档
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]


